#!/usr/bin/env python3
"""Render deterministic and selective PowKiddy X55 OpenSCAD evidence.

This source-model task deliberately does not write runtime skins.  The
semantic output is a two-view review atlas: front controls in the upper tile
and top-edge/shoulder controls in the lower tile.  Runtime descriptor and skin
integration remain a separate owner-approved follow-up.  The six orthographic
views remain the deterministic proof set; named three-quarter views are
evidence-only inspection cameras for curved-surface iteration.
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

from PIL import Image, ImageChops


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RENDERER = HERE / "render.py"
MODEL = HERE / "powkiddy-x55.scad"

RAW_SIZE = (1900, 1050)
VIEW_CANVAS = (1300, 720)
SEMANTIC_CANVAS = (1600, 1350)
PADDING = 16
DIFF_THRESHOLD = 20
RECT_PADDING = 0
RENDER_SETTLE_SECONDS = 0.12

APP_CAMERA = "106.25,47.25,400,106.25,47.25,9.5"
APP_ROTATE = 0

VIEW_CAMERAS = {
    "front": (APP_CAMERA, 0),
    "rear": ("106.25,47.25,-370,106.25,47.25,9.5", 0),
    "top": ("106.25,390,9.5,106.25,47.25,9.5", 180),
    "bottom": ("106.25,-310,9.5,106.25,47.25,9.5", 0),
    "left": ("-350,47.25,9.5,106.25,47.25,9.5", 270),
    "right": ("565,47.25,9.5,106.25,47.25,9.5", 90),
}

INSPECTION_CAMERAS = {
    "front-left": ("-245,150,285,106.25,47.25,9.5", 0),
    "front-right": ("457.5,150,285,106.25,47.25,9.5", 0),
    "rear-left": ("-245,150,-266,106.25,47.25,9.5", 0),
    "rear-right": ("457.5,150,-266,106.25,47.25,9.5", 0),
}

ALL_VIEW_CAMERAS = {**VIEW_CAMERAS, **INSPECTION_CAMERAS}

CONTROL_IDS = (
    "dpad",
    "stick_l",
    "stick_r",
    "btn_north",
    "btn_east",
    "btn_south",
    "btn_west",
    "btn_select",
    "vol_up",
    "vol_down",
    "btn_start",
    "btn_l1",
    "trig_l",
    "trig_r",
    "btn_r1",
    "btn_power",
    "btn_reset",
)

SEMANTIC_VIEWS = {
    "front": {
        "tile": (0, 0, 1600, 750),
        "controls": (
            "dpad",
            "stick_l",
            "stick_r",
            "btn_north",
            "btn_east",
            "btn_south",
            "btn_west",
            "btn_select",
            "vol_up",
            "vol_down",
            "btn_start",
        ),
    },
    "top": {
        "tile": (0, 750, 1600, 600),
        "controls": (
            "btn_l1",
            "trig_l",
            "trig_r",
            "btn_r1",
            "btn_power",
            "btn_reset",
        ),
    },
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
    colorway: str = "black",
    quality: str = "render",
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
        f'QUALITY="{quality}"',
        "-D",
        f'COLORWAY="{colorway}"',
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


def render_fitted(
    work: Path,
    *,
    stem: str,
    view_name: str,
    canvas: tuple[int, int],
    crop: tuple[int, int, int, int] | None = None,
    highlight: str = "",
    screen_marker: bool = False,
    colorway: str = "black",
    quality: str = "render",
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    camera, rotation = ALL_VIEW_CAMERAS[view_name]
    raw = work / f"{stem}-raw.png"
    run_openscad(
        raw,
        camera=camera,
        highlight=highlight,
        screen_marker=screen_marker,
        colorway=colorway,
        quality=quality,
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


def render_skin_set(work: Path) -> tuple[Image.Image, Image.Image, dict]:
    """Build the model-stage semantic review atlas."""
    work.mkdir(parents=True, exist_ok=True)
    neutral_atlas: Image.Image | None = None
    lit_atlas: Image.Image | None = None
    rectangles: dict[str, dict[str, int]] = {}
    control_views: dict[str, str] = {}
    display_rect: dict[str, int] | None = None
    camera_metadata: dict[str, dict] = {}

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
            if control_id in {
                "btn_north",
                "btn_east",
                "btn_south",
                "btn_west",
                "btn_l1",
                "trig_l",
                "trig_r",
                "btn_r1",
            }:
                local_rect = inset_rect(local_rect, 1)
            rectangle = offset_rect(local_rect, tile_x, tile_y)
            rectangles[control_id] = rectangle
            control_views[control_id] = view_name
            local_box = (
                local_rect["x"],
                local_rect["y"],
                local_rect["x"] + local_rect["w"],
                local_rect["y"] + local_rect["h"],
            )
            destination = (
                rectangle["x"],
                rectangle["y"],
                rectangle["x"] + rectangle["w"],
                rectangle["y"] + rectangle["h"],
            )
            lit_atlas.paste(highlighted.crop(local_box), destination)

    if neutral_atlas is None or lit_atlas is None or display_rect is None:
        raise RuntimeError("semantic atlas did not render")
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
        "device": "powkiddy-x55",
        "model": "PowKiddy X55",
        "model_number": "X55",
        "stage": "source-model-review",
        "runtime_integration": "deferred-until-owner-approval",
        "source": str(MODEL.relative_to(ROOT)),
        "source_sha256": sha256(MODEL),
        "renderer": str(RENDERER.relative_to(ROOT)),
        "renderer_sha256": sha256(RENDERER),
        "canvas": {"w": SEMANTIC_CANVAS[0], "h": SEMANTIC_CANVAS[1]},
        "raw_canvas": {"w": RAW_SIZE[0], "h": RAW_SIZE[1]},
        "display_rect": display_rect,
        "controls": rectangles,
        "control_views": control_views,
        "views": camera_metadata,
        "atlas_composition": "pairwise-disjoint-one-control-renders",
    }
    return neutral_atlas, lit_atlas, metadata


def render_views(
    output: Path,
    view_names: tuple[str, ...] | None = None,
    *,
    colorway: str = "black",
    quality: str = "render",
) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    selected = tuple(VIEW_CAMERAS) if view_names is None else view_names
    if not selected:
        raise RuntimeError("no evidence views selected")
    unknown = [name for name in selected if name not in ALL_VIEW_CAMERAS]
    if unknown:
        raise RuntimeError(
            "unknown evidence view(s): "
            + ", ".join(unknown)
            + "; available: "
            + ", ".join(ALL_VIEW_CAMERAS)
        )
    with tempfile.TemporaryDirectory(prefix="x55-evidence-") as directory:
        work = Path(directory)
        for name in selected:
            image, _ = render_fitted(
                work,
                stem=name,
                view_name=name,
                canvas=VIEW_CANVAS,
                colorway=colorway,
                quality=quality,
            )
            path = output / f"{name}.png"
            save_png(image, path)
            hashes[name] = sha256(path)
    return hashes


def write_semantic_output(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="x55-semantic-") as directory:
        neutral, lit, metadata = render_skin_set(Path(directory))
        save_png(neutral, output / "semantic-neutral.png")
        save_png(lit, output / "semantic-lit.png")
    metadata["neutral_sha256"] = sha256(output / "semantic-neutral.png")
    metadata["lit_sha256"] = sha256(output / "semantic-lit.png")
    (output / "semantic-model.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def deterministic_check() -> None:
    with tempfile.TemporaryDirectory(prefix="x55-render-check-") as directory:
        root = Path(directory)
        first = root / "first"
        second = root / "second"
        first.mkdir()
        second.mkdir()
        first_meta = write_semantic_output(first)
        second_meta = write_semantic_output(second)
        for name in ("semantic-neutral.png", "semantic-lit.png"):
            if (first / name).read_bytes() != (second / name).read_bytes():
                raise RuntimeError(f"non-deterministic semantic render: {name}")
        if first_meta != second_meta:
            raise RuntimeError("non-deterministic semantic metadata")

        views_a = root / "views-a"
        views_b = root / "views-b"
        hashes_a = render_views(views_a)
        hashes_b = render_views(views_b)
        if hashes_a != hashes_b:
            changed = [
                name
                for name in VIEW_CAMERAS
                if hashes_a[name] != hashes_b[name]
            ]
            raise RuntimeError(
                "non-deterministic evidence views: " + ", ".join(changed)
            )


def selected_view_names(requests: list[str] | None) -> tuple[str, ...] | None:
    if requests is None:
        return None
    selected: list[str] = []
    for request in requests:
        for name in request.split(","):
            normalized = name.strip()
            if normalized and normalized not in selected:
                selected.append(normalized)
    if not selected:
        raise RuntimeError("--only selected no evidence views")
    unknown = [name for name in selected if name not in ALL_VIEW_CAMERAS]
    if unknown:
        raise RuntimeError(
            "unknown evidence view(s): "
            + ", ".join(unknown)
            + "; available: "
            + ", ".join(ALL_VIEW_CAMERAS)
        )
    return tuple(selected)


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
    parser.add_argument(
        "--only",
        action="append",
        metavar="VIEW[,VIEW...]",
        help=(
            "with --views, render only named orthographic or three-quarter "
            "views; repeat the option or use commas"
        ),
    )
    parser.add_argument(
        "--colorway",
        choices=("black", "blue"),
        default="black",
        help="with --views, choose the physical or high-contrast shell",
    )
    parser.add_argument(
        "--quality",
        choices=("draft", "render"),
        default="render",
        help="with --views, choose fast iteration or final tessellation",
    )
    args = parser.parse_args(argv)
    if args.views is None and (
        args.only is not None
        or args.colorway != "black"
        or args.quality != "render"
    ):
        parser.error("--only, --colorway, and --quality require --views")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if shutil.which(os.environ.get("OPENSCAD", "openscad")) is None:
        raise RuntimeError("OpenSCAD CLI not found")
    if args.views is not None:
        hashes = render_views(
            args.views,
            selected_view_names(args.only),
            colorway=args.colorway,
            quality=args.quality,
        )
        print(
            f"views=pass count={len(hashes)} "
            + " ".join(
                f"{name}={digest[:12]}" for name, digest in hashes.items()
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
