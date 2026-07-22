#!/usr/bin/env python3
"""Build privacy-safe owner-photo versus model comparison evidence.

The input JPEGs remain untouched and are never copied.  Every output is a newly
encoded PNG with no EXIF.  Oblique close-ups are presented side by side; the
near-overhead rear photograph also receives a normalized silhouette overlay and
an IoU regression metric.  That number is deliberately not a tolerance claim.
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
    view_crop: tuple[int, int, int, int]
    note: str


# Pixel crops select the photographed feature, not a hidden geometric fit.
# They are stable for the seven owner originals listed in the adjacent README.
EVIDENCE = (
    Evidence(
        "Rear silhouette and printing",
        "20260721_192724.jpg",
        (45, 220, 3600, 1740),
        "rear.png",
        (0, 0, 1800, 1200),
        "Near-overhead reference; phone lens distortion remains visible.",
    ),
    Evidence(
        "Left shoulder stack",
        "20260721_192738.jpg",
        (150, 300, 1950, 2450),
        "top.png",
        (0, 390, 520, 790),
        "Macro versus standard top elevation; use for topology and layer order.",
    ),
    Evidence(
        "Top edge — left/centre",
        "20260721_192757.jpg",
        (300, 90, 3880, 720),
        "top.png",
        (0, 390, 1350, 800),
        "L2/L, power, host, and the start of the volume rocker.",
    ),
    Evidence(
        "Top edge — centre/right",
        "20260721_192803.jpg",
        (0, 80, 3420, 700),
        "top.png",
        (450, 390, 1800, 800),
        "Power, host, split volume, and R/R2 ordering.",
    ),
    Evidence(
        "Front controls — right",
        "20260721_192815.jpg",
        (300, 40, 2174, 3520),
        "front.png",
        (1050, 100, 1800, 1100),
        "Face labels, right stick, Select/Start, speaker, and endcap curve.",
    ),
    Evidence(
        "Front controls — left",
        "20260721_192821.jpg",
        (0, 220, 1884, 3350),
        "front.png",
        (0, 100, 750, 1100),
        "D-pad, left stick, Menu, speaker, and endcap curve.",
    ),
    Evidence(
        "Bottom edge",
        "20260721_192845.jpg",
        (0, 35, 4000, 570),
        "bottom.png",
        (0, 390, 1800, 820),
        "FN, badge, DC, mic, TF slot, and audio jack order.",
    ),
)

CONTACT_WIDTH = 1600
ROW_HEIGHT = 390
PANEL_SIZE = (750, 300)
REAR_MASK_CANVAS = (1200, 520)


def font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def read_pixels(path: Path) -> Image.Image:
    with Image.open(path) as source:
        # Apply orientation, then detach RGB pixels.  No EXIF object is carried
        # into any output Image instance.
        return ImageOps.exif_transpose(source).convert("RGB")


def checked_crop(
    image: Image.Image,
    box: tuple[int, int, int, int],
    source: Path,
) -> Image.Image:
    left, top, right, bottom = box
    if not (0 <= left < right <= image.width and
            0 <= top < bottom <= image.height):
        raise RuntimeError(
            f"crop {box} is outside {source.name} {image.size}"
        )
    return image.crop(box)


def contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    fitted = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    panel = Image.new("RGB", size, (242, 243, 245))
    at = ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2)
    panel.paste(fitted, at)
    return panel


def make_contact(photos: Path, views: Path, output: Path) -> None:
    header = 70
    contact = Image.new(
        "RGB",
        (CONTACT_WIDTH, header + ROW_HEIGHT * len(EVIDENCE)),
        (228, 230, 233),
    )
    draw = ImageDraw.Draw(contact)
    draw.text(
        (28, 18),
        "TrimUI Smart Pro — owner photographs vs semantic OpenSCAD model",
        fill=(24, 27, 31),
        font=font(28, bold=True),
    )

    for index, evidence in enumerate(EVIDENCE):
        photo_path = photos / evidence.photo
        view_path = views / evidence.view
        if not photo_path.is_file():
            raise RuntimeError(f"missing owner photograph: {photo_path}")
        if not view_path.is_file():
            raise RuntimeError(f"missing model view: {view_path}")

        photo = checked_crop(
            read_pixels(photo_path), evidence.photo_crop, photo_path
        )
        view = checked_crop(
            read_pixels(view_path), evidence.view_crop, view_path
        )
        y = header + index * ROW_HEIGHT
        contact.paste(contain(photo, PANEL_SIZE), (20, y + 42))
        contact.paste(contain(view, PANEL_SIZE), (830, y + 42))
        draw.text(
            (22, y + 7), evidence.title,
            fill=(22, 24, 28), font=font(22, bold=True),
        )
        draw.text(
            (620, y + 12), "OWNER PHOTO",
            fill=(75, 78, 83), font=font(14, bold=True),
        )
        draw.text(
            (1430, y + 12), "MODEL",
            fill=(75, 78, 83), font=font(14, bold=True),
        )
        draw.text(
            (22, y + 350), evidence.note,
            fill=(75, 78, 83), font=font(15),
        )

    contact.save(output / "photo-vs-model.png", "PNG", compress_level=9)


def dark_photo_mask(image: Image.Image) -> Image.Image:
    # The rear unit is dark against pale graph paper.  Closing removes printed
    # holes and texture without importing a computer-vision dependency.
    mask = ImageOps.grayscale(image).point(
        lambda value: 255 if value < 118 else 0
    )
    return mask.filter(ImageFilter.MaxFilter(11)).filter(
        ImageFilter.MinFilter(11)
    )


def rendered_mask(image: Image.Image) -> Image.Image:
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    difference = ImageChops.difference(image, background).convert("L")
    return difference.point(lambda value: 255 if value > 3 else 0)


def fit_mask(
    mask: Image.Image,
    canvas: tuple[int, int],
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    box = mask.getbbox()
    if box is None:
        raise RuntimeError("silhouette mask contains no foreground")
    cropped = mask.crop(box)
    fitted = ImageOps.contain(cropped, canvas, Image.Resampling.NEAREST)
    result = Image.new("L", canvas, 0)
    at = ((canvas[0] - fitted.width) // 2, (canvas[1] - fitted.height) // 2)
    result.paste(fitted, at)
    return result, box


def fit_image_by_mask(
    image: Image.Image,
    box: tuple[int, int, int, int],
    canvas: tuple[int, int],
) -> Image.Image:
    return contain(image.crop(box), canvas)


def mask_area(mask: Image.Image) -> int:
    histogram = mask.histogram()
    return histogram[255]


def rear_silhouette(photos: Path, views: Path, output: Path) -> float:
    evidence = EVIDENCE[0]
    photo_path = photos / evidence.photo
    view_path = views / evidence.view
    photo = checked_crop(
        read_pixels(photo_path), evidence.photo_crop, photo_path
    )
    view = checked_crop(read_pixels(view_path), evidence.view_crop, view_path)

    photo_mask, photo_box = fit_mask(
        dark_photo_mask(photo), REAR_MASK_CANVAS
    )
    view_mask, view_box = fit_mask(rendered_mask(view), REAR_MASK_CANVAS)
    intersection = ImageChops.multiply(photo_mask, view_mask)
    union = ImageChops.lighter(photo_mask, view_mask)
    union_area = mask_area(union)
    iou = mask_area(intersection) / union_area if union_area else 0.0

    overlay = Image.new("RGB", REAR_MASK_CANVAS, (36, 38, 43))
    overlay.paste((235, 55, 160), mask=photo_mask)   # photo-only magenta
    overlay.paste((20, 205, 225), mask=view_mask)   # model-only cyan
    overlay.paste((245, 245, 245), mask=intersection)

    panel_size = REAR_MASK_CANVAS
    strip = Image.new("RGB", (panel_size[0], panel_size[1] * 3 + 118),
                      (228, 230, 233))
    strip.paste(fit_image_by_mask(photo, photo_box, panel_size), (0, 45))
    strip.paste(fit_image_by_mask(view, view_box, panel_size),
                (0, 45 + panel_size[1]))
    strip.paste(overlay, (0, 45 + panel_size[1] * 2))
    draw = ImageDraw.Draw(strip)
    draw.text((16, 10), "OWNER REAR (normalized)", fill=(20, 22, 25),
              font=font(21, bold=True))
    draw.text((16, 45 + panel_size[1] - 30), "MODEL REAR (normalized)",
              fill=(20, 22, 25), font=font(21, bold=True))
    draw.text((16, 45 + panel_size[1] * 2 - 30),
              "SILHOUETTE: magenta=photo, cyan=model, white=overlap",
              fill=(20, 22, 25), font=font(21, bold=True))
    draw.text(
        (16, 45 + panel_size[1] * 3 + 14),
        f"normalized IoU={iou:.4f}; perspective/lens regression aid only",
        fill=(52, 55, 60), font=font(19),
    )
    strip.save(output / "rear-silhouette.png", "PNG", compress_level=9)

    metrics = {
        "schema_version": 1,
        "reference": evidence.photo,
        "reference_crop": list(evidence.photo_crop),
        "model_view": evidence.view,
        "photo_foreground_box_within_crop": list(photo_box),
        "model_foreground_box_within_view": list(view_box),
        "normalized_canvas": {
            "w": REAR_MASK_CANVAS[0], "h": REAR_MASK_CANVAS[1]
        },
        "silhouette_iou": round(iou, 6),
        "interpretation": (
            "Regression aid only; source is a wide-angle phone photograph, "
            "not a coplanar calibrated tolerance image."
        ),
        "privacy": "outputs are re-encoded PNG pixels with no source EXIF",
    }
    (output / "comparison-metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return iou


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    make_contact(args.photos, args.views, args.output)
    iou = rear_silhouette(args.photos, args.views, args.output)
    print(
        f"comparison=pass rows={len(EVIDENCE)} "
        f"rear_silhouette_iou={iou:.4f} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, RuntimeError) as error:
        print(f"compare.py: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
