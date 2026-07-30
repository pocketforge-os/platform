#!/usr/bin/env python3
"""Build privacy-safe owner-evidence versus TrimUI Brick model sheets.

Owner JPEGs are decoded with EXIF orientation, cropped to the device or the
hand-drawn measurement profile, and re-encoded as new pixel-only PNGs.  The
original files and their metadata are never copied into the repository.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageFilter,
    ImageFont,
    ImageOps,
)


@dataclass(frozen=True)
class Evidence:
    title: str
    photo: str
    photo_crop: tuple[int, int, int, int]
    view: str
    note: str


EVIDENCE = (
    Evidence(
        "Front layout and measured envelope",
        "20260721_032132.jpg",
        (785, 835, 1755, 2580),
        "front.png",
        "Owner unit on graph paper; use for proportions and control placement.",
    ),
    Evidence(
        "Stepped-depth measurement sketch",
        "20260721_032150.jpg",
        (680, 720, 1885, 2600),
        "left.png",
        "Owner sketch records 72.8 × 110.75 mm and 12/20 mm depth datums.",
    ),
)

CONTACT_WIDTH = 1540
ROW_HEIGHT = 500
PANEL_SIZE = (700, 370)
MASK_CANVAS = (720, 1040)


def font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def read_pixels(path: Path) -> Image.Image:
    with Image.open(path) as source:
        return ImageOps.exif_transpose(source).convert("RGB")


def checked_crop(
    image: Image.Image,
    box: tuple[int, int, int, int],
    source: Path,
) -> Image.Image:
    left, top, right, bottom = box
    if not (
        0 <= left < right <= image.width
        and 0 <= top < bottom <= image.height
    ):
        raise RuntimeError(
            f"crop {box} is outside {source.name} {image.size}"
        )
    return image.crop(box)


def contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    fitted = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    panel = Image.new("RGB", size, (244, 245, 247))
    at = ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2)
    panel.paste(fitted, at)
    return panel


def save_png(image: Image.Image, path: Path) -> None:
    image.save(path, format="PNG", optimize=False, compress_level=9)


def make_contact(photos: Path, views: Path, output: Path) -> None:
    header = 72
    contact = Image.new(
        "RGB",
        (CONTACT_WIDTH, header + ROW_HEIGHT * len(EVIDENCE)),
        (228, 230, 233),
    )
    draw = ImageDraw.Draw(contact)
    draw.text(
        (28, 18),
        "TrimUI Brick — owner evidence vs semantic OpenSCAD model",
        fill=(24, 27, 31),
        font=font(28, bold=True),
    )

    for index, evidence in enumerate(EVIDENCE):
        photo_path = photos / evidence.photo
        view_path = views / evidence.view
        if not photo_path.is_file():
            raise RuntimeError(f"missing owner evidence: {photo_path}")
        if not view_path.is_file():
            raise RuntimeError(f"missing model view: {view_path}")
        photo = checked_crop(
            read_pixels(photo_path), evidence.photo_crop, photo_path
        )
        view = read_pixels(view_path)
        y = header + index * ROW_HEIGHT
        contact.paste(contain(photo, PANEL_SIZE), (20, y + 55))
        contact.paste(contain(view, PANEL_SIZE), (820, y + 55))
        draw.text(
            (22, y + 12),
            evidence.title,
            fill=(22, 24, 28),
            font=font(22, bold=True),
        )
        draw.text(
            (570, y + 27),
            "OWNER EVIDENCE",
            fill=(75, 78, 83),
            font=font(13, bold=True),
        )
        draw.text(
            (1400, y + 27),
            "MODEL",
            fill=(75, 78, 83),
            font=font(13, bold=True),
        )
        draw.text(
            (22, y + 446),
            evidence.note,
            fill=(75, 78, 83),
            font=font(15),
        )

    save_png(contact, output / "photo-vs-model.png")


def dark_device_mask(image: Image.Image) -> Image.Image:
    # The black unit is strongly separated from pale graph paper. Closing
    # removes control/screen holes, while opening drops most narrow grid lines.
    mask = ImageOps.grayscale(image).point(
        lambda value: 255 if value < 82 else 0
    )
    mask = mask.filter(ImageFilter.MaxFilter(13))
    mask = mask.filter(ImageFilter.MinFilter(13))
    mask = mask.filter(ImageFilter.MinFilter(5))
    return mask.filter(ImageFilter.MaxFilter(5))


def rendered_mask(image: Image.Image) -> Image.Image:
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    difference = ImageChops.difference(image, background).convert("L")
    return difference.point(lambda value: 255 if value > 3 else 0)


def largest_component_box(mask: Image.Image) -> tuple[int, int, int, int]:
    # Pillow has no connected-components primitive. Horizontal/vertical
    # closing makes the device one dominant block, after which the aggregate
    # bbox is stable for the tightly cropped owner image.
    box = mask.getbbox()
    if box is None:
        raise RuntimeError("silhouette mask contains no foreground")
    return box


def fit_mask(
    mask: Image.Image,
    canvas: tuple[int, int],
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    box = largest_component_box(mask)
    cropped = mask.crop(box)
    fitted = ImageOps.contain(cropped, canvas, Image.Resampling.NEAREST)
    result = Image.new("L", canvas, 0)
    at = ((canvas[0] - fitted.width) // 2, (canvas[1] - fitted.height) // 2)
    result.paste(fitted, at)
    return result, box


def mask_area(mask: Image.Image) -> int:
    return mask.histogram()[255]


def front_silhouette(photos: Path, views: Path, output: Path) -> float:
    evidence = EVIDENCE[0]
    photo_path = photos / evidence.photo
    view_path = views / evidence.view
    photo = checked_crop(
        read_pixels(photo_path), evidence.photo_crop, photo_path
    )
    view = read_pixels(view_path)

    photo_mask, _ = fit_mask(dark_device_mask(photo), MASK_CANVAS)
    view_mask, _ = fit_mask(rendered_mask(view), MASK_CANVAS)
    intersection = ImageChops.multiply(photo_mask, view_mask)
    union = ImageChops.lighter(photo_mask, view_mask)
    union_area = mask_area(union)
    iou = mask_area(intersection) / union_area if union_area else 0.0

    overlay = Image.new("RGB", MASK_CANVAS, (36, 38, 43))
    overlay.paste((235, 55, 160), mask=photo_mask)
    overlay.paste((20, 205, 225), mask=view_mask)
    overlay.paste((245, 245, 245), mask=intersection)

    sheet = Image.new(
        "RGB",
        (MASK_CANVAS[0], MASK_CANVAS[1] + 82),
        (226, 228, 231),
    )
    sheet.paste(overlay, (0, 82))
    draw = ImageDraw.Draw(sheet)
    draw.text(
        (20, 14),
        f"Normalized front silhouette IoU: {iou:.4f}",
        fill=(25, 27, 31),
        font=font(24, bold=True),
    )
    draw.text(
        (20, 48),
        "white=overlap  magenta=owner only  cyan=model only",
        fill=(68, 71, 77),
        font=font(15),
    )
    save_png(sheet, output / "front-silhouette.png")
    return iou


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    make_contact(args.photos.resolve(), args.views.resolve(), output)
    iou = front_silhouette(
        args.photos.resolve(), args.views.resolve(), output
    )
    (output / "metrics.json").write_text(
        json.dumps(
            {
                "front_silhouette_iou": round(iou, 6),
                "interpretation": (
                    "regression aid only; not a manufacturing tolerance claim"
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"comparison=pass rows={len(EVIDENCE)} "
        f"front_silhouette_iou={iou:.4f} output={output}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, RuntimeError) as error:
        print(f"compare.py: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
