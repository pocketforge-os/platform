#!/usr/bin/env python3
"""Render six orthographic review views of a committed device glb.

    python3 device-models/render_glb_views.py skins/a133/model.glb

Writes ``skins/<id>/views/{front,back,left,right,top,bottom}.png`` next to the
glb. The views are rendered from the glb itself (not the .scad), so they show
exactly what the simulator will load: node placement, normals, materials and
the screen quad. They are what the owner reviews, so they move in lockstep
with the glb: after writing them this records, in ``skins/<id>/model-glb.json``,
a ``views`` block ``{glb_sha256, files: {<view>: sha256}}``, and
``check-skin-drift.py`` fails when a committed view or the glb no longer
matches it. ``device-models/regen.sh <slug>`` runs this after the export.

A small software z-buffer rasteriser (numpy + Pillow, local only; CI never
runs this): per-vertex normals interpolated per pixel, a key light plus
headlight and ambient, 2x supersampling. Every PNG must stay under 300 KB.
The recording half (``record_views``) is standard library only, so the
hermetic tests exercise it without numpy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError as error:  # record_views needs neither; rendering does
    np = Image = None
    RENDER_IMPORT_ERROR = error
else:
    RENDER_IMPORT_ERROR = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_gltf  # noqa: E402

MAX_BYTES = 300 * 1024
LONG_EDGE = 1100
SUPERSAMPLE = 2
MARGIN = 0.06
BACKGROUND = (236, 237, 240)
EXPOSURE = 3.2

# name -> (view direction from the camera into the scene, image up vector)
VIEWS = {
    "front": ((0, 0, -1), (0, 1, 0)),
    "back": ((0, 0, 1), (0, 1, 0)),
    "left": ((1, 0, 0), (0, 1, 0)),
    "right": ((-1, 0, 0), (0, 1, 0)),
    "top": ((0, -1, 0), (0, 0, -1)),
    "bottom": ((0, 1, 0), (0, 0, 1)),
}


def load_triangles(path: Path):
    """World-space triangles, per-corner normals and per-triangle linear colour."""
    doc, binary = export_gltf.read_glb(path.read_bytes())
    nodes = doc["nodes"]
    positions, normals, colours = [], [], []

    def visit(index: int, offset: np.ndarray) -> None:
        node = nodes[index]
        if "rotation" in node or "scale" in node or "matrix" in node:
            raise SystemExit(f"{path}: node {node.get('name')} has a non-translation transform")
        offset = offset + np.array(node.get("translation", [0, 0, 0]), dtype=np.float64)
        if "mesh" in node:
            for primitive in doc["meshes"][node["mesh"]]["primitives"]:
                attributes = primitive["attributes"]
                pos = np.array(export_gltf.read_accessor(doc, binary, attributes["POSITION"]),
                               dtype=np.float64).reshape(-1, 3) + offset
                nrm = np.array(export_gltf.read_accessor(doc, binary, attributes["NORMAL"]),
                               dtype=np.float64).reshape(-1, 3)
                idx = np.array(export_gltf.read_accessor(doc, binary, primitive["indices"]),
                               dtype=np.int64).reshape(-1, 3)
                factor = doc["materials"][primitive["material"]]["pbrMetallicRoughness"][
                    "baseColorFactor"][:3]
                positions.append(pos[idx])
                normals.append(nrm[idx])
                colours.append(np.tile(np.array(factor), (len(idx), 1)))
        for child in node.get("children", []):
            visit(child, offset)

    for root in doc["scenes"][doc.get("scene", 0)]["nodes"]:
        visit(root, np.zeros(3))
    return np.concatenate(positions), np.concatenate(normals), np.concatenate(colours)


def linear_to_srgb(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, 0.0, 1.0)
    return np.where(values <= 0.0031308, values * 12.92,
                    1.055 * np.power(values, 1 / 2.4) - 0.055)


def render(tris, nrms, cols, direction, up) -> Image.Image:
    d = np.array(direction, dtype=np.float64)
    u = np.array(up, dtype=np.float64)
    r = np.cross(d, u)
    sx, sy, depth = tris @ r, tris @ u, tris @ d
    lo_x, hi_x, lo_y, hi_y = sx.min(), sx.max(), sy.min(), sy.max()
    span = max(hi_x - lo_x, hi_y - lo_y)
    scale = LONG_EDGE * SUPERSAMPLE * (1 - 2 * MARGIN) / span
    width = int(round((hi_x - lo_x) * scale + 2 * MARGIN * LONG_EDGE * SUPERSAMPLE))
    height = int(round((hi_y - lo_y) * scale + 2 * MARGIN * LONG_EDGE * SUPERSAMPLE))
    pad = MARGIN * LONG_EDGE * SUPERSAMPLE
    px = (sx - lo_x) * scale + pad
    py = (hi_y - sy) * scale + pad

    zbuf = np.full((height, width), np.inf)
    image = np.empty((height, width, 3))
    image[:] = np.array(BACKGROUND) / 255.0
    image = image ** 2.2  # work in linear light
    key = -d + np.array([-0.45, 0.6, 0.0]) + np.cross(d, r) * 0.0
    key /= np.linalg.norm(key)
    head = -d

    for t in range(len(tris)):
        x, y, z = px[t], py[t], depth[t]
        x0, x1 = int(max(np.floor(x.min()), 0)), int(min(np.ceil(x.max()), width - 1))
        y0, y1 = int(max(np.floor(y.min()), 0)), int(min(np.ceil(y.max()), height - 1))
        if x0 > x1 or y0 > y1:
            continue
        area = (x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0])
        if abs(area) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((x[1] - gx) * (y[2] - gy) - (x[2] - gx) * (y[1] - gy)) / area
        w1 = ((x[2] - gx) * (y[0] - gy) - (x[0] - gx) * (y[2] - gy)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        zz = w0 * z[0] + w1 * z[1] + w2 * z[2]
        window = zbuf[y0:y1 + 1, x0:x1 + 1]
        draw = inside & (zz < window)
        if not draw.any():
            continue
        n = (w0[..., None] * nrms[t, 0] + w1[..., None] * nrms[t, 1]
             + w2[..., None] * nrms[t, 2])[draw]
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        # Shade back-facing samples as if facing the camera (thin parts).
        n = np.where((n @ d)[:, None] > 0, -n, n)
        light = 0.22 + 0.55 * np.clip(n @ key, 0, None) + 0.35 * np.clip(n @ head, 0, None)
        spec = 0.10 * np.clip(n @ ((key + head) / np.linalg.norm(key + head)), 0, None) ** 24
        window[draw] = zz[draw]
        image[y0:y1 + 1, x0:x1 + 1][draw] = (
            cols[t] * light[:, None] * EXPOSURE + spec[:, None]
        )

    pixels = (linear_to_srgb(image) * 255 + 0.5).astype(np.uint8)
    result = Image.fromarray(pixels, "RGB")
    return result.resize((width // SUPERSAMPLE, height // SUPERSAMPLE), Image.LANCZOS)


def save_under_limit(image: Image.Image, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        image.save(path, format="PNG", optimize=True)
        size = path.stat().st_size
        if size <= MAX_BYTES:
            return size
        image = image.resize((int(image.width * 0.85), int(image.height * 0.85)),
                             Image.LANCZOS)


def record_views(glb: Path) -> dict:
    """Record the glb and the six committed view PNGs in model-glb.json["views"]."""
    meta_path = glb.parent / export_gltf.METADATA_NAME
    if not meta_path.is_file():
        raise SystemExit(f"{glb}: no {meta_path.name} beside it (export with export_gltf.py --write)")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["views"] = {
        "glb_sha256": export_gltf.sha256_file(glb),
        "files": {
            name: export_gltf.sha256_file(glb.parent / "views" / f"{name}.png")
            for name in VIEWS
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta["views"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("glb", nargs="+", type=Path)
    args = parser.parse_args(argv)
    if RENDER_IMPORT_ERROR is not None:
        raise SystemExit(f"render_glb_views.py needs numpy and Pillow: {RENDER_IMPORT_ERROR}")
    for glb in args.glb:
        tris, nrms, cols = load_triangles(glb)
        for name, (direction, up) in VIEWS.items():
            out = glb.parent / "views" / f"{name}.png"
            size = save_under_limit(render(tris, nrms, cols, direction, up), out)
            print(f"wrote {out} bytes={size}")
        views = record_views(glb)
        print(f"recorded {glb.parent / export_gltf.METADATA_NAME} views "
              f"glb_sha256={views['glb_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
