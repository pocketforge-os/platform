#!/usr/bin/env python3
"""regression/caps/test_caps_v2.py — descriptor schema v2 + device catalog self-test (tsp-h5ed.46.3).

Device-free, stdlib only. Covers what test_caps.py does not:
  - the shipped v1 descriptors (a133/a523) still validate with the v2-aware validator;
  - the synthetic clamshell fixture (tests/caps-fixtures/clamshell) validates clean via `--root`,
    and its generated artefacts have not drifted from gen_fixture.py;
  - every v2 validation rule is shown to FAIL on a hostile addition and to PASS on the fixture
    in the SAME `caps.py --root <tmp> validate` invocation: each case is a copy of the fixture
    under its own device id with one text mutation, so one run carries the positive control
    and all the negatives. A case passes only when the device's set of named E_* rules equals
    the expected set (a parse error or the wrong rule firing is a failure, never a negative);
  - devices/catalog.toml lists the four products with their rungs, and the catalog rules
    (duplicate ids, dangling references, declared > derived) fail by name next to good rows.

Run:  python3 regression/caps/test_caps_v2.py   (exit 0 = all pass)
"""
import os, sys, re, json, shutil, subprocess, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CAPS_PY = os.path.join(ROOT, "core", "caps.py")
FIXTURE = os.path.join(ROOT, "tests", "caps-fixtures", "clamshell")
FIXTURE_DEV = os.path.join(FIXTURE, "devices", "synth-clamshell")
GEN_PY = os.path.join(FIXTURE, "gen_fixture.py")
SCHEMA_PATH = os.path.join(ROOT, "schemas", "capabilities.schema.json")
TAG = re.compile(r"\bE_[A-Z0-9_]+\b")

_spec = importlib.util.spec_from_file_location("caps", CAPS_PY)
caps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(caps)

_failures = []
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        _failures.append(name)
        if detail:
            print("  " + detail.replace("\n", "\n  "))


def run(*args, root=None):
    cmd = [sys.executable, "-B", CAPS_PY] + (["--root", root] if root else []) + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def tree_delete(d):
    """Bottom-up delete of a temp tree (no rm -rf / rmtree)."""
    for dirpath, dirnames, filenames in os.walk(d, topdown=False):
        for f in filenames:
            os.remove(os.path.join(dirpath, f))
        for sub in dirnames:
            os.rmdir(os.path.join(dirpath, sub))
    os.rmdir(d)


def read(path):
    with open(path) as f:
        return f.read()


def by_device(stdout):
    """{device: (ok?, [error lines])} from `caps.py validate` output."""
    out = {}
    for line in stdout.splitlines():
        m = re.match(r"^(OK|ERROR|WARN)\s+([a-z0-9-]+): (.*)$", line)
        if not m:
            continue
        kind, dev, msg = m.groups()
        ok, errs, warns = out.get(dev, (False, [], []))
        if kind == "OK":
            ok = True
        elif kind == "ERROR":
            errs.append(msg)
        else:
            warns.append(msg)
        out[dev] = (ok, errs, warns)
    return out


# ---------------------------------------------------------------------------
# Hostile additions. Each case = (device id, mutations, expected E_* tag set, needle).
# A mutation is (old, new): `old` must occur in the fixture text EXACTLY once (so a mutation can
# never silently no-op), or ("$append", text) to add tables at the end of the file.
# expected = set() means "a SCHEMA error, untagged"; then `needle` must appear in an error line.
# ---------------------------------------------------------------------------
POS = set()          # sentinel: expected to validate OK
GLB_LINE = 'glb    = "skins/synth-clamshell/model.glb"'
REAL_GLB = os.path.join(FIXTURE, "skins", "synth-clamshell", "model.glb")   # exists, outside --root
REAL_PKG = os.path.join(ROOT, "device-models", "trimui-smart-pro")           # exists, outside --root
DUP_JOINT = """
[[joints]]
id    = "lid"
kind  = "swivel"
node  = "pivot_lid"
axis  = [0.0, 0.0, 1.0]
range = [0.0, 90.0]
[[joints.postures]]
id    = "any"
range = [0.0, 90.0]
"""
CHAIN = """
[[joints]]
id      = "swing"
kind    = "swivel"
node    = "pivot_swing"
parent  = "lid"
axis    = [0.0, 0.0, 1.0]
range   = [-90.0, 90.0]
default = 0.0
[[joints.postures]]
id    = "left"
range = [-90.0, 0.0]
screen_rotation = { top = "cw270" }
[[joints.postures]]
id    = "right"
range = [0.0, 90.0]
[[joints]]
id    = "follow"
kind  = "slide"
node  = "pivot_follow"
axis  = [0.0, 1.0, 0.0]
range = [0.0, 38.0]
drive = { joint = "swing", map = [[-90.0, 0.0], [0.0, 0.0], [90.0, 38.0]] }
"""
DRIVEN_WITH_POSTURES = """
[[joints]]
id    = "follow"
kind  = "slide"
node  = "pivot_follow"
axis  = [0.0, 1.0, 0.0]
range = [0.0, 38.0]
drive = { joint = "lid", map = [[0.0, 0.0], [180.0, 38.0]] }
[[joints.postures]]
id    = "any"
range = [0.0, 38.0]
"""
DRIVE_CYCLE = """
[[joints]]
id    = "a"
kind  = "slide"
node  = "pivot_a"
axis  = [0.0, 1.0, 0.0]
range = [0.0, 10.0]
drive = { joint = "b", map = [[0.0, 0.0], [10.0, 10.0]] }
[[joints]]
id    = "b"
kind  = "slide"
node  = "pivot_b"
axis  = [0.0, 1.0, 0.0]
range = [0.0, 10.0]
drive = { joint = "a", map = [[0.0, 0.0], [10.0, 10.0]] }
"""
NO_MODEL = [('[model]\nglb    = "skins/synth-clamshell/model.glb"\nframe  = "pf-mm-v1"\n'
             'naming = "pf-semantic-v1"\n', ""),
            ('[maturity]\ndeclared = "sim-ready"', "")]

CASES = [
    # ---- positive controls (beyond the untouched fixture) ----
    ("pos-fixture", [], POS, None),
    ("pos-chain-drive-slide", NO_MODEL + [("$append", CHAIN)], POS, None),
    ("pos-declared-below-derived", [('declared = "sim-ready"', 'declared = "model-only"')], POS, None),
    ("pos-screen-renamed",
     [('[[screens]]\nid            = "bottom"', '[[screens]]\nid            = "bottomx"'),
      ('active_screens   = ["top", "bottom"]\n[[joints.postures]]', 'active_screens   = ["top", "bottomx"]\n[[joints.postures]]'),
      ('active_screens   = ["top", "bottom"]\nscreen_rotation  = { top = "none", bottom = "none" }',
       'active_screens   = ["top"]\nscreen_rotation  = { top = "none" }')], POS, None),
    # ---- schema_version gating ----
    ("neg-v2-key-at-v1", [("schema_version = 2", "schema_version = 1")], {"E_V2_AT_V1"}, None),
    ("neg-v2-key-absent-version", [("schema_version = 2\n", "")], {"E_V2_AT_V1"}, None),
    ("neg-schema-version-3", [("schema_version = 2", "schema_version = 3")], {"E_SCHEMA_VERSION"}, None),
    # ---- joints ----
    ("neg-dup-joint-id", [("$append", DUP_JOINT)], {"E_JOINT_DUPLICATE"}, None),
    ("neg-joint-node-name", [('node     = "pivot_lid"', 'node     = "hinge_lid"')],
     {"E_JOINT_NODE", "E_MODEL_NODE"}, None),
    ("neg-joint-axis-zero", [("axis     = [-1.0, 0.0, 0.0]", "axis     = [0.0, 0.0, 0.0]")],
     {"E_JOINT_AXIS"}, None),
    ("neg-joint-default-out", [("default  = 180.0", "default  = 200.0")], {"E_JOINT_RANGE"}, None),
    ("neg-joint-detent-out", [("detents  = [0.0, 180.0]", "detents  = [0.0, 190.0]")], {"E_JOINT_RANGE"}, None),
    ("neg-joint-range-reversed", [("range    = [0.0, 180.0]", "range    = [180.0, 0.0]")],
     {"E_JOINT_RANGE"}, None),
    ("neg-joint-sensor-ghost", [('sensor   = "hinge"', 'sensor   = "ghost"')], {"E_JOINT_REF"}, None),
    ("neg-joint-sensor-wrong-kind", [('kind = "hinge_angle"', 'kind = "accel"')], {"E_JOINT_REF"}, None),
    ("neg-joint-parent-ghost", NO_MODEL + [("$append", CHAIN.replace('parent  = "lid"', 'parent  = "ghost"'))],
     {"E_JOINT_REF"}, None),
    ("neg-switch-not-sw", [('code = "SW_LID"', 'code = "KEY_POWER"')], {"E_JOINT_SWITCH"}, None),
    ("neg-switch-primary-node", [('source = "gpio-keys", active', 'source = "PF Synth Clamshell", active')],
     {"E_JOINT_SWITCH"}, None),
    ("neg-switch-threshold-out", [("active = [0.0, 10.0]", "active = [0.0, 200.0]")], {"E_JOINT_SWITCH"}, None),
    ("neg-drive-with-postures", NO_MODEL + [("$append", DRIVEN_WITH_POSTURES)], {"E_JOINT_DRIVE"}, None),
    ("neg-drive-cycle", NO_MODEL + [("$append", DRIVE_CYCLE)], {"E_JOINT_DRIVE"}, None),
    ("neg-drive-map-out", NO_MODEL + [("$append", CHAIN.replace("[90.0, 38.0]", "[90.0, 50.0]"))],
     {"E_JOINT_DRIVE"}, None),
    # ---- postures ----
    ("neg-posture-gap", [("range            = [10.0, 150.0]", "range            = [12.0, 150.0]")],
     {"E_POSTURE_TILING"}, None),
    ("neg-posture-overlap", [("range            = [10.0, 150.0]", "range            = [8.0, 150.0]")],
     {"E_POSTURE_TILING"}, None),
    ("neg-posture-short", [("range            = [150.0, 180.0]", "range            = [150.0, 170.0]")],
     {"E_POSTURE_TILING"}, None),
    ("neg-posture-dup-id", [('id               = "open"', 'id               = "half"')], {"E_POSTURE_DUPLICATE"}, None),
    ("neg-posture-screen-ref", [('active_screens   = ["top", "bottom"]\n[[joints.postures]]',
                                 'active_screens   = ["top", "middle"]\n[[joints.postures]]')], {"E_POSTURE_REF"}, None),
    ("neg-posture-input-ref", [('reachable_inputs = ["vol_up", "vol_down"]', 'reachable_inputs = ["vol_up", "power"]')],
     {"E_POSTURE_REF"}, None),
    ("neg-posture-rotation-ref", [('{ top = "none", bottom = "none" }', '{ top = "none", side = "none" }')],
     {"E_POSTURE_REF"}, None),
    # ---- model ----
    ("neg-model-sha", [('frame  = "pf-mm-v1"', 'frame  = "pf-mm-v1"\nsha256 = "' + "0" * 64 + '"')],
     {"E_MODEL_SHA"}, None),
    ("neg-model-glb-missing", [('glb    = "skins/synth-clamshell/model.glb"', 'glb    = "skins/synth-clamshell/nope.glb"')],
     {"E_MODEL_GLB"}, None),
    ("neg-model-glb-not-gltf", [('glb    = "skins/synth-clamshell/model.glb"', 'glb    = "skins/synth-clamshell/body.png"')],
     {"E_MODEL_GLB"}, None),
    ("neg-model-glb-truncated", [('glb    = "skins/synth-clamshell/model.glb"', 'glb    = "skins/synth-clamshell/truncated.glb"')],
     {"E_MODEL_GLB"}, None),
    # Root confinement: every artefact path resolves INSIDE --root. Each escape below points at a
    # file/dir that EXISTS (the real fixture glb, a copy beside the root, a repo package), so only
    # the confinement rule can reject it.
    ("neg-model-glb-absolute", [(GLB_LINE, 'glb    = "' + REAL_GLB + '"')], {"E_MODEL_GLB"}, None),
    ("neg-model-glb-dotdot", [(GLB_LINE, 'glb    = "../outside/model.glb"')], {"E_MODEL_GLB"}, None),
    ("neg-model-glb-symlink-escape", [(GLB_LINE, 'glb    = "skins/synth-clamshell/escape.glb"')],
     {"E_MODEL_GLB"}, None),
    ("pos-model-glb-symlink-inside", [(GLB_LINE, 'glb    = "skins/synth-clamshell/inside.glb"')], POS, None),
    ("neg-model-source-absolute", [('frame  = "pf-mm-v1"', 'frame  = "pf-mm-v1"\nsource = "' + REAL_PKG + '"')],
     {"E_MODEL_SOURCE"}, None),
    ("neg-model-source-dotdot", [('frame  = "pf-mm-v1"', 'frame  = "pf-mm-v1"\nsource = "../outside"')],
     {"E_MODEL_SOURCE"}, None),
    ("neg-model-node-missing", [('skin_part = "btn_guide"', 'skin_part = "btn_home"'),
                                ("btn_guide    = {", "btn_home     = {")], {"E_MODEL_NODE"}, None),
    ("neg-model-source-missing", [('frame  = "pf-mm-v1"', 'frame  = "pf-mm-v1"\nsource = "device-models/ghost"')],
     {"E_MODEL_SOURCE"}, None),
    # ---- maturity ----
    ("neg-maturity-no-model", NO_MODEL[:1], {"E_MATURITY_EXCEEDS"}, None),
    ("neg-maturity-unbound-screen", [('node          = "screen_bottom"\n', "")], {"E_MATURITY_EXCEEDS"}, None),
    # ---- screens ----
    ("neg-screen-two-primaries", [('role          = "secondary"', 'role          = "primary"')],
     {"E_SCREEN_PRIMARY"}, None),
    ("neg-screen-primary-not-first", [('role          = "primary"', 'role          = "secondaryX"'),
                                      ('role          = "secondary"', 'role          = "primary"'),
                                      ('role          = "secondaryX"', 'role          = "secondary"')],
     {"E_SCREEN_PRIMARY"}, None),
    ("neg-screen-dup-id", [('id            = "bottom"', 'id            = "top"')],
     {"E_SCREEN_ID", "E_POSTURE_REF"}, None),  # renaming 'bottom' also orphans its posture refs
    ("neg-screen-missing-id", [('id            = "bottom"\n', "")], {"E_SCREEN_ID", "E_POSTURE_REF"}, None),
    ("neg-touch-primary-node", [('source   = "synth-touch"', 'source   = "PF Synth Clamshell"')],
     {"E_SCREEN_TOUCH"}, None),
    ("neg-touch-axis", [("x = { min = 0, max = 639 }", "x = { min = 639, max = 0 }")], {"E_SCREEN_TOUCH"}, None),
    ("neg-physical-zero", [("w = 150.0, h = 75.0, d = 22.0", "w = 150.0, h = 0.0, d = 22.0")],
     {"E_PHYSICAL"}, None),
    # ---- schema-level (structural; untagged schema errors) ----
    ("neg-schema-fourcc", [('fourcc        = "XR24"\ndiagonal_in   = 3.5\nactive_mm     = { w = 71.1, h = 53.3 }\n\n[[screens]]',
                            'fourcc        = "XR2"\ndiagonal_in   = 3.5\nactive_mm     = { w = 71.1, h = 53.3 }\n\n[[screens]]')],
     set(), "fourcc"),
    ("neg-schema-joint-kind", [('kind     = "hinge"', 'kind     = "telescope"')], set(), "kind"),
    ("neg-schema-joint-unknown-key", [('kind     = "hinge"', 'kind     = "hinge"\nunits    = "deg"')], set(), "units"),
    ("neg-schema-maturity-enum", [('declared = "sim-ready"', 'declared = "shipping"')], set(), "declared"),
]


def mutate(text, case_id, mutations):
    text = text.replace('id           = "synth-clamshell"', f'id           = "{case_id}"')
    for old, new in mutations:
        if old == "$append":
            text += new
            continue
        n = text.count(old)
        if n != 1:
            raise AssertionError(f"case {case_id}: mutation anchor occurs {n}x (want 1): {old!r}")
        text = text.replace(old, new)
    return text


def descriptor_cases(tmp):
    """Build one --root tree holding every case, validate it in ONE invocation, judge per device."""
    os.makedirs(os.path.join(tmp, "devices"))
    shutil.copytree(os.path.join(FIXTURE, "skins"), os.path.join(tmp, "skins"))
    glb_dir = os.path.join(tmp, "skins", "synth-clamshell")
    with open(os.path.join(glb_dir, "model.glb"), "rb") as f:
        head = f.read(100)  # header + part of the JSON chunk: a partial file must never pass
    with open(os.path.join(glb_dir, "truncated.glb"), "wb") as f:
        f.write(head)
    outside = os.path.join(os.path.dirname(tmp), "outside")       # beside the root, not in it
    os.makedirs(outside)
    shutil.copyfile(os.path.join(glb_dir, "model.glb"), os.path.join(outside, "model.glb"))
    os.symlink(os.path.join(outside, "model.glb"), os.path.join(glb_dir, "escape.glb"))
    os.symlink("model.glb", os.path.join(glb_dir, "inside.glb"))
    caps_txt = read(os.path.join(FIXTURE_DEV, "capabilities.toml"))
    prof_txt = read(os.path.join(FIXTURE_DEV, "profile.toml"))
    for case_id, muts, _, _ in CASES:
        d = os.path.join(tmp, "devices", case_id)
        os.makedirs(d)
        with open(os.path.join(d, "capabilities.toml"), "w") as f:
            f.write(mutate(caps_txt, case_id, muts))
        with open(os.path.join(d, "profile.toml"), "w") as f:
            f.write(prof_txt.replace('"synth-clamshell"', f'"{case_id}"'))
    rc, out, err = run("validate", root=tmp)
    check("hostile run: one invocation exits 1 (negatives present)", rc == 1, err)
    res = by_device(out)
    for case_id, _, expected, needle in CASES:
        ok, errs, warns = res.get(case_id, (False, [], []))
        tags = {t for e in errs for t in TAG.findall(e)}
        if expected is POS:
            check(f"{case_id}: validates OK (positive control, same invocation)",
                  ok and not errs and not warns, "\n".join(errs + warns))
        elif not expected:
            check(f"{case_id}: schema rejects, naming '{needle}'",
                  not ok and errs and not tags and any(needle in e for e in errs), "\n".join(errs))
        else:
            check(f"{case_id}: rejected by exactly {sorted(expected)}",
                  not ok and tags == expected and not any("cannot parse" in e for e in errs),
                  "\n".join(errs))
    return out


CATALOG_GOOD = """schema_version = 1
[[devices]]
id = "synth-sim"
manufacturer = "PocketForge"
name = "Synth Sim"
code_name = "SC0001"
platform_id = "synth-clamshell"
package = "device-models/synth-pkg"
maturity = "sim-ready"
[[devices]]
id = "synth-model"
manufacturer = "PocketForge"
name = "Synth Model"
package = "device-models/synth-pkg"
maturity = "model-only"
[[devices]]
id = "synth-planned"
manufacturer = "PocketForge"
name = "Synth Planned"
maturity = "planned"
"""
CATALOG_BAD = """
[[devices]]
id = "synth-planned"
manufacturer = "PocketForge"
name = "Duplicate"
maturity = "planned"
[[devices]]
id = "bad-platform"
manufacturer = "PocketForge"
name = "Bad Platform"
platform_id = "ghost"
maturity = "planned"
[[devices]]
id = "bad-package"
manufacturer = "PocketForge"
name = "Bad Package"
package = "device-models/ghost"
maturity = "planned"
[[devices]]
id = "bad-package-abs"
manufacturer = "PocketForge"
name = "Absolute Package"
package = "{REAL_PKG}"
maturity = "planned"
[[devices]]
id = "bad-package-dotdot"
manufacturer = "PocketForge"
name = "Escaping Package"
package = "../outside-pkg"
maturity = "planned"
[[devices]]
id = "bad-rung"
manufacturer = "PocketForge"
name = "Bad Rung"
package = "device-models/synth-pkg"
maturity = "sim-ready"
"""


def catalog_cases(tmp):
    shutil.copytree(os.path.join(FIXTURE, "skins"), os.path.join(tmp, "skins"))
    os.makedirs(os.path.join(os.path.dirname(tmp), "outside-pkg"))   # beside the root, not in it
    shutil.copytree(FIXTURE_DEV, os.path.join(tmp, "devices", "synth-clamshell"))
    os.makedirs(os.path.join(tmp, "device-models", "synth-pkg"))
    cat = os.path.join(tmp, "devices", "catalog.toml")
    with open(cat, "w") as f:
        f.write(CATALOG_GOOD)
    rc, out, err = run("catalog", root=tmp)
    rows = [l.split("\t") for l in out.splitlines() if "\t" in l]
    check("catalog (good rows): exits 0", rc == 0, out + err)
    check("catalog (good rows): derived rungs sim-ready / model-only / planned",
          [(r[0], r[-2], r[-1]) for r in rows[1:]] == [("synth-sim", "sim-ready", "sim-ready"),
                                                         ("synth-model", "model-only", "model-only"),
                                                         ("synth-planned", "planned", "planned")],
          out)
    with open(cat, "a") as f:
        f.write(CATALOG_BAD.replace("{REAL_PKG}", REAL_PKG))
    rc, out, err = run("catalog", "validate", root=tmp)
    errs = [l for l in out.splitlines() if l.startswith("ERROR")]
    check("catalog (hostile rows): one invocation exits 1", rc == 1, out + err)
    def has(row, tag):
        return any(f"'{row}'" in e and tag in e for e in errs)
    check("catalog: duplicate id -> E_CATALOG_DUPLICATE", has("synth-planned", "E_CATALOG_DUPLICATE"), out)
    check("catalog: platform_id with no descriptor -> E_CATALOG_REF", has("bad-platform", "E_CATALOG_REF"), out)
    check("catalog: package dir missing -> E_CATALOG_REF", has("bad-package", "E_CATALOG_REF"), out)
    check("catalog: absolute package path (exists, outside --root) -> E_CATALOG_REF",
          has("bad-package-abs", "E_CATALOG_REF"), out)
    check("catalog: ../ package path (exists, outside --root) -> E_CATALOG_REF",
          has("bad-package-dotdot", "E_CATALOG_REF"), out)
    check("catalog: declared sim-ready > derived model-only -> E_CATALOG_MATURITY",
          has("bad-rung", "E_CATALOG_MATURITY"), out)
    check("catalog: good rows stay clean next to hostile ones (same invocation)",
          not any(f"'{r}'" in e for e in errs for r in ("synth-sim", "synth-model")), out)
    check("catalog: every error is named", errs and all(TAG.search(e) for e in errs), out)
    # Schema-level: unknown maturity value.
    with open(cat, "w") as f:
        f.write(CATALOG_GOOD.replace('maturity = "planned"', 'maturity = "someday"'))
    rc, out, _ = run("catalog", "validate", root=tmp)
    check("catalog: maturity outside the three rungs is a schema error", rc == 1 and "someday" in out, out)


def main():
    # --- 1. shipped v1 descriptors unchanged + still valid under the v2-aware validator ---
    rc, out, err = run("validate", "a133", "a523")
    check("validate a133 a523: exit 0", rc == 0, out + err)
    for d in ("a133", "a523"):
        data = caps._load(os.path.join(ROOT, "devices", d, "capabilities.toml"))
        check(f"{d}: still a v1 descriptor (no schema_version, no v2 tables)",
              "schema_version" not in data and not any(k in data for k in getattr(caps, "V2_TOP_KEYS", ("physical", "model", "joints", "maturity"))))
    rc, out, err = run("validate")
    check("bare validate (all descriptors + ci-matrix + catalog): exit 0", rc == 0, out + err)
    check("bare validate covers a133, a523, ci-matrix and the catalog",
          all(s in out for s in ("OK    a133", "OK    a523", "OK    ci-matrix", "OK    catalog")), out)

    # --- 2. the synthetic clamshell fixture ---
    r = subprocess.run([sys.executable, "-B", GEN_PY, "--check"], capture_output=True, text=True)
    check("gen_fixture.py --check: committed PNG/glb artefacts match the generator", r.returncode == 0,
          r.stdout + r.stderr)
    rc, out, err = run("validate", root=FIXTURE)
    check("--root clamshell validate: exit 0", rc == 0, out + err)
    check("--root clamshell validate: synth-clamshell OK with zero warnings",
          "OK    synth-clamshell: capabilities valid" in out and "WARN" not in out, out)
    nodes = getattr(caps, "glb_node_names", lambda p: None)(os.path.join(FIXTURE, "skins", "synth-clamshell", "model.glb"))
    check("fixture glb parses as glTF 2.0 and names pivot_lid + both screen quads",
          isinstance(nodes, set) and {"pivot_lid", "screen_top", "screen_bottom"} <= nodes)
    try:
        import jsonschema
        data = caps._load(os.path.join(FIXTURE_DEV, "capabilities.toml"))
        with open(SCHEMA_PATH) as f:
            jsonschema.validate(data, json.load(f))
        check("fixture agrees with the reference jsonschema library", True)
    except ImportError:
        check("jsonschema not installed — reference agreement skipped", True)
    except Exception as e:  # noqa: BLE001 — any reference rejection is a failure
        check("fixture agrees with the reference jsonschema library", False, str(e))

    # --- 3. hostile additions, positive + negative controls in one invocation ---
    tmp = tempfile.mkdtemp(prefix="caps-v2-")
    try:
        descriptor_cases(os.path.join(tmp, "desc"))
        catalog_cases(os.path.join(tmp, "cat"))
    finally:
        tree_delete(tmp)

    # --- 4. the shipped catalog ---
    rc, out, err = run("catalog")
    rows = {l.split("\t")[0]: l.split("\t") for l in out.splitlines() if "\t" in l}
    check("catalog: exit 0", rc == 0, out + err)
    want = {"trimui-smart-pro": ("TG5040", "a133", "sim-ready"),
            "trimui-smart-pro-s": ("TG5050", "a523", "sim-ready"),
            "trimui-brick": ("TG3040", "", "model-only"),
            "powkiddy-x55": ("", "", "planned")}
    for pid, (code, plat, rung) in want.items():
        row = rows.get(pid)
        check(f"catalog row {pid}: code {code or '-'}, platform {plat or '-'}, declared {rung}",
              row is not None and row[3] == (code or "-") and row[4] == (plat or "-") and row[5] == rung,
              out)
    check("catalog lists exactly the four products", set(rows) - {"id"} == set(want), out)

    print()
    if _failures:
        print(f"{len(_failures)} FAILURE(S): " + ", ".join(_failures))
        return 1
    print("ALL CAPS V2 SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
