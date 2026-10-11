#!/usr/bin/env python3
"""Deterministically render the TrimUI Brick semantic OpenSCAD model.

The source-model task deliberately does not write runtime skins.  Its semantic
atlas is a four-view review sheet: front controls, the rear shoulder shelf,
left-side volume keys, and right-side function/power keys.  A later integration
task can turn the owner-approved source into device-specific runtime views.

Each file it hashes and then uses is read once (tsp-h5ed.46.34): the .scad and
render.py are hashed before the first OpenSCAD call, those hashes are recorded and
compared, and both are re-hashed before anything is written (``ensure_inputs``);
a recorded PNG and semantic-model.json are read through one open file, and the keep
decision and the recorded hash use those same bytes (``read_pinned``), after the
path is re-checked to still name the file that was read (``ensure_pinned``). A
mismatch refuses, naming the file; re-run. Residual window (accidents, not
adversaries): OpenSCAD opens the .scad by path, so an edit undone between the two
hashes is not seen; a rewrite in place to the same size keeps (st_dev, st_ino,
st_size); a file replaced after its last check is recorded with the hash of the
bytes that were compared, so the record no longer matches it; and the running
render.py is the one Python imported before the first hash.
"""

from __future__ import annotations

import argparse
import hashlib
import io
from itertools import combinations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from PIL import Image, ImageChops


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RENDERER = HERE / "render.py"
MODEL = HERE / "trimui-brick.scad"

RAW_SIZE = (1500, 2100)
VIEW_CANVAS = (900, 1200)
SEMANTIC_CANVAS = (1800, 1600)
PADDING = 14
DIFF_THRESHOLD = 20
RECT_PADDING = 0
RENDER_SETTLE_SECONDS = 0.15

# Tie jitter. Copied from trimui-smart-pro/render.py (tsp-h5ed.46.29) by tsp-h5ed.46.32
# rather than shared: that render.py's hash is recorded in the committed a133 skin.
# OpenSCAD 2021.01 does not draw identical geometry from one process to the next: a
# few pixels on edges where two faces tie take one face's shade or the other's (0-30
# pixels per a133/a523 skin canvas). None was measured at the Brick's cameras (6
# semantic sets and 6 view sets, 174 frames, byte-identical), but the renderer is the
# same. A re-render into an output directory whose semantic-model.json records an
# UNEDITED .scad AND render.py, whose derived crops/rects equal the recorded ones and
# whose PNG differs from the recorded PNG in at most JITTER_MAX_PIXELS pixels keeps
# the recorded bytes. Editing either input always writes fresh renders.
JITTER_MAX_PIXELS = 128
# A tie pixel inside a highlighted control's red frame can cross DIFF_THRESHOLD at the
# control's edge (measured on the a523's trig_r: one row). With unedited inputs and
# the recorded crops, a derived rect whose every edge is within JITTER_RECT_PIXELS of
# the recorded rect takes the recorded rect (see ``canonical_rects``).
JITTER_RECT_PIXELS = 1

APP_CAMERA = "36.4,55.375,350,36.4,55.375,10"
APP_ROTATE = 0

VIEW_CAMERAS = {
    "front": (APP_CAMERA, 0),
    "rear": ("36.4,55.375,-320,36.4,55.375,10", 0),
    "top": ("36.4,360,10,36.4,55.375,10", 180),
    "bottom": ("36.4,-260,10,36.4,55.375,10", 0),
    "left": ("-300,55.375,10,36.4,55.375,10", 270),
    "right": ("370,55.375,10,36.4,55.375,10", 90),
}

CONTROL_IDS = (
    "dpad",
    "btn_north",
    "btn_east",
    "btn_south",
    "btn_west",
    "btn_f1",
    "btn_f2",
    "btn_menu",
    "btn_select",
    "btn_start",
    "btn_l1",
    "trig_l",
    "trig_r",
    "btn_r1",
    "vol_up",
    "vol_down",
    "btn_fn",
    "btn_power",
)

SEMANTIC_VIEWS = {
    "front": {
        "tile": (0, 0, 900, 1600),
        "controls": (
            "dpad",
            "btn_north",
            "btn_east",
            "btn_south",
            "btn_west",
            "btn_f1",
            "btn_f2",
            "btn_menu",
            "btn_select",
            "btn_start",
        ),
    },
    "top": {
        "tile": (900, 0, 900, 500),
        "controls": ("btn_l1", "trig_l", "trig_r", "btn_r1"),
    },
    "left": {
        "tile": (900, 500, 900, 500),
        "controls": ("vol_up", "vol_down"),
    },
    "right": {
        "tile": (900, 1000, 900, 500),
        "controls": ("btn_fn", "btn_power"),
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def shown(path: Path) -> Path:
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def _after_read(path: Path) -> None:
    """Test hook: runs right after ``read_pinned`` read ``path``, before any use."""


def read_pinned(path: Path) -> tuple[bytes, tuple[int, int, int]] | None:
    """``path``'s bytes and the (st_dev, st_ino, st_size) of the file they came from,
    through one open file; None when ``path`` is not a file."""
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        data = stream.read()
        status = os.fstat(stream.fileno())
    _after_read(path)
    return data, (status.st_dev, status.st_ino, status.st_size)


def ensure_pinned(path: Path, identity: tuple[int, int, int] | None) -> None:
    """Refuse when ``path`` no longer names the file ``read_pinned`` read (None:
    there was none)."""
    try:
        status = path.stat()
        current = (status.st_dev, status.st_ino, status.st_size)
    except FileNotFoundError:
        current = None
    if current != identity:
        raise RuntimeError(f"{shown(path)} changed while render.py was using it; re-run")


def input_hashes() -> dict[str, str]:
    """The .scad and render.py hashes, taken before a render reads the .scad."""
    return {"source_sha256": sha256(MODEL), "renderer_sha256": sha256(RENDERER)}


def ensure_inputs(inputs: dict) -> None:
    """Refuse when the .scad or render.py no longer hashes to ``inputs``."""
    for key, path in (("source_sha256", MODEL), ("renderer_sha256", RENDERER)):
        if sha256(path) != inputs.get(key):
            raise RuntimeError(f"{shown(path)} changed during the render; re-run")


def run_openscad(
    output: Path,
    *,
    camera: str,
    highlight: str = "",
    part: str = "assembly",
    control_id: str = "btn_east",
    screen_marker: bool = False,
    raw_size: tuple[int, int] = RAW_SIZE,
) -> None:
    command = [
        os.environ.get("OPENSCAD", "openscad"),
        "--hardwarnings",
        "--check-parameters=true",
        "--check-parameter-ranges=true",
        "-o",
        str(output.resolve()),
        f"--imgsize={raw_size[0]},{raw_size[1]}",
        "--projection=ortho",
        "--viewall",
        "--colorscheme=Tomorrow",
        f"--camera={camera}",
        "-D",
        'QUALITY="render"',
        "-D",
        f'PART="{part}"',
        "-D",
        f'CONTROL_ID="{control_id}"',
        "-D",
        f'HIGHLIGHT="{highlight}"',
        "-D",
        f"SCREEN_MARKER={'true' if screen_marker else 'false'}",
        str(MODEL),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0 or "ERROR:" in completed.stdout:
        print(completed.stdout, file=sys.stderr)
        raise RuntimeError(
            f"OpenSCAD failed ({completed.returncode}): {' '.join(command)}"
        )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"OpenSCAD produced no image: {output}")


def normalized_raw(path: Path, rotation: int) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    if rotation:
        image = image.rotate(
            rotation,
            expand=True,
            fillcolor=image.getpixel((0, 0)),
        )
    return image


def exact_foreground_bbox(
    image: Image.Image,
    threshold: int = 3,
) -> tuple[int, int, int, int]:
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    difference = ImageChops.difference(image, background).convert("L")
    box = difference.point(
        lambda value: 255 if value > threshold else 0
    ).getbbox()
    if box is None:
        raise RuntimeError("render contains no foreground pixels")
    return box


def foreground_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    left, top, right, bottom = exact_foreground_bbox(image)
    return (
        max(0, left - PADDING),
        max(0, top - PADDING),
        min(image.width, right + PADDING),
        min(image.height, bottom + PADDING),
    )


def fit_transform(
    image: Image.Image,
    crop: tuple[int, int, int, int],
    canvas: tuple[int, int],
) -> Image.Image:
    cropped = image.crop(crop)
    available = (canvas[0] - 2 * PADDING, canvas[1] - 2 * PADDING)
    scale = min(available[0] / cropped.width, available[1] / cropped.height)
    target = (
        max(1, round(cropped.width * scale)),
        max(1, round(cropped.height * scale)),
    )
    resized = cropped.resize(target, Image.Resampling.LANCZOS)
    result = Image.new("RGB", canvas, image.getpixel((0, 0)))
    offset = ((canvas[0] - target[0]) // 2, (canvas[1] - target[1]) // 2)
    result.paste(resized, offset)
    return result


def diff_rect(
    neutral: Image.Image,
    changed: Image.Image,
    *,
    padding: int = RECT_PADDING,
) -> dict[str, int]:
    difference = ImageChops.difference(neutral, changed).convert("L")
    box = difference.point(
        lambda value: 255 if value >= DIFF_THRESHOLD else 0
    ).getbbox()
    if box is None:
        raise RuntimeError("semantic highlight changed zero pixels")
    left, top, right, bottom = box
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(neutral.width, right + padding)
    bottom = min(neutral.height, bottom + padding)
    return {
        "x": left,
        "y": top,
        "w": right - left,
        "h": bottom - top,
    }


def overlap_box(
    first: dict[str, int],
    second: dict[str, int],
) -> tuple[int, int, int, int] | None:
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["w"], second["x"] + second["w"])
    bottom = min(first["y"] + first["h"], second["y"] + second["h"])
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def rectangle_overlaps(
    rectangles: dict[str, dict[str, int]],
) -> list[tuple[str, str, tuple[int, int, int, int]]]:
    overlaps = []
    for (first_id, first), (second_id, second) in combinations(
        rectangles.items(), 2
    ):
        overlap = overlap_box(first, second)
        if overlap is not None:
            overlaps.append((first_id, second_id, overlap))
    return overlaps


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=9)


def tie_jitter_pixels(committed: bytes | None, image: Image.Image) -> int | None:
    """Pixels where ``image`` differs from the committed PNG (its bytes) in any
    channel; None when there is no committed PNG or the sizes differ."""
    if committed is None:
        return None
    with Image.open(io.BytesIO(committed)) as source:
        previous = source.convert("RGB")
    if previous.size != image.size:
        return None
    red, green, blue = ImageChops.difference(previous, image.convert("RGB")).split()
    changed = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    return changed.point(lambda value: 255 if value else 0).histogram()[255]


def inputs_unchanged(committed: dict | None, inputs: dict | None = None) -> bool:
    """The committed metadata was rendered from this .scad by this render.py
    (``inputs``, from ``input_hashes``; hashed now when None)."""
    if committed is None:
        return False
    inputs = input_hashes() if inputs is None else inputs
    return (
        committed.get("source_sha256") == inputs["source_sha256"]
        and committed.get("renderer_sha256") == inputs["renderer_sha256"]
    )


def keeps_committed(committed: bytes | None, image: Image.Image, same: bool) -> bool:
    """True when ``image`` is a tie-jitter re-render of the committed PNG (its bytes)
    and ``same`` (see ``same_derivation``) holds."""
    if not same:
        return False
    count = tie_jitter_pixels(committed, image)
    return count is not None and count <= JITTER_MAX_PIXELS


def same_derivation(
    committed: dict | None,
    inputs_same: bool,
    derived: dict,
    keys: tuple[str, ...],
) -> bool:
    """The committed render came from the same inputs (``inputs_unchanged``) and
    derived the same geometry."""
    return (
        inputs_same
        and committed is not None
        and all(committed.get(key) == derived.get(key) for key in keys)
    )


def save_canonical_png(image: Image.Image, path: Path, same: bool) -> str:
    """Write ``image`` unless it only tie-jitters against the committed ``path``;
    return the sha256 of the bytes ``path`` holds. The committed PNG is read once:
    the kept bytes are the ones compared and hashed."""
    pinned = read_pinned(path) if same else None
    if pinned is None or not keeps_committed(pinned[0], image, same):
        save_png(image, path)
        return sha256(path)
    committed, identity = pinned
    count = tie_jitter_pixels(committed, image)
    ensure_pinned(path, identity)
    if count:
        # The output directory need not be under ROOT (unlike the a133 skin).
        print(f"tie_jitter=kept path={shown(path)} pixels={count}")
    return hashlib.sha256(committed).hexdigest()


def rect_edges(rectangle: dict[str, int]) -> tuple[int, int, int, int]:
    return (
        rectangle["x"],
        rectangle["y"],
        rectangle["x"] + rectangle["w"],
        rectangle["y"] + rectangle["h"],
    )


def canonical_rects(
    fresh: dict[str, dict[str, int]],
    committed: dict | None,
    same: bool,
) -> dict[str, dict[str, int]]:
    """The committed rects when ``same`` (unedited inputs and the committed crop), the
    ids match and every fresh edge is within JITTER_RECT_PIXELS of the committed one;
    otherwise ``fresh``."""
    if (not same or not isinstance(committed, dict) or set(committed) != set(fresh)
            or not all(isinstance(rect, dict) for rect in committed.values())):
        return fresh
    for name, rectangle in fresh.items():
        moved = zip(rect_edges(rectangle), rect_edges(committed[name]))
        if max(abs(new - old) for new, old in moved) > JITTER_RECT_PIXELS:
            return fresh
    kept = sorted(name for name in fresh if fresh[name] != committed[name])
    if kept:
        print(f"tie_jitter=kept rects={','.join(kept)}")
    return {name: dict(committed[name]) for name in fresh}


SEMANTIC_DERIVATION_KEYS = (
    "canvas", "controls", "control_views", "display_rect", "views"
)


def render_fitted(
    work: Path,
    *,
    stem: str,
    view_name: str,
    canvas: tuple[int, int],
    crop: tuple[int, int, int, int] | None = None,
    highlight: str = "",
    screen_marker: bool = False,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    camera, rotation = VIEW_CAMERAS[view_name]
    raw = work / f"{stem}-raw.png"
    run_openscad(
        raw,
        camera=camera,
        highlight=highlight,
        screen_marker=screen_marker,
    )
    source = normalized_raw(raw, rotation)
    chosen_crop = foreground_bbox(source) if crop is None else crop
    return fit_transform(source, chosen_crop, canvas), chosen_crop


def offset_rect(
    rectangle: dict[str, int],
    x: int,
    y: int,
) -> dict[str, int]:
    return {
        "x": rectangle["x"] + x,
        "y": rectangle["y"] + y,
        "w": rectangle["w"],
        "h": rectangle["h"],
    }


def inset_rect(rectangle: dict[str, int], amount: int) -> dict[str, int]:
    if rectangle["w"] <= 2 * amount or rectangle["h"] <= 2 * amount:
        raise RuntimeError(f"cannot inset collapsed rectangle: {rectangle}")
    return {
        "x": rectangle["x"] + amount,
        "y": rectangle["y"] + amount,
        "w": rectangle["w"] - 2 * amount,
        "h": rectangle["h"] - 2 * amount,
    }


def render_skin_set(
    work: Path, committed: dict | None = None
) -> tuple[Image.Image, Image.Image, dict]:
    """Build the model-stage semantic review atlas.

    The function name is retained for the repository validator.  This atlas is
    evidence, not a committed runtime skin: controls are assigned to the view
    where the physical input is actually visible.  ``committed`` is a previous
    semantic-model.json, whose rects a tie-jittered derivation keeps
    (``canonical_rects``).
    """
    inputs = input_hashes()
    work.mkdir(parents=True, exist_ok=True)
    neutral_atlas: Image.Image | None = None
    lit_atlas: Image.Image | None = None
    rectangles: dict[str, dict[str, int]] = {}
    control_views: dict[str, str] = {}
    display_rect: dict[str, int] | None = None
    camera_metadata: dict[str, dict] = {}
    highlights: dict[str, tuple[Image.Image, int, int]] = {}

    for view_name, spec in SEMANTIC_VIEWS.items():
        tile_x, tile_y, tile_w, tile_h = spec["tile"]
        tile_size = (tile_w, tile_h)
        neutral, crop = render_fitted(
            work,
            stem=f"{view_name}-neutral",
            view_name=view_name,
            canvas=tile_size,
        )
        if neutral_atlas is None:
            background = neutral.getpixel((0, 0))
            neutral_atlas = Image.new("RGB", SEMANTIC_CANVAS, background)
            lit_atlas = Image.new("RGB", SEMANTIC_CANVAS, background)
        assert lit_atlas is not None
        neutral_atlas.paste(neutral, (tile_x, tile_y))
        lit_atlas.paste(neutral, (tile_x, tile_y))

        camera, rotation = VIEW_CAMERAS[view_name]
        camera_metadata[view_name] = {
            "projection": "ortho",
            "eye_target": camera,
            "raw_rotation_degrees": rotation,
            "crop": list(crop),
            "tile": {
                "x": tile_x,
                "y": tile_y,
                "w": tile_w,
                "h": tile_h,
            },
        }

        if view_name == "front":
            time.sleep(RENDER_SETTLE_SECONDS)
            marker, _ = render_fitted(
                work,
                stem="front-screen",
                view_name="front",
                canvas=tile_size,
                crop=crop,
                screen_marker=True,
            )
            display_rect = offset_rect(
                diff_rect(neutral, marker, padding=0),
                tile_x,
                tile_y,
            )

        for control_id in spec["controls"]:
            time.sleep(RENDER_SETTLE_SECONDS)
            highlighted, _ = render_fitted(
                work,
                stem=f"{view_name}-{control_id}",
                view_name=view_name,
                canvas=tile_size,
                crop=crop,
                highlight=control_id,
            )
            local_rect = diff_rect(neutral, highlighted)
            # The four circular face crowns are arranged diagonally. Their
            # antialias-only square bbox corners can touch by one pixel even
            # though the rendered circles do not. Drop that fringe so the
            # rectangular runtime-review crops remain strictly disjoint.
            if control_id in {
                "btn_north", "btn_east", "btn_south", "btn_west"
            }:
                local_rect = inset_rect(local_rect, 1)
            rectangles[control_id] = offset_rect(local_rect, tile_x, tile_y)
            control_views[control_id] = view_name
            highlights[control_id] = (highlighted, tile_x, tile_y)

    if neutral_atlas is None or lit_atlas is None or display_rect is None:
        raise RuntimeError("semantic atlas did not render")
    ensure_inputs(inputs)
    if committed is not None:
        same = (inputs_unchanged(committed, inputs)
                and committed.get("views") == camera_metadata)
        rectangles = canonical_rects(rectangles, committed.get("controls"), same)
        display_rect = canonical_rects(
            {"display_rect": display_rect},
            {"display_rect": committed.get("display_rect")},
            same,
        )["display_rect"]
    # Compose the lit atlas from the (possibly recorded) rects.
    for control_id, (highlighted, tile_x, tile_y) in highlights.items():
        rectangle = rectangles[control_id]
        destination = (
            rectangle["x"],
            rectangle["y"],
            rectangle["x"] + rectangle["w"],
            rectangle["y"] + rectangle["h"],
        )
        local_box = (
            destination[0] - tile_x,
            destination[1] - tile_y,
            destination[2] - tile_x,
            destination[3] - tile_y,
        )
        lit_atlas.paste(highlighted.crop(local_box), destination)
    if set(rectangles) != set(CONTROL_IDS):
        raise RuntimeError(
            "semantic view map differs from CONTROL_IDS: "
            f"mapped={sorted(rectangles)} declared={sorted(CONTROL_IDS)}"
        )
    overlaps = rectangle_overlaps(rectangles)
    if overlaps:
        rendered = ", ".join(
            f"{first}/{second}={box}"
            for first, second, box in overlaps
        )
        raise RuntimeError(f"semantic rectangles overlap: {rendered}")

    metadata = {
        "schema_version": 1,
        "device": "trimui-brick",
        "model": "TrimUI Brick",
        "model_number": "TG3040",
        "stage": "source-model-review",
        "runtime_integration": "deferred-until-owner-approval",
        "source": str(MODEL.relative_to(ROOT)),
        "source_sha256": inputs["source_sha256"],
        "renderer": str(RENDERER.relative_to(ROOT)),
        "renderer_sha256": inputs["renderer_sha256"],
        "canvas": {"w": SEMANTIC_CANVAS[0], "h": SEMANTIC_CANVAS[1]},
        "raw_canvas": {"w": RAW_SIZE[0], "h": RAW_SIZE[1]},
        "display_rect": display_rect,
        "controls": rectangles,
        "control_views": control_views,
        "views": camera_metadata,
        "atlas_composition": "pairwise-disjoint-one-control-renders",
    }
    return neutral_atlas, lit_atlas, metadata


def render_views(output: Path) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="brick-six-view-") as directory:
        work = Path(directory)
        for name in VIEW_CAMERAS:
            image, _ = render_fitted(
                work,
                stem=name,
                view_name=name,
                canvas=VIEW_CANVAS,
            )
            path = output / f"{name}.png"
            save_png(image, path)
            hashes[name] = sha256(path)
    return hashes


def write_semantic_output(output: Path) -> dict:
    """Write the semantic atlas into ``output``. A previous semantic-model.json there
    is the committed render the tie-jitter rule compares against."""
    output.mkdir(parents=True, exist_ok=True)
    recorded = output / "semantic-model.json"
    pinned = read_pinned(recorded)
    committed = None if pinned is None else json.loads(pinned[0].decode("utf-8"))
    with tempfile.TemporaryDirectory(prefix="brick-semantic-") as directory:
        neutral, lit, metadata = render_skin_set(Path(directory), committed)
        same = same_derivation(
            committed,
            inputs_unchanged(committed, metadata),
            metadata,
            SEMANTIC_DERIVATION_KEYS,
        )
        ensure_inputs(metadata)
        ensure_pinned(recorded, None if pinned is None else pinned[1])
        metadata["neutral_sha256"] = save_canonical_png(
            neutral, output / "semantic-neutral.png", same
        )
        metadata["lit_sha256"] = save_canonical_png(
            lit, output / "semantic-lit.png", same
        )
    (output / "semantic-model.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def deterministic_check() -> None:
    with tempfile.TemporaryDirectory(prefix="brick-render-check-") as directory:
        root = Path(directory)
        semantic = root / "semantic"
        names = ("semantic-neutral.png", "semantic-lit.png", "semantic-model.json")
        write_semantic_output(semantic)
        first = {name: (semantic / name).read_bytes() for name in names}
        # The second render goes over the first, so tie jitter keeps its bytes.
        write_semantic_output(semantic)
        for name in names:
            if (semantic / name).read_bytes() != first[name]:
                raise RuntimeError(f"non-deterministic semantic render: {name}")

        views_a = root / "views-a"
        views_b = root / "views-b"
        hashes_a = render_views(views_a)
        hashes_b = render_views(views_b)
        if hashes_a != hashes_b:
            changed = [
                name for name in VIEW_CAMERAS
                if hashes_a[name] != hashes_b[name]
            ]
            raise RuntimeError(
                "non-deterministic evidence views: " + ", ".join(changed)
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument(
        "--views",
        type=Path,
        help="write deterministic front/rear/top/bottom/left/right PNGs",
    )
    modes.add_argument(
        "--semantic-output",
        type=Path,
        help="write the model-stage neutral/lit semantic review atlas",
    )
    modes.add_argument(
        "--check",
        action="store_true",
        help="render every artifact twice and require byte equality",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if shutil.which(os.environ.get("OPENSCAD", "openscad")) is None:
        raise RuntimeError("OpenSCAD CLI not found")
    if args.views is not None:
        hashes = render_views(args.views)
        print(
            "views=pass "
            + " ".join(
                f"{name}={digest[:12]}"
                for name, digest in sorted(hashes.items())
            )
        )
    elif args.semantic_output is not None:
        metadata = write_semantic_output(args.semantic_output)
        print(
            "semantic=pass "
            f"controls={len(metadata['controls'])} "
            f"output={args.semantic_output}"
        )
    else:
        deterministic_check()
        print(
            f"render_check=pass views={len(VIEW_CAMERAS)} "
            f"controls={len(CONTROL_IDS)} deterministic=true"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"render.py: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
