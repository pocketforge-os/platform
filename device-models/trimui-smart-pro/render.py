#!/usr/bin/env python3
"""Deterministically render the TG5040 OpenSCAD model into pf-hwprobe skins.

The existing application contract is intentionally simple:

* body.png is the neutral device;
* body_lit.png is a pairwise-safe atlas composed from individual red-control
  renders with identical camera/geometry;
* [skin.parts] rectangles select one crop from body_lit at runtime.

This tool derives those rectangles from one-at-a-time semantic highlight
renders, makes the rectangles pairwise disjoint, and then builds the atlas
from those same renders. Control geometry, sprite coordinates, and atlas
contents therefore cannot silently drift or light a neighbouring control.
It never reads or modifies the owner's photographs.
"""

from __future__ import annotations

import argparse
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

from PIL import Image, ImageChops, ImageDraw, ImageOps


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RENDERER = HERE / "render.py"
MODEL = HERE / "trimui-smart-pro.scad"
DESCRIPTOR = ROOT / "devices" / "a133" / "capabilities.toml"
SKIN_DIR = ROOT / "skins" / "a133"
BODY = SKIN_DIR / "body.png"
BODY_LIT = SKIN_DIR / "body_lit.png"
METADATA = SKIN_DIR / "model-render.json"

CANVAS = (1480, 640)
RAW_SIZE = (3200, 1400)
PADDING = 12
DIFF_THRESHOLD = 24
RECT_PADDING = 1
SHOULDER_HORIZONTAL_SAFETY = 4

# The six-number camera is eye XYZ, target XYZ. OpenSCAD chooses an inverted
# up vector for this top-biased view, so the raw image is rotated 180 degrees
# before the shared crop/fit transform. That rotation is part of the committed
# camera contract, not an interactive adjustment.
APP_CAMERA = "94.175,125,330,94.175,39.885,5.5"
APP_ROTATE = 180

CONTROL_IDS = (
    "dpad",
    "stick_l",
    "stick_r",
    "btn_north",
    "btn_east",
    "btn_south",
    "btn_west",
    "btn_select",
    "btn_guide",
    "btn_start",
    "btn_l1",
    "btn_r1",
    "trig_l",
    "trig_r",
)

VIEW_CAMERAS = {
    "front": ("94.175,39.885,400,94.175,39.885,5.5", 0),
    "rear": ("94.175,39.885,-400,94.175,39.885,5.5", 0),
    "top": ("94.175,360,40,94.175,39.885,5.5", 180),
    "bottom": ("94.175,-280,40,94.175,39.885,5.5", 0),
    "left": ("-350,39.885,35,94.175,39.885,5.5", 90),
    "right": ("540,39.885,35,94.175,39.885,5.5", 270),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        str(output),
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
    )
    if completed.returncode:
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
        # A quarter-turn with ``expand=False`` leaves opaque corner wedges.
        # Those wedges look like foreground to the crop detector and shrink a
        # side elevation to a postage stamp.  Expand onto the known OpenSCAD
        # background colour so all six evidence views share one crop path.
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
    """Find non-background pixels using the stable OpenSCAD corner colour."""
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    difference = ImageChops.difference(image, background).convert("L")
    mask = difference.point(lambda value: 255 if value > threshold else 0)
    box = mask.getbbox()
    if box is None:
        raise RuntimeError("render contains no foreground pixels")
    return box


def foreground_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    """Find the foreground plus the standard full-model crop padding."""
    # OpenSCAD's antialias fringe is useful; ignore only near-zero noise.
    box = exact_foreground_bbox(image)
    left, top, right, bottom = box
    return (
        max(0, left - PADDING),
        max(0, top - PADDING),
        min(image.width, right + PADDING),
        min(image.height, bottom + PADDING),
    )


def fit_transform(
    image: Image.Image,
    crop: tuple[int, int, int, int],
    canvas: tuple[int, int] = CANVAS,
) -> Image.Image:
    cropped = image.crop(crop)
    available = (canvas[0] - 2 * PADDING, canvas[1] - 2 * PADDING)
    scale = min(available[0] / cropped.width, available[1] / cropped.height)
    target = (
        max(1, round(cropped.width * scale)),
        max(1, round(cropped.height * scale)),
    )
    resized = cropped.resize(target, Image.Resampling.LANCZOS)
    background = image.getpixel((0, 0))
    result = Image.new("RGB", canvas, background)
    offset = ((canvas[0] - target[0]) // 2, (canvas[1] - target[1]) // 2)
    result.paste(resized, offset)
    return result


def diff_rect(
    neutral: Image.Image,
    highlighted: Image.Image,
) -> dict[str, int]:
    difference = ImageChops.difference(neutral, highlighted).convert("L")
    mask = difference.point(
        lambda value: 255 if value >= DIFF_THRESHOLD else 0
    )
    box = mask.getbbox()
    if box is None:
        raise RuntimeError("semantic highlight changed zero pixels")
    left, top, right, bottom = box
    left = max(0, left - RECT_PADDING)
    top = max(0, top - RECT_PADDING)
    right = min(neutral.width, right + RECT_PADDING)
    bottom = min(neutral.height, bottom + RECT_PADDING)
    return {
        "x": left,
        "y": top,
        "w": right - left,
        "h": bottom - top,
    }


def exact_diff_rect(
    neutral: Image.Image,
    changed: Image.Image,
    threshold: int = DIFF_THRESHOLD,
) -> dict[str, int]:
    difference = ImageChops.difference(neutral, changed).convert("L")
    box = difference.point(
        lambda value: 255 if value >= threshold else 0
    ).getbbox()
    if box is None:
        raise RuntimeError("marker render changed zero pixels")
    left, top, right, bottom = box
    return {
        "x": left,
        "y": top,
        "w": right - left,
        "h": bottom - top,
    }


def descriptor_rects() -> dict[str, dict[str, int]]:
    with DESCRIPTOR.open("rb") as stream:
        data = tomllib.load(stream)
    return {
        name: {key: int(value) for key, value in rect.items()}
        for name, rect in data["skin"]["parts"].items()
    }


def descriptor_display_rect() -> dict[str, int]:
    with DESCRIPTOR.open("rb") as stream:
        data = tomllib.load(stream)
    screens = data.get("screens", [])
    if len(screens) != 1 or "display_rect" not in screens[0]:
        raise RuntimeError("a133 descriptor must have one projected display_rect")
    return {
        key: int(value)
        for key, value in screens[0]["display_rect"].items()
    }


def split_shoulder_overlaps(
    rectangles: dict[str, dict[str, int]],
) -> None:
    """Give stacked bumper/trigger sprites disjoint crop bands.

    The two physical paddles overlap in an oblique camera projection. A single
    all-lit atlas cannot isolate overlapping rectangles: pressing L1 would
    otherwise paste a red slice of L2 too. Split their shared vertical band at
    its midpoint. Each crop still covers the unmistakable exposed half of its
    paddle, and the runtime can light the two controls independently.
    """
    for bumper_id, trigger_id in (
        ("btn_l1", "trig_l"),
        ("btn_r1", "trig_r"),
    ):
        bumper = rectangles[bumper_id]
        trigger = rectangles[trigger_id]
        overlap_top = max(bumper["y"], trigger["y"])
        overlap_bottom = min(
            bumper["y"] + bumper["h"],
            trigger["y"] + trigger["h"],
        )
        if overlap_bottom <= overlap_top:
            continue
        split = round((overlap_top + overlap_bottom) / 2)
        trigger["h"] = split - trigger["y"]
        bumper_bottom = bumper["y"] + bumper["h"]
        bumper["y"] = split
        bumper["h"] = bumper_bottom - split

    # When both stacked paddles are red, OpenSCAD's shared curved seam can
    # contribute a few antialiased pixels beyond either one-at-a-time diff.
    # Keep the vertical bands disjoint, but add a horizontal safety margin so
    # the atlas union covers that seam without lighting the neighbouring
    # paddle. Four pixels is the measured maximum at the fixed 1480 px camera.
    for control_id in ("btn_l1", "btn_r1", "trig_l", "trig_r"):
        rectangle = rectangles[control_id]
        right = min(
            CANVAS[0],
            rectangle["x"] + rectangle["w"] + SHOULDER_HORIZONTAL_SAFETY,
        )
        rectangle["x"] = max(
            0,
            rectangle["x"] - SHOULDER_HORIZONTAL_SAFETY,
        )
        rectangle["w"] = right - rectangle["x"]


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


def trim_shoulder_bumpers_from_front_controls(
    rectangles: dict[str, dict[str, int]],
) -> None:
    """Keep diagonal shoulder crops from covering a front control.

    The physical L/R bumper arcs pass above the D-pad and north face button,
    but a rectangular bounding box contains the empty triangular space below
    each arc. pf-hwprobe tints the whole rectangle, so that empty space must not
    include another control. Preserve every front-control rect and trim only
    the lower edge of the bumper crop to the first protected control.
    """
    shoulder_ids = {"btn_l1", "btn_r1", "trig_l", "trig_r"}
    for bumper_id in ("btn_l1", "btn_r1"):
        bumper = rectangles[bumper_id]
        bumper_bottom = bumper["y"] + bumper["h"]
        limits = []
        for control_id, rectangle in rectangles.items():
            if control_id in shoulder_ids:
                continue
            horizontal_overlap = min(
                bumper["x"] + bumper["w"],
                rectangle["x"] + rectangle["w"],
            ) - max(bumper["x"], rectangle["x"])
            if (horizontal_overlap > 0 and
                    bumper["y"] < rectangle["y"] < bumper_bottom):
                limits.append(rectangle["y"])
        if limits:
            bumper["h"] = min(limits) - bumper["y"]
        if bumper["h"] <= 0:
            raise RuntimeError(f"shoulder crop collapsed: {bumper_id}={bumper}")


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


def render_skin_set(work: Path) -> tuple[Image.Image, Image.Image, dict]:
    raw_neutral = work / "neutral-raw.png"
    raw_screen = work / "screen-raw.png"
    run_openscad(raw_neutral, camera=APP_CAMERA)
    # OpenSCAD 2021.01 occasionally corrupts back-to-back off-screen frames
    # while the prior GL context settles. Keep the proven one-second guard.
    time.sleep(1)
    # Render the complete assembly with only the active screen recoloured.
    # Keeping the same assembly is essential: OpenSCAD --viewall would scale a
    # screen-only render to the full canvas and produce a meaningless rect.
    run_openscad(raw_screen, camera=APP_CAMERA, screen_marker=True)

    neutral_source = normalized_raw(raw_neutral, APP_ROTATE)
    screen_source = normalized_raw(raw_screen, APP_ROTATE)
    crop = foreground_bbox(neutral_source)
    neutral = fit_transform(neutral_source, crop)
    screen = fit_transform(screen_source, crop)
    display_rect = exact_diff_rect(neutral, screen)

    rectangles: dict[str, dict[str, int]] = {}
    control_frames: dict[str, Image.Image] = {}
    for control_id in CONTROL_IDS:
        time.sleep(1)
        raw_control = work / f"{control_id}-raw.png"
        run_openscad(
            raw_control,
            camera=APP_CAMERA,
            highlight=control_id,
        )
        control_source = normalized_raw(raw_control, APP_ROTATE)
        control = fit_transform(control_source, crop)
        control_frames[control_id] = control
        rectangles[control_id] = diff_rect(neutral, control)
    split_shoulder_overlaps(rectangles)
    trim_shoulder_bumpers_from_front_controls(rectangles)

    overlaps = rectangle_overlaps(rectangles)
    if overlaps:
        rendered = ", ".join(
            f"{first}/{second}={box}"
            for first, second, box in overlaps
        )
        raise RuntimeError(f"semantic rectangles overlap: {rendered}")

    # Compose the shared atlas from one-control renders only after the crops
    # are proven disjoint. This preserves the existing one-PNG runtime contract
    # without letting an all-lit crop carry pixels from a neighbouring control.
    lit = neutral.copy()
    for control_id in CONTROL_IDS:
        rectangle = rectangles[control_id]
        box = (
            rectangle["x"],
            rectangle["y"],
            rectangle["x"] + rectangle["w"],
            rectangle["y"] + rectangle["h"],
        )
        lit.paste(control_frames[control_id].crop(box), box)

    metadata = {
        "schema_version": 3,
        "device": "a133",
        "model": "TrimUI Smart Pro",
        "model_number": "TG5040",
        "source": str(MODEL.relative_to(ROOT)),
        "source_sha256": sha256(MODEL),
        "renderer": str(RENDERER.relative_to(ROOT)),
        "renderer_sha256": sha256(RENDERER),
        "canvas": {"w": CANVAS[0], "h": CANVAS[1]},
        "raw_canvas": {"w": RAW_SIZE[0], "h": RAW_SIZE[1]},
        "camera": {
            "projection": "ortho",
            "eye_target": APP_CAMERA,
            "raw_rotation_degrees": APP_ROTATE,
            "crop": list(crop),
            "padding": PADDING,
            "colorscheme": "Tomorrow",
        },
        "display_rect": display_rect,
        "controls": rectangles,
        "atlas_composition": "pairwise-disjoint-one-control-renders",
        "shoulder_crop_policy": (
            "split-overlap-midpoint+"
            f"{SHOULDER_HORIZONTAL_SAFETY}px-horizontal+front-control-trim"
        ),
    }
    return neutral, lit, metadata


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=9)


def write_outputs(neutral: Image.Image, lit: Image.Image, metadata: dict) -> None:
    save_png(neutral, BODY)
    save_png(lit, BODY_LIT)
    metadata = dict(metadata)
    metadata["body_sha256"] = sha256(BODY)
    metadata["body_lit_sha256"] = sha256(BODY_LIT)
    METADATA.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def check_outputs(neutral: Image.Image, lit: Image.Image, metadata: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="tsp-skin-check-") as directory:
        root = Path(directory)
        generated_body = root / "body.png"
        generated_lit = root / "body_lit.png"
        save_png(neutral, generated_body)
        save_png(lit, generated_lit)
        failures = []
        for committed, generated in (
            (BODY, generated_body),
            (BODY_LIT, generated_lit),
        ):
            if not committed.is_file():
                failures.append(f"missing committed asset: {committed}")
            elif committed.read_bytes() != generated.read_bytes():
                failures.append(
                    f"stale generated asset: {committed.relative_to(ROOT)}"
                )

        declared = descriptor_rects()
        derived = metadata["controls"]
        if set(declared) != set(derived):
            failures.append(
                "descriptor/model semantic ids differ: "
                f"declared={sorted(declared)} derived={sorted(derived)}"
            )
        for control_id in sorted(set(declared) & set(derived)):
            if declared[control_id] != derived[control_id]:
                failures.append(
                    f"{control_id}: descriptor={declared[control_id]} "
                    f"derived={derived[control_id]}"
                )

        declared_display = descriptor_display_rect()
        if declared_display != metadata["display_rect"]:
            failures.append(
                "display_rect: "
                f"descriptor={declared_display} "
                f"derived={metadata['display_rect']}"
            )

        for name, rectangle in {
            "display_rect": metadata["display_rect"],
            **derived,
        }.items():
            if (rectangle["w"] <= 0 or rectangle["h"] <= 0 or
                    rectangle["x"] < 0 or rectangle["y"] < 0 or
                    rectangle["x"] + rectangle["w"] > CANVAS[0] or
                    rectangle["y"] + rectangle["h"] > CANVAS[1]):
                failures.append(f"out-of-bounds derived rectangle {name}: {rectangle}")

        atlas_difference = ImageChops.difference(neutral, lit).convert("L").point(
            lambda value: 255 if value >= DIFF_THRESHOLD else 0
        )
        covered = Image.new("L", CANVAS, 0)
        covered_draw = ImageDraw.Draw(covered)
        for control_id, rectangle in derived.items():
            box = (
                rectangle["x"],
                rectangle["y"],
                rectangle["x"] + rectangle["w"],
                rectangle["y"] + rectangle["h"],
            )
            covered_draw.rectangle(box, fill=255)
            if atlas_difference.crop(box).getbbox() is None:
                failures.append(
                    f"all-lit atlas changes zero pixels inside {control_id}: {rectangle}"
                )
        uncovered = ImageChops.multiply(
            atlas_difference,
            ImageOps.invert(covered),
        )
        if uncovered.getbbox() is not None:
            failures.append(
                f"all-lit atlas has changed pixels outside semantic rectangles: "
                f"{uncovered.getbbox()}"
            )

        for first_id, second_id, overlap in rectangle_overlaps(derived):
            failures.append(
                "semantic sprite rectangles overlap: "
                f"{first_id}/{second_id}={overlap}"
            )

        expected_metadata = dict(metadata)
        expected_metadata["body_sha256"] = sha256(generated_body)
        expected_metadata["body_lit_sha256"] = sha256(generated_lit)
        if not METADATA.is_file():
            failures.append(f"missing render metadata: {METADATA.relative_to(ROOT)}")
        else:
            committed_metadata = json.loads(METADATA.read_text(encoding="utf-8"))
            if committed_metadata != expected_metadata:
                failures.append(
                    f"stale render metadata: {METADATA.relative_to(ROOT)}"
                )

        if failures:
            raise RuntimeError("\n".join(failures))


def render_views(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for index, (name, (camera, rotation)) in enumerate(VIEW_CAMERAS.items()):
        if index:
            time.sleep(1)
        with tempfile.TemporaryDirectory(prefix=f"tsp-{name}-") as directory:
            raw = Path(directory) / f"{name}-raw.png"
            run_openscad(raw, camera=camera, raw_size=(1800, 1200))
            source = normalized_raw(raw, rotation)
            crop = foreground_bbox(source)
            fitted = fit_transform(source, crop, (1800, 1200))
            save_png(fitted, output / f"{name}.png")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write",
        action="store_true",
        help="regenerate committed a133 body/body_lit assets and metadata",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="prove committed assets and descriptor rects match the model",
    )
    mode.add_argument(
        "--views",
        metavar="DIR",
        type=Path,
        help="render front/rear/top/bottom/side evidence views",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if shutil.which(os.environ.get("OPENSCAD", "openscad")) is None:
        raise RuntimeError("OpenSCAD CLI not found")
    if args.views is not None:
        render_views(args.views)
        print(f"views=pass output={args.views}")
        return 0

    with tempfile.TemporaryDirectory(prefix="tsp-skin-render-") as directory:
        neutral, lit, metadata = render_skin_set(Path(directory))
        if args.write:
            write_outputs(neutral, lit, metadata)
            print(
                "skin_write=pass "
                f"body={BODY.relative_to(ROOT)} "
                f"lit={BODY_LIT.relative_to(ROOT)}"
            )
            print("display_rect=" + json.dumps(metadata["display_rect"], sort_keys=True))
            print("derived_rects=" + json.dumps(metadata["controls"], sort_keys=True))
        else:
            check_outputs(neutral, lit, metadata)
            print("skin_check=pass assets=2 controls=14")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"render.py: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
