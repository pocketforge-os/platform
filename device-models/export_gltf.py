#!/usr/bin/env python3
"""Export a semantic OpenSCAD device model to a committed glTF 2.0 binary (D4).

The .scad stays the source of truth; this script turns it into
``skins/<id>/model.glb`` for the 3D simulator (tsp-h5ed.46) and records the
export in ``skins/<id>/model-glb.json`` beside the rendered skin.

    python3 device-models/export_gltf.py --model trimui-smart-pro --write
    python3 device-models/export_gltf.py --check

``--write`` needs OpenSCAD and runs locally. ``--check`` needs nothing beyond
the Python 3.11+ standard library: it recomputes the sha256 of every committed
glb, compares it with ``model-glb.json``, re-reads the glb and asserts the
structural contract below, and prints the triangle count per device. CI runs it
together with ``check-skin-drift.py`` (cross-file lockstep) and the pinned
Khronos validator (``gltf_validate.py``).

GLB CONTRACT (pf-semantic-v1)
* One scene root node ``body`` (the non-interactive shell). Every other node
  is a descendant of ``body``.
* One node per semantic control, named by the control id (== the .scad
  ``CONTROL_IDS`` == the descriptor ``[skin.parts]`` keys == ``skin_part``).
  Its translation is the control's pivot: the centre of its footprint at its
  lowest Z, so a press is a -Z translation and a stick tilt a rotation about
  the node origin. ``extras.inputs`` lists the descriptor inputs bound to it.
* One screen quad per panel, named by the descriptor ``screens[].node``
  (default ``screen_main``): two triangles over the active area, 0.05 mm in
  front of it, ``TEXCOORD_0`` 0..1 (u left->right, v top->bottom of the
  presented image, glTF top-left origin) and ``extras.panel_rotation_deg``
  (descriptor ``rotation``: none/cw90/cw180/cw270 -> 0/90/180/270).
* Reserved names: ``body``, ``screen_*``, ``pivot_*``. A future articulated
  model puts each moving assembly under an empty ``pivot_<joint id>`` node
  (D4/D6; joint semantics live in the descriptor ``[[joints]]``). Any other
  node name is a control and must be a declared control id.
* Frame pf-mm-v1 (X left->right, Y bottom->top, Z rear->front, origin as in
  the .scad), scaled to glTF metres. Smooth normals with a 30 degree crease;
  zero-area triangles are dropped. One material per part class (OpenSCAD
  2021.01 STL carries no colour): body/control plastic and screen glass,
  base colours from the .scad palette tokens.
* At most TRIANGLE_BUDGET triangles per device.

The writer is deterministic (sorted JSON, no timestamps), so the same STL input
always yields the same bytes. OpenSCAD output is cached under
``device-models/.cache/`` keyed by the .scad bytes, the defines and the
OpenSCAD version, so exporter-only changes re-export in seconds.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
EXPORTER_REL = "device-models/export_gltf.py"
METADATA_NAME = "model-glb.json"
GLB_NAME = "model.glb"

TRIANGLE_BUDGET = 150_000
BODY_NODE = "body"
SCREEN_PREFIX = "screen_"
PIVOT_PREFIX = "pivot_"
DEFAULT_SCREEN_NODE = "screen_main"
MM_TO_M = 0.001
CREASE_DEG = 30.0
SCREEN_LIFT_MM = 0.05
DEGENERATE_AREA2 = 1e-9  # |cross| in mm^2; below this a triangle has no normal
ROTATION_DEG = {"none": 0, "cw90": 90, "cw180": 180, "cw270": 270}
UV_CONVENTION = (
    "u left->right, v top->bottom of the presented image (glTF top-left origin); "
    "rotate the panel scanout by panel_rotation_deg before mapping"
)

# Part class -> (palette token in the .scad, roughness). One neutral material
# per class; the owner ignores colour variants (decision record section 0.6).
MATERIALS = {
    "body": ("shell_rear_color", "plastic", 0.6),
    "control": ("control_color", "plastic", 0.5),
    "screen": ("glass_color", "glass", 0.05),
}

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963
FLOAT = 5126
UNSIGNED_SHORT = 5123
UNSIGNED_INT = 5125
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}
COMPONENT_FORMAT = {FLOAT: "f", UNSIGNED_SHORT: "H", UNSIGNED_INT: "I"}


class ExportError(Exception):
    """The model cannot be exported as asked (names, geometry, OpenSCAD)."""


class GlbError(Exception):
    """The bytes are not a glb this tool can read."""


@dataclass(frozen=True)
class Model:
    slug: str                 # device-models/<slug>/<slug>.scad
    skin: str                 # skins/<skin>/
    descriptor: str | None    # repo-relative capabilities.toml, None = model-only
    panel_rotation_deg: int | None = None  # model-only screens (no descriptor)


MODELS = {
    "trimui-smart-pro": Model("trimui-smart-pro", "a133", "devices/a133/capabilities.toml"),
    "trimui-smart-pro-s": Model("trimui-smart-pro-s", "a523", "devices/a523/capabilities.toml"),
    # Brick: descriptor on HOLD (owner 2026-10-09), model-only; panel rotation
    # is unknown without a descriptor, so the quad carries 0.
    "trimui-brick": Model("trimui-brick", "trimui-brick", None, panel_rotation_deg=0),
}


@dataclass
class Resolved:
    root: Path
    model: Model
    scad_rel: str
    control_ids: list[str]
    screens: list[dict]
    inputs_by_part: dict[str, list[dict]]
    palette: dict[str, list[float]]


@dataclass
class Mesh:
    positions: list[float] = field(default_factory=list)  # metres, node-local
    normals: list[float] = field(default_factory=list)
    uvs: list[float] | None = None
    indices: list[int] = field(default_factory=list)


@dataclass
class Summary:
    names: list[str]
    roots: list[str]
    parents: dict[str, str | None]
    has_mesh: dict[str, bool]
    controls: list[str]
    screens: dict[str, dict]
    pivots: list[str]
    triangles: int


# ---- small helpers ---------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def srgb_to_linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def is_reserved(name: str) -> bool:
    return (name == BODY_NODE or name.startswith(SCREEN_PREFIX)
            or name.startswith(PIVOT_PREFIX))


# ---- model resolution (names, screens, palette) -----------------------------

def scad_control_ids(scad: Path) -> list[str]:
    text = scad.read_text(encoding="utf-8")
    match = re.search(r"^CONTROL_IDS\s*=\s*\[(.*?)\];", text, re.S | re.M)
    if not match:
        raise ExportError(f"{scad}: no CONTROL_IDS = [...] list")
    ids = re.findall(r'"([^"]+)"', match.group(1))
    if not ids or len(set(ids)) != len(ids):
        raise ExportError(f"{scad}: CONTROL_IDS must be non-empty and unique: {ids}")
    reserved = [i for i in ids if is_reserved(i)]
    if reserved:
        raise ExportError(f"{scad}: control ids use reserved node names: {reserved}")
    return ids


def scad_palette(scad: Path) -> dict[str, list[float]]:
    text = scad.read_text(encoding="utf-8")
    palette = {}
    for token, _, _ in MATERIALS.values():
        match = re.search(
            rf"^{token}\s*=\s*\[([^\]]+)\];", text, re.M
        )
        if not match:
            raise ExportError(f"{scad}: palette token {token} not found")
        palette[token] = [float(v) for v in match.group(1).split(",")]
    return palette


def descriptor_screens(descriptor: dict) -> list[dict]:
    """The screen quads a descriptor asks for: node, id, panel rotation."""
    screens = descriptor.get("screens", [])
    if len(screens) != 1:
        raise ExportError(
            f"descriptor has {len(screens)} screens; the exporter's PART=screen "
            "probe is single-panel (extend it with per-panel probes first)"
        )
    screen = screens[0]
    rotation = screen.get("rotation", "none")
    if rotation not in ROTATION_DEG:
        raise ExportError(f"unknown screen rotation {rotation!r}")
    return [{
        "node": screen.get("node", DEFAULT_SCREEN_NODE),
        "screen_id": screen.get("id", screen.get("role", "main")),
        "panel_rotation_deg": ROTATION_DEG[rotation],
    }]


def part_name_failures(control_ids, skin_parts) -> list[str]:
    extra = sorted(set(control_ids) - set(skin_parts))
    missing = sorted(set(skin_parts) - set(control_ids))
    failures = []
    if extra:
        failures.append(f"model control ids not in descriptor [skin.parts]: {extra}")
    if missing:
        failures.append(f"descriptor [skin.parts] ids the model lacks: {missing}")
    return failures


def resolve_model(root: Path, model: Model) -> Resolved:
    scad_rel = f"device-models/{model.slug}/{model.slug}.scad"
    scad = root / scad_rel
    if not scad.is_file():
        raise ExportError(f"missing model source {scad_rel}")
    control_ids = scad_control_ids(scad)
    inputs_by_part: dict[str, list[dict]] = {}
    if model.descriptor:
        path = root / model.descriptor
        if not path.is_file():
            raise ExportError(f"missing descriptor {model.descriptor}")
        with path.open("rb") as stream:
            descriptor = tomllib.load(stream)
        failures = part_name_failures(
            control_ids, descriptor.get("skin", {}).get("parts", {})
        )
        if failures:
            raise ExportError(f"{model.slug}: refusing to export: " + "; ".join(failures))
        screens = descriptor_screens(descriptor)
        for row in descriptor.get("inputs", []):
            part = row.get("skin_part")
            if part:
                inputs_by_part.setdefault(part, []).append({
                    key: row[key] for key in ("id", "kind", "ev_type", "code")
                    if key in row
                })
    else:
        if model.panel_rotation_deg not in ROTATION_DEG.values():
            raise ExportError(f"{model.slug}: model-only export needs panel_rotation_deg")
        screens = [{
            "node": DEFAULT_SCREEN_NODE,
            "screen_id": "main",
            "panel_rotation_deg": model.panel_rotation_deg,
        }]
    return Resolved(root, model, scad_rel, control_ids, screens, inputs_by_part,
                    scad_palette(scad))


# ---- geometry -----------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def bbox(triangles) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    points = [p for tri in triangles for p in tri]
    if not points:
        raise ExportError("empty mesh")
    return (tuple(min(p[i] for p in points) for i in range(3)),
            tuple(max(p[i] for p in points) for i in range(3)))


def smooth_mesh(triangles, origin) -> Mesh:
    """Index a triangle soup (mm) with angle-weighted smooth normals.

    Faces sharing an exact vertex position are averaged (area-weighted) when
    their normals are within CREASE_DEG; sharper edges split the vertex.
    Zero-area triangles are dropped (they have no normal).
    """
    cos_crease = math.cos(math.radians(CREASE_DEG))
    faces = []
    for tri in triangles:
        corners = tuple(tuple(float(v) for v in point) for point in tri)
        normal = _cross(_sub(corners[1], corners[0]), _sub(corners[2], corners[0]))
        length = math.sqrt(normal[0] ** 2 + normal[1] ** 2 + normal[2] ** 2)
        if length <= DEGENERATE_AREA2 or len(set(corners)) != 3:
            continue
        faces.append((corners, (normal[0] / length, normal[1] / length,
                                normal[2] / length), length))
    by_position: dict[tuple, list[int]] = defaultdict(list)
    for index, (corners, _, _) in enumerate(faces):
        for point in corners:
            by_position[point].append(index)

    mesh = Mesh()
    seen: dict[tuple, int] = {}
    for corners, face_normal, _ in faces:
        for point in corners:
            sx = sy = sz = 0.0
            for other in by_position[point]:
                normal, weight = faces[other][1], faces[other][2]
                if (normal[0] * face_normal[0] + normal[1] * face_normal[1]
                        + normal[2] * face_normal[2]) >= cos_crease:
                    sx += normal[0] * weight
                    sy += normal[1] * weight
                    sz += normal[2] * weight
            length = math.sqrt(sx * sx + sy * sy + sz * sz)
            vertex_normal = ((sx / length, sy / length, sz / length)
                             if length > 1e-12 else face_normal)
            vertex_normal = tuple(f32(v) for v in vertex_normal)
            key = (point, vertex_normal)
            index = seen.get(key)
            if index is None:
                index = len(seen)
                seen[key] = index
                mesh.positions.extend(
                    (point[i] - origin[i]) * MM_TO_M for i in range(3)
                )
                mesh.normals.extend(vertex_normal)
            mesh.indices.append(index)
    if not mesh.indices:
        raise ExportError("mesh has no non-degenerate triangles")
    return mesh


def screen_quad(screen_bbox) -> tuple[Mesh, tuple[float, float, float], dict]:
    (x0, y0, _), (x1, y1, z1) = screen_bbox
    z = z1 + SCREEN_LIFT_MM
    origin = ((x0 + x1) / 2, (y0 + y1) / 2, z)
    corners = [(x0, y1, z), (x1, y1, z), (x1, y0, z), (x0, y0, z)]  # TL TR BR BL
    mesh = Mesh(uvs=[0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0])
    for point in corners:
        mesh.positions.extend((point[i] - origin[i]) * MM_TO_M for i in range(3))
        mesh.normals.extend((0.0, 0.0, 1.0))
    mesh.indices = [0, 3, 2, 0, 2, 1]
    active = {"w": round(x1 - x0, 3), "h": round(y1 - y0, 3)}
    return mesh, origin, active


# ---- glb writer/reader ------------------------------------------------------

class _Buffer:
    def __init__(self, doc: dict):
        self.doc = doc
        self.data = bytearray()

    def _view(self, payload: bytes, target: int) -> int:
        while len(self.data) % 4:
            self.data.append(0)
        self.doc["bufferViews"].append({
            "buffer": 0, "byteOffset": len(self.data),
            "byteLength": len(payload), "target": target,
        })
        self.data.extend(payload)
        return len(self.doc["bufferViews"]) - 1

    def accessor(self, values, kind: str, component: int, target: int,
                 bounds: bool) -> int:
        fmt = COMPONENT_FORMAT[component]
        payload = struct.pack(f"<{len(values)}{fmt}", *values)
        accessor = {
            "bufferView": self._view(payload, target),
            "componentType": component,
            "count": len(values) // COMPONENTS[kind],
            "type": kind,
        }
        if bounds:
            width = COMPONENTS[kind]
            stored = struct.unpack(f"<{len(values)}{fmt}", payload)
            accessor["min"] = [min(stored[i::width]) for i in range(width)]
            accessor["max"] = [max(stored[i::width]) for i in range(width)]
        self.doc["accessors"].append(accessor)
        return len(self.doc["accessors"]) - 1

    def mesh(self, name: str, mesh: Mesh, material: int) -> int:
        attributes = {
            "POSITION": self.accessor(mesh.positions, "VEC3", FLOAT, ARRAY_BUFFER, True),
            "NORMAL": self.accessor(mesh.normals, "VEC3", FLOAT, ARRAY_BUFFER, False),
        }
        if mesh.uvs is not None:
            attributes["TEXCOORD_0"] = self.accessor(
                mesh.uvs, "VEC2", FLOAT, ARRAY_BUFFER, True
            )
        index_type = UNSIGNED_SHORT if max(mesh.indices) < 65535 else UNSIGNED_INT
        indices = self.accessor(mesh.indices, "SCALAR", index_type,
                                ELEMENT_ARRAY_BUFFER, False)
        self.doc["meshes"].append({
            "name": name,
            "primitives": [{"attributes": attributes, "indices": indices,
                            "material": material}],
        })
        return len(self.doc["meshes"]) - 1

    def finish(self) -> bytes:
        while len(self.data) % 4:
            self.data.append(0)
        self.doc["buffers"] = [{"byteLength": len(self.data)}]
        return bytes(self.data)


def pack_glb(doc: dict, binary: bytes) -> bytes:
    text = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    binary = binary + b"\x00" * (-len(binary) % 4)
    total = 12 + 8 + len(text) + 8 + len(binary)
    return (GLB_MAGIC + struct.pack("<II", 2, total)
            + struct.pack("<II", len(text), CHUNK_JSON) + text
            + struct.pack("<II", len(binary), CHUNK_BIN) + binary)


def read_glb(data: bytes) -> tuple[dict, bytes]:
    if len(data) < 20 or data[:4] != GLB_MAGIC:
        raise GlbError("not a glb (bad magic or too short)")
    version, total = struct.unpack_from("<II", data, 4)
    if version != 2 or total != len(data):
        raise GlbError(f"glb header version={version} length={total} size={len(data)}")
    length, kind = struct.unpack_from("<II", data, 12)
    if kind != CHUNK_JSON or 20 + length > len(data):
        raise GlbError("first glb chunk is not a complete JSON chunk")
    try:
        doc = json.loads(data[20:20 + length].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GlbError(f"glb JSON chunk does not parse: {error}") from error
    binary = b""
    offset = 20 + length
    if offset < len(data):
        if offset + 8 > len(data):
            raise GlbError("truncated BIN chunk header")
        length, kind = struct.unpack_from("<II", data, offset)
        if kind != CHUNK_BIN or offset + 8 + length > len(data):
            raise GlbError("second glb chunk is not a complete BIN chunk")
        binary = data[offset + 8:offset + 8 + length]
    if not isinstance(doc, dict):
        raise GlbError("glb JSON is not an object")
    return doc, binary


def read_accessor(doc: dict, binary: bytes, index: int) -> list:
    try:
        accessor = doc["accessors"][index]
        view = doc["bufferViews"][accessor["bufferView"]]
        fmt = COMPONENT_FORMAT[accessor["componentType"]]
        count = accessor["count"] * COMPONENTS[accessor["type"]]
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        size = struct.calcsize(f"<{count}{fmt}")
        if start + size > view.get("byteOffset", 0) + view["byteLength"] or \
                start + size > len(binary):
            raise GlbError(f"accessor {index} reads past its buffer view")
        return list(struct.unpack_from(f"<{count}{fmt}", binary, start))
    except (KeyError, IndexError, TypeError) as error:
        raise GlbError(f"accessor {index} is malformed: {error}") from error


# ---- document assembly ------------------------------------------------------

def build_document(resolved: Resolved, parts: dict, openscad_version: str) -> bytes:
    """Assemble the glb bytes from per-part triangle soups (mm).

    parts = {"body": tris, "controls": {id: tris}, "screen_bbox": (lo, hi)}.
    """
    controls = parts.get("controls", {})
    missing = [cid for cid in resolved.control_ids if not controls.get(cid)]
    extra = sorted(set(controls) - set(resolved.control_ids))
    if missing or extra:
        raise ExportError(
            f"{resolved.model.slug}: control meshes missing={missing} extra={extra}"
        )
    scad = resolved.root / resolved.scad_rel
    doc = {
        "asset": {
            "version": "2.0",
            "generator": f"PocketForge {EXPORTER_REL}",
            "extras": {
                "frame": "pf-mm-v1",
                "units": "metres (pf-mm-v1 millimetres x 0.001)",
                "naming": "pf-semantic-v1",
                "model": resolved.model.slug,
                "source": resolved.scad_rel,
                "source_sha256": sha256_file(scad),
                "openscad": openscad_version,
            },
        },
        "scene": 0,
        "scenes": [{"name": resolved.model.slug, "nodes": [0]}],
        "nodes": [],
        "meshes": [],
        "materials": [],
        "accessors": [],
        "bufferViews": [],
    }
    for name, (token, klass, roughness) in MATERIALS.items():
        colour = resolved.palette[token]
        doc["materials"].append({
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": [round(srgb_to_linear(c), 6) for c in colour[:3]]
                + [1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": roughness,
            },
            "extras": {"class": klass, "palette_token": token},
        })
    material = {name: index for index, name in enumerate(MATERIALS)}
    buffer = _Buffer(doc)

    body_mesh = smooth_mesh(parts["body"], (0.0, 0.0, 0.0))
    doc["nodes"].append({
        "name": BODY_NODE,
        "mesh": buffer.mesh(BODY_NODE, body_mesh, material["body"]),
        "extras": {"role": "body", "pivot": "model origin"},
        "children": [],
    })
    for cid in resolved.control_ids:
        (lo, hi) = bbox(controls[cid])
        origin = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])
        extras = {"role": "control", "pivot": "footprint centre at lowest Z"}
        if resolved.model.descriptor:
            extras["inputs"] = resolved.inputs_by_part.get(cid, [])
        doc["nodes"].append({
            "name": cid,
            "mesh": buffer.mesh(cid, smooth_mesh(controls[cid], origin),
                                material["control"]),
            "translation": [f32(v * MM_TO_M) for v in origin],
            "extras": extras,
        })
        doc["nodes"][0]["children"].append(len(doc["nodes"]) - 1)
    for screen in resolved.screens:
        quad, origin, active = screen_quad(parts["screen_bbox"])
        doc["nodes"].append({
            "name": screen["node"],
            "mesh": buffer.mesh(screen["node"], quad, material["screen"]),
            "translation": [f32(v * MM_TO_M) for v in origin],
            "extras": {
                "role": "screen",
                "screen_id": screen["screen_id"],
                "panel_rotation_deg": screen["panel_rotation_deg"],
                "active_mm": active,
                "uv": UV_CONVENTION,
            },
        })
        doc["nodes"][0]["children"].append(len(doc["nodes"]) - 1)
    binary = buffer.finish()
    return pack_glb(doc, binary)


# ---- inspection and the structural contract ---------------------------------

def summarize(doc: dict, binary: bytes) -> Summary:
    try:
        nodes = doc["nodes"]
        names = [node.get("name") for node in nodes]
        parents: dict[str, str | None] = {name: None for name in names}
        for node in nodes:
            for child in node.get("children", []):
                parents[names[child]] = node.get("name")
        scene = doc["scenes"][doc.get("scene", 0)]
        roots = [names[i] for i in scene.get("nodes", [])]
        triangles = 0
        for mesh in doc.get("meshes", []):
            for primitive in mesh["primitives"]:
                if primitive.get("mode", 4) != 4:
                    raise GlbError("only TRIANGLES primitives are supported")
                if "indices" in primitive:
                    count = doc["accessors"][primitive["indices"]]["count"]
                else:
                    count = doc["accessors"][primitive["attributes"]["POSITION"]]["count"]
                triangles += count // 3
        screens = {}
        for node in nodes:
            name = node.get("name")
            if not isinstance(name, str) or not name.startswith(SCREEN_PREFIX):
                continue
            info = {"panel_rotation_deg": node.get("extras", {}).get("panel_rotation_deg"),
                    "uv_min": None, "uv_max": None}
            if "mesh" in node:
                attributes = doc["meshes"][node["mesh"]]["primitives"][0]["attributes"]
                if "TEXCOORD_0" in attributes:
                    uvs = read_accessor(doc, binary, attributes["TEXCOORD_0"])
                    info["uv_min"] = [min(uvs[0::2]), min(uvs[1::2])]
                    info["uv_max"] = [max(uvs[0::2]), max(uvs[1::2])]
            screens[name] = info
    except (KeyError, IndexError, TypeError) as error:
        raise GlbError(f"glb document is malformed: {error}") from error
    return Summary(
        names=names,
        roots=roots,
        parents=parents,
        has_mesh={node.get("name"): "mesh" in node for node in nodes},
        controls=[n for n in names if isinstance(n, str) and not is_reserved(n)],
        screens=screens,
        pivots=[n for n in names if isinstance(n, str) and n.startswith(PIVOT_PREFIX)],
        triangles=triangles,
    )


def contract_failures(summary: Summary, label: str,
                      budget: int = TRIANGLE_BUDGET) -> list[str]:
    failures = []
    if any(not isinstance(n, str) or not n for n in summary.names):
        failures.append(f"{label}: every node needs a non-empty name")
    if len(set(summary.names)) != len(summary.names):
        failures.append(f"{label}: duplicate node names {summary.names}")
    if summary.roots != [BODY_NODE]:
        failures.append(f"{label}: scene roots {summary.roots} != ['{BODY_NODE}']")
    for name in summary.names:
        seen, cursor = set(), name
        while cursor is not None and cursor not in seen:
            seen.add(cursor)
            cursor = summary.parents.get(cursor)
        if BODY_NODE not in seen:
            failures.append(f"{label}: node {name!r} is not under '{BODY_NODE}'")
    for name in summary.controls:
        if not summary.has_mesh.get(name):
            failures.append(f"{label}: control node {name!r} has no mesh")
    if not summary.screens:
        failures.append(f"{label}: no screen quad node ({SCREEN_PREFIX}*)")
    for name, info in sorted(summary.screens.items()):
        if info["uv_min"] is None:
            failures.append(f"{label}: screen node {name!r} has no TEXCOORD_0")
        elif info["uv_min"] != [0.0, 0.0] or info["uv_max"] != [1.0, 1.0]:
            failures.append(
                f"{label}: screen node {name!r} UV range "
                f"{info['uv_min']}..{info['uv_max']} != [0,0]..[1,1]"
            )
        if info["panel_rotation_deg"] not in ROTATION_DEG.values():
            failures.append(
                f"{label}: screen node {name!r} extras.panel_rotation_deg="
                f"{info['panel_rotation_deg']!r} not in {sorted(ROTATION_DEG.values())}"
            )
    for name in summary.pivots:
        if summary.has_mesh.get(name):
            failures.append(f"{label}: pivot node {name!r} must be an empty node")
    if summary.triangles > budget:
        failures.append(
            f"{label}: {summary.triangles} triangles exceed the budget of {budget}"
        )
    return failures


def check_all(root: Path = ROOT, budget: int = TRIANGLE_BUDGET):
    """--check: committed glb sha + structural contract for every device."""
    failures: list[str] = []
    counts: dict[str, int] = {}
    metas = sorted((root / "skins").glob(f"*/{METADATA_NAME}"))
    if not metas:
        return [f"no skins/*/{METADATA_NAME} found"], counts
    for meta_path in metas:
        device = meta_path.parent.name
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        glb = root / meta.get("glb", "")
        if not meta.get("glb") or not glb.is_file():
            failures.append(f"{device}: missing committed glb {meta.get('glb')!r}")
            continue
        actual = sha256_file(glb)
        if actual != meta.get("glb_sha256"):
            failures.append(
                f"{device}: glb_sha256 drift for {meta['glb']}: "
                f"metadata={meta.get('glb_sha256')} committed={actual} "
                "(re-export with export_gltf.py --write)"
            )
            continue
        try:
            summary = summarize(*read_glb(glb.read_bytes()))
        except GlbError as error:
            failures.append(f"{device}: {error}")
            continue
        failures.extend(contract_failures(summary, device, budget))
        if summary.names != meta.get("nodes"):
            failures.append(
                f"{device}: glb nodes {summary.names} != {METADATA_NAME} nodes "
                f"{meta.get('nodes')}"
            )
        if summary.triangles != meta.get("triangles"):
            failures.append(
                f"{device}: glb has {summary.triangles} triangles, "
                f"{METADATA_NAME} records {meta.get('triangles')}"
            )
        counts[device] = summary.triangles
    return failures, counts


# ---- OpenSCAD side (local --write only) -------------------------------------

def openscad_version(openscad: str) -> str:
    result = subprocess.run([openscad, "--version"], capture_output=True, text=True,
                            check=False)
    text = (result.stdout + result.stderr).strip()
    match = re.search(r"version\s+(\S+)", text)
    if result.returncode != 0 or not match:
        raise ExportError(f"cannot run {openscad} --version: {text}")
    return match.group(1)


def parse_stl(data: bytes) -> list[tuple]:
    if data[:5] == b"solid" and b"facet" in data[:400]:
        points = [tuple(float(v) for v in line.split()[1:4])
                  for line in data.decode("ascii").splitlines()
                  if line.strip().startswith("vertex")]
    else:
        if len(data) < 84:
            raise ExportError("STL too short")
        count = struct.unpack_from("<I", data, 80)[0]
        points = []
        for index in range(count):
            values = struct.unpack_from("<12f", data, 84 + index * 50)
            points.extend([tuple(values[3:6]), tuple(values[6:9]), tuple(values[9:12])])
    if len(points) % 3:
        raise ExportError("STL vertex count is not a multiple of 3")
    return [tuple(points[i:i + 3]) for i in range(0, len(points), 3)]


def openscad_part(root: Path, openscad: str, version: str, scad: Path,
                  defines: dict[str, str]) -> list[tuple]:
    key = hashlib.sha256()
    key.update(scad.read_bytes())
    key.update(json.dumps(defines, sort_keys=True).encode())
    key.update(version.encode())
    cache = root / "device-models" / ".cache" / "stl"
    cache.mkdir(parents=True, exist_ok=True)
    cached = cache / f"{key.hexdigest()}.stl"
    if not cached.is_file():
        label = " ".join(f"{k}={v}" for k, v in defines.items())
        print(f"openscad {scad.name} {label}", file=sys.stderr, flush=True)
        out = cache / f"{key.hexdigest()}.{os.getpid()}.partial.stl"
        command = [openscad, "-o", str(out)]
        for name, value in defines.items():
            command += ["-D", f'{name}="{value}"']
        try:
            result = subprocess.run(command + [str(scad)], capture_output=True,
                                    text=True, check=False)
            if result.returncode != 0 or not out.is_file():
                raise ExportError(f"openscad failed for {label}:\n{result.stderr}")
            os.replace(out, cached)
        finally:
            out.unlink(missing_ok=True)
    return parse_stl(cached.read_bytes())


def openscad_parts(resolved: Resolved, openscad: str, version: str) -> dict:
    scad = resolved.root / resolved.scad_rel
    body = openscad_part(resolved.root, openscad, version, scad, {"PART": "shell"})
    controls = {
        cid: openscad_part(resolved.root, openscad, version, scad,
                           {"PART": "control", "CONTROL_ID": cid})
        for cid in resolved.control_ids
    }
    screen = openscad_part(resolved.root, openscad, version, scad, {"PART": "screen"})
    return {"body": body, "controls": controls, "screen_bbox": bbox(screen)}


def write_outputs(root: Path, resolved: Resolved, parts: dict,
                  openscad_version: str) -> dict:
    data = build_document(resolved, parts, openscad_version)
    summary = summarize(*read_glb(data))
    failures = contract_failures(summary, resolved.model.skin)
    if failures:
        raise ExportError("; ".join(failures))
    skin_dir = root / "skins" / resolved.model.skin
    skin_dir.mkdir(parents=True, exist_ok=True)
    glb = skin_dir / GLB_NAME
    glb.write_bytes(data)
    meta = {
        "schema_version": 1,
        "device": resolved.model.skin,
        "model": resolved.model.slug,
        "descriptor": resolved.model.descriptor,
        "source": resolved.scad_rel,
        "source_sha256": sha256_file(root / resolved.scad_rel),
        "exporter": EXPORTER_REL,
        "exporter_sha256": sha256_file(root / EXPORTER_REL),
        "openscad": openscad_version,
        "glb": f"skins/{resolved.model.skin}/{GLB_NAME}",
        "glb_sha256": sha256_file(glb),
        "nodes": summary.names,
        "controls": summary.controls,
        "screens": resolved.screens,
        "triangles": summary.triangles,
        "triangle_budget": TRIANGLE_BUDGET,
    }
    (skin_dir / METADATA_NAME).write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return meta


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", action="append", choices=sorted(MODELS),
                        help="model slug to export (repeatable)")
    parser.add_argument("--all", action="store_true", help="export every model")
    parser.add_argument("--write", action="store_true",
                        help="run OpenSCAD and write skins/<id>/model.glb + model-glb.json")
    parser.add_argument("--check", action="store_true",
                        help="verify committed glbs (no OpenSCAD needed)")
    parser.add_argument("--openscad", default=shutil.which("openscad") or "openscad")
    args = parser.parse_args(argv)
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")

    if args.check:
        failures, counts = check_all(ROOT)
        for device, count in sorted(counts.items()):
            print(f"glb device={device} triangles={count} budget={TRIANGLE_BUDGET}")
        if failures:
            print("glb_check=fail", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        print(f"glb_check=pass models={len(counts)}")
        return 0

    slugs = sorted(MODELS) if args.all else (args.model or [])
    if not slugs:
        parser.error("--write needs --model <slug> or --all")
    try:
        version = openscad_version(args.openscad)
        for slug in slugs:
            resolved = resolve_model(ROOT, MODELS[slug])
            parts = openscad_parts(resolved, args.openscad, version)
            meta = write_outputs(ROOT, resolved, parts, version)
            print(f"wrote {meta['glb']} triangles={meta['triangles']} "
                  f"nodes={len(meta['nodes'])} sha256={meta['glb_sha256']}")
    except ExportError as error:
        print(f"export_gltf: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
