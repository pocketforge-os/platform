#!/usr/bin/env python3
"""skins/generate-bezel.py — render a device's clickable-skin bezel FROM its descriptor.

Original schematic art (NOT a copyrighted vendor render): a clean landscape-handheld
chassis with every control drawn at exactly the rect declared in
devices/<id>/capabilities.toml [skin.parts], plus the screen at display_rect. Because the
geometry is read from the descriptor, body.png and the rects CANNOT drift. The layout
proportions are traced from the device's FCC external-photo exhibit (public record).

Produces, per device:
  skins/<id>/body.png       — the unlit chassis
  skins/<id>/body_lit.png   — same, every control in its lit (pressed) colour

The app/simulator lights control X by compositing body_lit cropped to parts[X].rect over
body. Real photographic bezel art can replace body.png later without touching the rects.

Usage:  python3 skins/generate-bezel.py <id> [<id> ...]   (or --all)
Requires Pillow.
"""
import sys, os, tomllib
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEVICES = os.path.join(ROOT, "devices")
BEZEL = (1480, 640)                      # skin canvas (landscape handheld); rects fit within
BODY_BG = (232, 232, 234)                # off-white chassis
EDGE = (120, 120, 126)
SCREEN_FILL = (18, 18, 24)
NEUTRAL = (158, 158, 165)
LIT = (214, 64, 64)


def _rect(r):
    return [r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]]


def draw_device(data, lit):
    img = Image.new("RGB", BEZEL, BODY_BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, BEZEL[0] - 7, BEZEL[1] - 7], radius=70, outline=EDGE, width=5)

    for s in data.get("screens", []):
        dr = s.get("display_rect")
        if dr:
            d.rectangle(_rect(dr), fill=SCREEN_FILL, outline=(70, 70, 78), width=3)
            rc = s.get("render_canvas", {})
            d.text((dr["x"] + 12, dr["y"] + 10),
                   f"SCREEN  {rc.get('w','?')}x{rc.get('h','?')}  (present {s.get('present','?')}, {s.get('rotation','?')})",
                   fill=(118, 118, 130))

    # printed glyph per skin part (e.g. face buttons carry label "A"/"B"/"X"/"Y")
    label_for = {inp["skin_part"]: inp.get("label")
                 for inp in data.get("inputs", []) if inp.get("skin_part")}
    fill = LIT if lit else NEUTRAL
    for name, r in data.get("skin", {}).get("parts", {}).items():
        box = _rect(r)
        if name.startswith("stick"):
            d.ellipse(box, fill=fill, outline=(58, 58, 64), width=3)
            d.ellipse([box[0] + 8, box[1] + 8, box[2] - 8, box[3] - 8], outline=(58, 58, 64), width=2)
        elif name == "dpad":
            cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
            t = r["w"] // 3
            d.rectangle([box[0], cy - t // 2, box[2], cy + t // 2], fill=fill, outline=(58, 58, 64), width=2)
            d.rectangle([cx - t // 2, box[1], cx + t // 2, box[3]], fill=fill, outline=(58, 58, 64), width=2)
        else:
            d.rounded_rectangle(box, radius=9, fill=fill, outline=(58, 58, 64), width=2)
        glyph = label_for.get(name)
        if glyph:  # draw the printed glyph centered inside the control
            tb = d.textbbox((0, 0), glyph)
            cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
            d.text((cx - (tb[2] - tb[0]) // 2, cy - (tb[3] - tb[1]) // 2), glyph, fill=(20, 20, 24))
        else:  # otherwise label the part by name, above (or below if at the top edge)
            ly = r["y"] - 13 if r["y"] >= 14 else r["y"] + r["h"] + 2
            d.text((r["x"], ly), name, fill=(70, 70, 78))
    return img


def generate(dev_id):
    cpath = os.path.join(DEVICES, dev_id, "capabilities.toml")
    with open(cpath, "rb") as f:
        data = tomllib.load(f)
    outdir = os.path.join(ROOT, "skins", dev_id)
    os.makedirs(outdir, exist_ok=True)
    draw_device(data, lit=False).save(os.path.join(outdir, "body.png"))
    draw_device(data, lit=True).save(os.path.join(outdir, "body_lit.png"))
    print(f"wrote skins/{dev_id}/body.png + body_lit.png  ({BEZEL[0]}x{BEZEL[1]})")


def main(argv):
    if not argv:
        print(__doc__); return 2
    if argv[0] == "--all":
        argv = sorted(d for d in os.listdir(DEVICES)
                      if os.path.isfile(os.path.join(DEVICES, d, "capabilities.toml")))
    for dev_id in argv:
        generate(dev_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
