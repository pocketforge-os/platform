#!/usr/bin/env python3
"""tests/caps-fixtures/clamshell/gen_fixture.py — generate the synthetic clamshell's binary artefacts.

The SYNTHETIC two-screen clamshell (tsp-h5ed.46.3, D5/D6) is test data for the descriptor v2
articulation rules, NOT a device. Its descriptor (devices/synth-clamshell/capabilities.toml) is
hand-authored; the binaries it references are produced HERE, deterministically, stdlib only:

  skins/synth-clamshell/body.png      flat 640x600 2D skin (schema-required [skin].body)
  skins/synth-clamshell/body_lit.png  same size, lighter (all-lit overlay)
  skins/synth-clamshell/model.glb     tiny glTF 2.0 binary in the pf-mm-v1 frame with
                                      pf-semantic-v1 node names (one node per skin_part,
                                      screen_top / screen_bottom quads, pivot_lid)

Model, authored at the joint's REST value (range[0] = 0 deg = closed). Frame pf-mm-v1:
X left->right, Y bottom->top, Z rear->front, millimetres. The base lies on its back (front face
+Z); the lid lies closed on top of it, hinged along the base's top edge (y = 75, z = 11). Opening
rotates pivot_lid about axis [-1, 0, 0] by the joint value: at 90 deg the lid stands up, at 180
deg it lies flat above the base with screen_top facing +Z and reading upright.

Usage:
  gen_fixture.py            # (re)write the artefacts
  gen_fixture.py --check    # exit 1 if any committed artefact differs from what would be written
"""
import json, os, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SKIN_DIR = os.path.join(HERE, "skins", "synth-clamshell")

BASE = (150.0, 75.0, 11.0)          # body box w, h, d (mm); the lid is the same box
SCREEN = (71.1, 53.3)               # active area w, h (mm), both panels
# (node, centre x, centre y) on the base's front face (z = 11), each an 8 x 8 x 2 mm control.
FRONT_CONTROLS = [
    ("dpad", -55.0, 37.5), ("btn_north", 55.0, 46.0), ("btn_south", 55.0, 29.0),
    ("btn_west", 46.5, 37.5), ("btn_east", 63.5, 37.5),
    ("btn_select", -12.0, 5.0), ("btn_guide", 0.0, 5.0), ("btn_start", 12.0, 5.0),
]
REAR_CONTROLS = [("btn_l1", -60.0, 70.0), ("btn_r1", 60.0, 70.0)]   # on the rear face (z = 0)
SIDE_CONTROLS = [("btn_vol_up", 45.0), ("btn_vol_down", 30.0)]      # on the left face (x = -75)


def png(w, h, rgb):
    def chunk(typ, data):
        body = typ + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def cube():
    """Unit cube centred on the origin: 24 vertices (flat normals), 36 indices."""
    pos, nrm, idx = [], [], []
    for axis in range(3):
        for sign in (-1.0, 1.0):
            n = [0.0, 0.0, 0.0]; n[axis] = sign
            u, v = [(1, 2), (2, 0), (0, 1)][axis]
            base = len(pos)
            for a, b in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
                p = [0.0, 0.0, 0.0]; p[axis] = 0.5 * sign; p[u] = a; p[v] = b
                pos.append(p); nrm.append(n)
            quad = [0, 1, 2, 0, 2, 3] if sign > 0 else [0, 2, 1, 0, 3, 2]
            idx += [base + q for q in quad]
    return pos, nrm, None, idx


def quad():
    """Unit quad in the XY plane facing +Z; UV 0..1 over it, v = 0 at the top edge."""
    pos = [[-0.5, -0.5, 0.0], [0.5, -0.5, 0.0], [0.5, 0.5, 0.0], [-0.5, 0.5, 0.0]]
    return pos, [[0.0, 0.0, 1.0]] * 4, [[0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]], [0, 1, 2, 0, 2, 3]


def glb():
    gl = {"asset": {"version": "2.0", "generator": "pf gen_fixture.py (synthetic clamshell)"},
          "buffers": [], "bufferViews": [], "accessors": [], "meshes": [], "nodes": [],
          "materials": [
              {"name": "body", "pbrMetallicRoughness": {"baseColorFactor": [0.25, 0.25, 0.27, 1.0],
                                                         "metallicFactor": 0.0, "roughnessFactor": 0.7}},
              {"name": "control", "pbrMetallicRoughness": {"baseColorFactor": [0.08, 0.08, 0.08, 1.0],
                                                            "metallicFactor": 0.0, "roughnessFactor": 0.5}},
              {"name": "screen", "pbrMetallicRoughness": {"baseColorFactor": [0.0, 0.0, 0.0, 1.0],
                                                           "metallicFactor": 0.0, "roughnessFactor": 0.2},
               "emissiveFactor": [1.0, 1.0, 1.0]},
          ],
          "scenes": [{"name": "synth-clamshell", "nodes": [0]}], "scene": 0}
    blob = bytearray()

    def view(data, target):
        while len(blob) % 4:
            blob.append(0)
        gl["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data),
                                  "target": target})
        blob.extend(data)
        return len(gl["bufferViews"]) - 1

    def accessor(rows, typ, comp, target, minmax=False):
        flat = [x for r in rows for x in (r if isinstance(r, list) else [r])]
        fmt = "<%d%s" % (len(flat), "f" if comp == 5126 else "H")
        acc = {"bufferView": view(struct.pack(fmt, *flat), target), "componentType": comp,
               "count": len(rows), "type": typ}
        if minmax:
            acc["min"] = [min(r[i] for r in rows) for i in range(len(rows[0]))]
            acc["max"] = [max(r[i] for r in rows) for i in range(len(rows[0]))]
        gl["accessors"].append(acc)
        return len(gl["accessors"]) - 1

    def mesh(name, geom, material):
        pos, nrm, uv, idx = geom
        attrs = {"POSITION": accessor(pos, "VEC3", 5126, 34962, minmax=True),
                 "NORMAL": accessor(nrm, "VEC3", 5126, 34962)}
        if uv is not None:
            attrs["TEXCOORD_0"] = accessor(uv, "VEC2", 5126, 34962)
        gl["meshes"].append({"name": name, "primitives": [
            {"attributes": attrs, "indices": accessor(idx, "SCALAR", 5123, 34963), "material": material}]})
        return len(gl["meshes"]) - 1

    body_mesh = mesh("body_box", cube(), 0)
    control_mesh = mesh("control_box", cube(), 1)
    screen_mesh = mesh("screen_quad", quad(), 2)

    def node(name, children=None, **kw):
        gl["nodes"].append(dict(name=name, **kw))
        i = len(gl["nodes"]) - 1
        if children is not None:
            children.append(i)
        return i

    w, h, d = BASE
    root = node("synth-clamshell")
    top = []
    node("body_base", top, mesh=body_mesh, translation=[0.0, h / 2, d / 2], scale=[w, h, d])
    node("screen_bottom", top, mesh=screen_mesh, translation=[0.0, h / 2, d + 0.01],
         scale=[SCREEN[0], SCREEN[1], 1.0], extras={"panel_rotation_deg": 0})
    for name, x, y in FRONT_CONTROLS:
        node(name, top, mesh=control_mesh, translation=[x, y, d + 1.0], scale=[8.0, 8.0, 2.0])
    for name, x, y in REAR_CONTROLS:
        node(name, top, mesh=control_mesh, translation=[x, y, -1.0], scale=[20.0, 4.0, 2.0])
    for name, y in SIDE_CONTROLS:
        node(name, top, mesh=control_mesh, translation=[-w / 2 - 1.0, y, d / 2], scale=[2.0, 10.0, 4.0])
    lid = []
    # Closed, the lid's screen faces -Z onto the base: the quad is flipped 180 deg about X, which
    # the 180 deg opening rotation about -X undoes exactly (screen faces +Z, image upright).
    node("body_lid", lid, mesh=body_mesh, translation=[0.0, -h / 2, d / 2], scale=[w, h, d])
    node("screen_top", lid, mesh=screen_mesh, translation=[0.0, -h / 2, -0.01],
         rotation=[1.0, 0.0, 0.0, 0.0], scale=[SCREEN[0], SCREEN[1], 1.0],
         extras={"panel_rotation_deg": 0})
    pivot = node("pivot_lid", top, translation=[0.0, h, d])
    gl["nodes"][pivot]["children"] = lid
    gl["nodes"][root]["children"] = top

    while len(blob) % 4:
        blob.append(0)
    gl["buffers"].append({"byteLength": len(blob)})
    js = json.dumps(gl, sort_keys=True, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    return (struct.pack("<4sII", b"glTF", 2, total)
            + struct.pack("<I4s", len(js), b"JSON") + js
            + struct.pack("<I4s", len(blob), b"BIN\x00") + bytes(blob))


def artefacts():
    return {
        os.path.join(SKIN_DIR, "body.png"): png(640, 600, (60, 60, 66)),
        os.path.join(SKIN_DIR, "body_lit.png"): png(640, 600, (200, 200, 210)),
        os.path.join(SKIN_DIR, "model.glb"): glb(),
    }


def main(argv):
    check = argv[1:] == ["--check"]
    if argv[1:] and not check:
        sys.stderr.write(__doc__)
        return 2
    drift = []
    for path, data in artefacts().items():
        rel = os.path.relpath(path, HERE)
        if check:
            try:
                with open(path, "rb") as f:
                    same = f.read() == data
            except OSError:
                same = False
            if not same:
                drift.append(rel)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            print(f"wrote {rel} ({len(data)} bytes)")
    for rel in drift:
        print(f"DRIFT {rel}: committed bytes differ from gen_fixture.py output (re-run it)")
    if check and not drift:
        print("OK    synthetic clamshell artefacts match gen_fixture.py")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
