#!/usr/bin/env python3
"""core/caps.py — validator + tooling for the device CAPABILITY descriptor.

`capabilities.toml` is the NET-NEW per-variant sibling to `devices/<id>/profile.toml`,
joined ONLY by `device.id`. The build profile owns kernel/gpu/bootchain; THIS file owns
what a device can SENSE, ACTUATE, and LOOK LIKE — one descriptor consumed by the
capability broker (E2), the simulator (E5), and CI (E7).

Core invariants enforced here:
  - descriptor = EXPECTATION; the live EVIOCGBIT/EVIOCGABS probe = GROUND TRUTH (SPIKE-0).
  - missing hardware = ROW OMISSION, never a fabricated row (unknown/garbage keys rejected).
  - screen geometry is render INTENT (logical rotation enum), never the per-SoC magic
    number; panel pixel dims live in the kernel DTS and are NOT duplicated here. The only
    cross-check against the build profile is the `device.id` JOIN.

This file is CORE and MUST stay SoC-agnostic (ci/core-purity-check.sh). It deliberately
depends on the stdlib ONLY (a tiny JSON-Schema-subset engine), so `pf caps` runs on any
build/dev/CI host with Python 3.11+ — exactly like core/profile.py. The shipped
schemas/capabilities.schema.json is standard JSON-Schema (Draft 2020-12), so editors and
the reference `jsonschema` library validate it identically; the regression self-test
asserts that agreement when the library is present.

Usage:
  caps.py [--root <dir>] <command>  # --root: validate a fixture tree laid out like platform/
                                    #   (devices/, skins/, ...) instead of this checkout
  caps.py list                      # device ids that have a capabilities.toml
  caps.py validate [<id>...|--all]  # schema + semantic validation; non-zero exit on error
                                    #   (no id or --all: every descriptor + the CI gate matrix
                                    #   + the device catalog)
  caps.py matrix list [--posture blocking|advisory|excluded] [--format tsv|ids]
  caps.py matrix validate           # validate ci-matrix.toml vs the devices/ tree
  caps.py catalog [list|validate] [--format tsv|json]   # devices/catalog.toml + maturity rungs
  caps.py emit-sdldb --device <id>  # emit the SDL gamecontrollerdb mapping line for a device
  caps.py probe-diff --device <id> --probe <capture.json>   # SPIKE-0 asymmetric diff vs silicon

Schema v2 (tsp-h5ed.46.3, decision D5/D6): `schema_version = 2` unlocks [physical], [model],
[[joints]] + [[joints.postures]], [maturity] and per-screen id/node/panel facts/touch. Every v2
rule's error carries a stable E_* name (see docs/CAPABILITIES-SCHEMA.md); v1 messages are as before.
"""
import sys, os, re, json, struct

try:
    import tomllib  # py3.11+
    def _load(p):
        with open(p, "rb") as f:
            return tomllib.load(f)
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
        def _load(p):
            with open(p, "rb") as f:
                return tomllib.load(f)
    except ModuleNotFoundError:
        sys.stderr.write("FATAL: need Python 3.11+ (tomllib) or the 'tomli' package.\n")
        sys.exit(3)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = ROOT  # this checkout; ROOT moves with --root, REPO_ROOT never does
DEVICES = os.path.join(ROOT, "devices")
SCHEMA_PATH = os.path.join(ROOT, "schemas", "capabilities.schema.json")
CAPS_FILE = "capabilities.toml"

# ---------------------------------------------------------------------------
# The data-driven CI gate matrix (infra-113 §5 / D6, Phase B4). ci-matrix.toml
# is the SINGLE source of truth for WHICH devices the sim CI suites run and each
# device's POSTURE. All three gate workflows (sim-gate, hwprobe-smoke, platform
# sim-descriptor-gate) derive their device rows + posture from it via
# `pf caps matrix` — so adding a device to CI is a DATA change here, never a
# workflow edit ("add a device = add data" — the fleet keystone).
#
#   blocking — a suite failure BLOCKS merge (required-check red). Promotion to
#              blocking is the deliberate data change gated by §5's promotion rules.
#   advisory — a suite failure REPORTS but does not block. This is the DEFAULT for
#              any device that ships a capabilities.toml and carries no explicit
#              matrix entry (D6 auto-join: a new descriptor joins as advisory with
#              zero workflow edits).
#   excluded — deliberately NOT run and NOT gated. MUST be EXPLICIT: a device dir
#              with no capabilities.toml (a build-only profile like a133-owned /
#              sdm845) is a VALIDATION ERROR until it is explicitly excluded here —
#              never a silent skip.
MATRIX_FILE = "ci-matrix.toml"
MATRIX_PATH = os.path.join(ROOT, MATRIX_FILE)
POSTURES = ("blocking", "advisory", "excluded")
DEFAULT_POSTURE = "advisory"  # a capabilities.toml device with no explicit entry auto-joins here

# The device catalog (tsp-h5ed.46.3, decisions D5/D17/D18): one row per retail product mapping
# marketing name + maker code name -> platform id (devices/<dir>) -> model package, with a
# DECLARED maturity rung that may never exceed the rung DERIVED from the artefacts present.
# It is a FILE under devices/, so every devices/ directory scan (here and in profile.py) skips it.
CATALOG_FILE = "catalog.toml"
CATALOG_SCHEMA_PATH = os.path.join(ROOT, "schemas", "device-catalog.schema.json")
RUNGS = ("planned", "model-only", "sim-ready")  # ordered: a later rung implies the earlier ones


def set_root(root):
    """Re-point every tree path at `root` (a fixture laid out like platform/). Schemas fall back
    to this checkout's copies when the fixture carries none."""
    global ROOT, DEVICES, MATRIX_PATH, SCHEMA_PATH, CATALOG_SCHEMA_PATH
    ROOT = os.path.abspath(root)
    DEVICES = os.path.join(ROOT, "devices")
    MATRIX_PATH = os.path.join(ROOT, MATRIX_FILE)
    for name, default in (("capabilities.schema.json", "SCHEMA_PATH"),
                          ("device-catalog.schema.json", "CATALOG_SCHEMA_PATH")):
        own = os.path.join(ROOT, "schemas", name)
        globals()[default] = own if os.path.isfile(own) else os.path.join(REPO_ROOT, "schemas", name)


def _at_repo_root():
    return os.path.realpath(ROOT) == os.path.realpath(REPO_ROOT)

# ---------------------------------------------------------------------------
# Canonical Linux input-event-codes we accept (gamepad/handheld-relevant subset).
# An author may extend these as new hardware lands; an UNKNOWN code is a typo until
# proven otherwise (descriptor = expectation, probe = ground truth).
# ---------------------------------------------------------------------------
BTN_CODES = {
    "BTN_SOUTH", "BTN_EAST", "BTN_NORTH", "BTN_WEST", "BTN_C", "BTN_Z",
    "BTN_A", "BTN_B", "BTN_X", "BTN_Y",
    "BTN_TL", "BTN_TR", "BTN_TL2", "BTN_TR2",
    "BTN_SELECT", "BTN_START", "BTN_MODE", "BTN_THUMBL", "BTN_THUMBR",
    "BTN_THUMB", "BTN_TRIGGER",
    "BTN_DPAD_UP", "BTN_DPAD_DOWN", "BTN_DPAD_LEFT", "BTN_DPAD_RIGHT",
}
KEY_CODES = {
    "KEY_HOMEPAGE", "KEY_HOME", "KEY_BACK", "KEY_MENU", "KEY_POWER",
    "KEY_VOLUMEUP", "KEY_VOLUMEDOWN", "KEY_ESC", "KEY_ENTER",
}
ABS_CODES = {
    "ABS_X", "ABS_Y", "ABS_Z", "ABS_RX", "ABS_RY", "ABS_RZ",
    "ABS_HAT0X", "ABS_HAT0Y", "ABS_HAT1X", "ABS_HAT1Y",
    "ABS_THROTTLE", "ABS_RUDDER", "ABS_GAS", "ABS_BRAKE",
}
FF_CODES = {
    "FF_RUMBLE", "FF_PERIODIC", "FF_CONSTANT", "FF_SPRING", "FF_FRICTION",
    "FF_DAMPER", "FF_INERTIA", "FF_RAMP",
}
ALL_INPUT_CODES = BTN_CODES | KEY_CODES | ABS_CODES
# EV_SW codes a joint may emit as a threshold switch (schema v2 [[joints]].switches). Kept OUT of
# ALL_INPUT_CODES: switch-type [[inputs]] rows wait for the synthesiser's EV_SW support (D8).
SW_CODES = {
    "SW_LID", "SW_TABLET_MODE", "SW_HEADPHONE_INSERT", "SW_MICROPHONE_INSERT", "SW_DOCK",
    "SW_LINEOUT_INSERT", "SW_JACK_PHYSICAL_INSERT", "SW_KEYPAD_SLIDE", "SW_FRONT_PROXIMITY",
    "SW_ROTATE_LOCK", "SW_MUTE_DEVICE", "SW_MACHINE_COVER",
}

# ---------------------------------------------------------------------------
# Schema v2 (tsp-h5ed.46.3). schema_version absent = 1. These keys are only legal at v2, so a v1
# descriptor (every one shipped before v2, and every collector-emitted candidate) is untouched.
# ---------------------------------------------------------------------------
SCHEMA_VERSION_MAX = 2
V2_TOP_KEYS = ("physical", "model", "joints", "maturity")
V2_SCREEN_KEYS = ("id", "node", "panel_px", "fourcc", "diagonal_in", "active_mm", "touch")
V2_SENSOR_KINDS = ("hinge_angle",)
JOINT_UNITS = {"hinge": "deg", "swivel": "deg", "slide": "mm"}  # documented; units follow kind


# ---------------------------------------------------------------------------
# Minimal JSON-Schema engine (Draft-2020-12 SUBSET: exactly the keywords the
# shipped schema uses). Returns a list of human-readable error strings.
# ---------------------------------------------------------------------------
def _typ_ok(inst, t):
    if t == "object":  return isinstance(inst, dict)
    if t == "array":   return isinstance(inst, list)
    if t == "string":  return isinstance(inst, str)
    if t == "boolean": return isinstance(inst, bool)
    if t == "integer": return isinstance(inst, int) and not isinstance(inst, bool)
    if t == "number":  return isinstance(inst, (int, float)) and not isinstance(inst, bool)
    return True


def _resolve_ref(root, ref):
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported $ref (only local '#/...' supported): {ref}")
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _jschema(inst, schema, root, path, errs):
    if "$ref" in schema:
        _jschema(inst, _resolve_ref(root, schema["$ref"]), root, path, errs)
        return
    t = schema.get("type")
    if t is not None and not _typ_ok(inst, t):
        errs.append(f"{path or '<root>'}: expected {t}, got {type(inst).__name__}")
        return  # type wrong -> downstream checks are noise
    if "enum" in schema and inst not in schema["enum"]:
        errs.append(f"{path}: {inst!r} not in {schema['enum']}")
    if isinstance(inst, str):
        if "pattern" in schema and not re.search(schema["pattern"], inst):
            errs.append(f"{path}: {inst!r} does not match /{schema['pattern']}/")
        if "minLength" in schema and len(inst) < schema["minLength"]:
            errs.append(f"{path}: string shorter than minLength {schema['minLength']}")
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            errs.append(f"{path}: {inst} < minimum {schema['minimum']}")
        if "maximum" in schema and inst > schema["maximum"]:
            errs.append(f"{path}: {inst} > maximum {schema['maximum']}")
    if isinstance(inst, dict):
        for r in schema.get("required", []):
            if r not in inst:
                errs.append(f"{path}: missing required key '{r}'")
        props = schema.get("properties", {})
        addl = schema.get("additionalProperties", True)
        for k, v in inst.items():
            kpath = f"{path}.{k}" if path else k
            if k in props:
                _jschema(v, props[k], root, kpath, errs)
            elif isinstance(addl, dict):
                _jschema(v, addl, root, kpath, errs)
            elif addl is False:
                errs.append(f"{kpath}: unknown key (additionalProperties=false)")
    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            errs.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(inst) > schema["maxItems"]:
            errs.append(f"{path}: more than maxItems {schema['maxItems']}")
        items = schema.get("items")
        if items is not None:
            for i, el in enumerate(inst):
                _jschema(el, items, root, f"{path}[{i}]", errs)


def schema_errors(data, schema):
    errs = []
    _jschema(data, schema, schema, "", errs)
    return errs


# ---------------------------------------------------------------------------
# PNG dimension read (stdlib, IHDR chunk) — for skin-bounds checks.
# ---------------------------------------------------------------------------
def png_size(path):
    try:
        with open(path, "rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


# ---------------------------------------------------------------------------
# glTF 2.0 binary (.glb) read (stdlib) — the node names a [model] binds to. Structural only: the
# Khronos validator owns full glTF conformance (D4); this proves the file is a glb whose JSON
# chunk parses and yields the node table.
# ---------------------------------------------------------------------------
def _glb_json(path):
    """Return the parsed JSON chunk of a .glb, or an error string."""
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except OSError:
        return "file not found"
    if len(blob) < 20 or blob[:4] != b"glTF":
        return "not a glTF binary (bad magic)"
    version, total = struct.unpack_from("<II", blob, 4)
    if version != 2:
        return f"glTF container version {version}, need 2"
    if total != len(blob):
        return f"header length {total} != file size {len(blob)} (truncated or padded)"
    clen, ctype = struct.unpack_from("<II", blob, 12)
    if ctype != 0x4E4F534A or 20 + clen > len(blob):
        return "first chunk is not a complete JSON chunk"
    try:
        gl = json.loads(blob[20:20 + clen])
    except ValueError as e:
        return f"JSON chunk does not parse: {e}"
    if not isinstance(gl, dict) or gl.get("asset", {}).get("version") != "2.0":
        return "asset.version is not \"2.0\""
    return gl


def glb_node_names(path):
    """Set of node names in a .glb, or an error string."""
    gl = _glb_json(path)
    if isinstance(gl, str):
        return gl
    return {n.get("name") for n in gl.get("nodes", []) if isinstance(n, dict) and n.get("name")}


# ---------------------------------------------------------------------------
# Semantic checks (what JSON-Schema cannot express: the device.id JOIN, code
# membership, ev_type/kind/code coherence, range sanity, geometry coherence,
# skin bounds, reference integrity). Returns (errors, warnings).
# ---------------------------------------------------------------------------
def _axis_ok(name, ax, where, errs):
    lo, hi = ax.get("min"), ax.get("max")
    if lo is not None and hi is not None and lo > hi:
        errs.append(f"{where}: {name} range min ({lo}) > max ({hi})")
    flat = ax.get("flat")
    if flat is not None and lo is not None and hi is not None and flat > (hi - lo):
        errs.append(f"{where}: {name} flat ({flat}) exceeds span ({hi - lo})")


def semantic_errors(dev_id, data):
    errs, warns = [], []
    ident = data.get("identity", {})

    # 1) device.id JOIN — the ONE cross-check against the build profile.
    did = ident.get("id")
    if did != dev_id:
        errs.append(f"identity.id '{did}' != device directory '{dev_id}'")
    prof = os.path.join(DEVICES, dev_id, "profile.toml")
    if not os.path.isfile(prof):
        errs.append(f"device.id join: no sibling profile.toml at devices/{dev_id}/")
    else:
        try:
            pid = _load(prof).get("device", {}).get("id")
            if pid != did:
                errs.append(f"device.id join: profile.toml [device].id '{pid}' != identity.id '{did}'")
        except Exception as e:
            errs.append(f"device.id join: cannot parse devices/{dev_id}/profile.toml: {e}")

    # 2) inputs — codes known, ev_type/kind/code coherent, ranges sane, ids unique.
    seen_input_ids = set()
    for inp in data.get("inputs", []):
        iid = inp.get("id", "?")
        where = f"input '{iid}'"
        if iid in seen_input_ids:
            errs.append(f"{where}: duplicate input id")
        seen_input_ids.add(iid)
        evt = inp.get("ev_type")
        codes = [c for c in inp.get("code", "").split(",") if c]
        for c in codes:
            if c not in ALL_INPUT_CODES:
                errs.append(f"{where}: unknown ev code '{c}'")
                continue
            if evt == "EV_KEY" and not (c.startswith("BTN_") or c.startswith("KEY_")):
                errs.append(f"{where}: ev_type EV_KEY but code '{c}' is not BTN_*/KEY_*")
            if evt == "EV_ABS" and not c.startswith("ABS_"):
                errs.append(f"{where}: ev_type EV_ABS but code '{c}' is not ABS_*")
        kind = inp.get("kind")
        if kind == "hat" and len(codes) != 2:
            errs.append(f"{where}: kind=hat needs exactly 2 codes (ABS_HAT0X,ABS_HAT0Y)")
        if kind == "stick":
            if len(codes) != 2:
                errs.append(f"{where}: kind=stick needs exactly 2 codes (ABS_X,ABS_Y)")
            if "x" not in inp or "y" not in inp:
                warns.append(f"{where}: kind=stick without per-axis x/y ranges")
        if kind in ("button", "stick-click") and len(codes) != 1:
            errs.append(f"{where}: kind={kind} needs exactly 1 code")
        if kind == "stick-click" and codes and codes[0] not in ("BTN_THUMBL", "BTN_THUMBR"):
            warns.append(f"{where}: kind=stick-click code '{codes[0]}' is not BTN_THUMBL/THUMBR")
        if kind == "trigger" and "range" not in inp:
            warns.append(f"{where}: kind=trigger without a 'range'")
        for axname in ("range", "x", "y"):
            if axname in inp:
                _axis_ok(axname, inp[axname], where, errs)
        # ACTUATOR SEMANTICS vs WIRE FORMAT (tsp-v19s). `kind`/`ev_type`/`code` describe
        # the WIRE (what the kernel emits); `semantics` describes what the physical
        # actuator IS. They diverge on kind=trigger when the wire is analog (ABS_Z/RZ,
        # 0..255) but the actuator is a binary switch that fires endpoints only (TrimUI
        # 5040/5050 L2/R2, SPIKE-0 tsp-9sx.1). Restrict the annotation to kind=trigger:
        # every other kind's semantics is unambiguous from the wire (button/stick-click
        # = binary; stick = analog; hat = enum), so allowing it there is only a footgun.
        sem = inp.get("semantics")
        if sem is not None and kind != "trigger":
            errs.append(f"{where}: 'semantics' is only meaningful on kind=trigger "
                        f"(this input's kind={kind!r} has an unambiguous wire semantics)")

        # INPUT CLASS + SOURCE (tsp-bwrg.16). Two orthogonal, per-input facts a device with more
        # than one evdev node needs, so a consumer never has to INFER them:
        #   class  = "gamepad" (default) | "system". A `system` control is NOT app-bindable — the
        #            E2 broker must never hand it to an app (VOL±, etc.). It is a POLICY marker on
        #            the honest device description, NOT a reason to omit the row (owner ruling
        #            2026-07-27: describe the whole device; gate access in the broker).
        #   source = the evdev NODE NAME the control lives on. DEFAULT (absent) = the primary
        #            gamepad node, i.e. identity.match.evdev_name. Named explicitly only when the
        #            control is on a DIFFERENT node (the a133 has three: the TRIMUI Player1 gamepad,
        #            the sunxi-keyboard LRADC where VOL± live, and the audiocodec Audio Jack).
        # The FRAME-HONESTY invariant this lane exists to enforce (guards-must-be-shown-to-fail):
        # a `system` control must NAME its node and must NOT claim the primary gamepad node — a
        # system key on the gamepad node would be a device-scoped claim from node-scoped evidence,
        # the exact defect that shipped "the device has EXACTLY these controls and NOTHING ELSE".
        cls = inp.get("class")
        src_node = inp.get("source")
        primary_node = ident.get("match", {}).get("evdev_name")
        if cls == "system":
            if src_node is None:
                errs.append(f"{where}: class=system requires an explicit 'source' (a system key "
                            f"is not a primary-gamepad-node control — name its evdev node)")
            elif primary_node is not None and src_node == primary_node:
                errs.append(f"{where}: class=system claims the primary gamepad node "
                            f"'{primary_node}' as its source — a system control does not live on "
                            f"the gamepad node; name its real node (e.g. 'sunxi-keyboard')")

    # 2b) accept_default hint (if present) must reference a real input id.
    accept = data.get("accept_default")
    if accept is not None and accept not in seen_input_ids:
        errs.append(f"accept_default '{accept}' is not an input id")

    # 3) sensors / actuators — unique ids, actuator code membership, IIO-kind→iio_device.
    for section, codes_ok in (("sensors", None), ("actuators", FF_CODES)):
        seen = set()
        for row in data.get(section, []):
            rid = row.get("id", "?")
            if rid in seen:
                errs.append(f"{section} '{rid}': duplicate id")
            seen.add(rid)
            if codes_ok is not None and "code" in row and row["code"] not in codes_ok:
                errs.append(f"{section} '{rid}': unknown FF code '{row['code']}'")
            # IIO-backed sensor kinds must declare their iio_device path (the schema-required
            # invariant before gnss/gps landed). gnss/gps are OMITTED from this set because
            # they aren't IIO devices (gpsd/NMEA/CUSE stream, not iio sysfs) — presence is
            # what matters, not the source path — see tsp-9sx.6.
            if section == "sensors" and row.get("kind") in ("accel", "gyro", "mag", "accel+gyro", "imu"):
                if not row.get("iio_device"):
                    errs.append(f"sensors '{rid}': kind '{row.get('kind')}' requires iio_device")

    # 4) screens — geometry coherence (logical rotation of the render canvas must
    #    match the declared presentation orientation; catches a forgotten rotation).
    for s in data.get("screens", []):
        role = s.get("role", "?")
        rc = s.get("render_canvas", {})
        w, h, rot, present = rc.get("w"), rc.get("h"), s.get("rotation"), s.get("present")
        if None in (w, h, rot, present):
            continue
        fw, fh = (h, w) if rot in ("cw90", "cw270") else (w, h)
        final = "portrait" if fh > fw else ("landscape" if fw > fh else "square")
        if present != final:
            errs.append(f"screen '{role}': rotation {rot} of canvas {w}x{h} presents {final}, "
                        f"but present={present} (render INTENT incoherent)")

    # 5) skin — body exists, parts/display_rects fit the bezel, references resolve.
    skin = data.get("skin")
    if skin is None:
        warns.append("no [skin] section (required for epic acceptance; OK during early authoring)")
    else:
        body = skin.get("body", "")
        dims = png_size(os.path.join(ROOT, body))
        part_names = set(skin.get("parts", {}).keys())
        if dims is None:
            errs.append(f"skin.body not found or not a PNG: {body}")
        else:
            bw, bh = dims
            lit_body = skin.get("lit_body")
            if lit_body:
                ld = png_size(os.path.join(ROOT, lit_body))
                if ld is None:
                    errs.append(f"skin.lit_body not found or not a PNG: {lit_body}")
                elif ld != (bw, bh):
                    errs.append(f"skin.lit_body dims {ld} != body dims {bw}x{bh}")
            for name, part in skin.get("parts", {}).items():
                if part["x"] + part["w"] > bw or part["y"] + part["h"] > bh:
                    errs.append(f"skin part '{name}' ({part['x']},{part['y']},{part['w']},{part['h']}) "
                                f"exceeds bezel {bw}x{bh}")
                lit = part.get("lit")
                if lit and png_size(os.path.join(ROOT, lit)) is None:
                    warns.append(f"skin part '{name}': lit overlay missing/not-PNG: {lit}")
            for s in data.get("screens", []):
                dr = s.get("display_rect")
                if dr and (dr["x"] + dr["w"] > bw or dr["y"] + dr["h"] > bh):
                    errs.append(f"screen '{s.get('role','?')}': display_rect exceeds bezel {bw}x{bh}")
        for inp in data.get("inputs", []):
            sp = inp.get("skin_part")
            if sp and sp not in part_names:
                errs.append(f"input '{inp.get('id','?')}': skin_part '{sp}' has no [skin.parts] entry")

    # 6) schema v2 (tsp-h5ed.46.3): version gate, then the v2 rules.
    ver = data.get("schema_version", 1)
    if ver > SCHEMA_VERSION_MAX:
        errs.append(f"E_SCHEMA_VERSION schema_version {ver} is newer than this validator "
                    f"supports ({SCHEMA_VERSION_MAX})")
    elif ver < 2:
        for key in v2_keys_used(data):
            errs.append(f"E_V2_AT_V1 {key} is a schema v2 key but schema_version is {ver} "
                        f"(absent = 1): set schema_version = 2")
    else:
        e2, w2 = v2_semantic_errors(data)
        errs += e2
        warns += w2
    return errs, warns


def v2_keys_used(data):
    """Every v2-only key/value present in a descriptor, as human-readable locations."""
    used = [f"[{k}]" for k in V2_TOP_KEYS if k in data]
    for i, s in enumerate(data.get("screens", [])):
        used += [f"screens[{i}].{k}" for k in V2_SCREEN_KEYS if k in s]
    for s in data.get("sensors", []):
        if s.get("kind") in V2_SENSOR_KINDS:
            used.append(f"sensors '{s.get('id', '?')}' kind={s.get('kind')}")
    return used


def screen_ids(data):
    """screens[].id, defaulting to the role (legal only while there is one screen)."""
    return [s.get("id") or s.get("role") for s in data.get("screens", [])]


def model_sha_errors(data):
    """The glb sha lives in skins/<id>/model-render.json (D4), never in [model]. Checked before the
    schema so the author gets the named reason, not just 'unknown key'."""
    model = data.get("model")
    if not isinstance(model, dict):
        return []
    return [f"E_MODEL_SHA [model].{k}: the glb hash belongs in model-render.json (D4, owned by "
            f"the skin drift gate), never in the descriptor" for k in model if "sha" in k.lower()]


def derive_maturity(data):
    """The highest rung a DESCRIPTOR's own content supports (D18):
         sim-ready  — [model] present, every screen names its glTF node and every input its
                      skin_part (the viewer can bind the whole device);
         model-only — [model] present but some screen/input is not bound to the model;
         planned    — no [model]: nothing pfvd can present."""
    if not data.get("model"):
        return "planned"
    bound = (all(s.get("node") for s in data.get("screens", []))
             and all(i.get("skin_part") for i in data.get("inputs", [])))
    return "sim-ready" if bound else "model-only"


def _tiling_errors(where, lo, hi, postures):
    """Postures must tile [lo, hi] in document order: first lo == range lo, each lo == the
    previous hi, last hi == range hi (lo inclusive, hi exclusive; the last hi inclusive)."""
    if not postures:
        return [f"E_POSTURE_TILING {where}: no [[joints.postures]]; a joint without `drive` must "
                f"tile its range [{lo}, {hi}] with postures"]
    out, expect = [], lo
    for p in postures:
        plo, phi = p.get("range", [None, None])
        pw = f"{where} posture '{p.get('id', '?')}'"
        if not plo < phi:
            out.append(f"E_POSTURE_TILING {pw}: range [{plo}, {phi}] needs min < max")
        if plo > expect:
            out.append(f"E_POSTURE_TILING {pw}: gap [{expect}, {plo}) is covered by no posture")
        elif plo < expect:
            out.append(f"E_POSTURE_TILING {pw}: starts at {plo}, overlapping the previous posture "
                       f"(which ends at {expect}); postures are ordered and non-overlapping")
        expect = phi
    if expect != hi:
        out.append(f"E_POSTURE_TILING {where}: postures end at {expect} but the joint range ends "
                   f"at {hi}")
    return out


def _cycles(edges):
    """Ids on a cycle of a single-successor graph {id: successor id}."""
    on_cycle = set()
    for start in edges:
        seen, cur = [], start
        while cur in edges and cur not in seen:
            seen.append(cur)
            cur = edges[cur]
        if cur in seen:
            on_cycle.update(seen[seen.index(cur):])
    return sorted(on_cycle)


def v2_semantic_errors(data):
    """Schema v2 rules (tsp-h5ed.46.3). Every error starts with its E_* rule name."""
    errs, warns = [], []
    primary_node = data.get("identity", {}).get("match", {}).get("evdev_name")
    screens = data.get("screens", [])
    inputs = data.get("inputs", [])
    sids = screen_ids(data)
    input_ids = {i.get("id") for i in inputs}

    # Screens: today's consumers index screens[0] as THE screen, so the primary is first and
    # unique; postures name screens, so ids are unique and explicit once there are two.
    roles = [s.get("role") for s in screens]
    if roles.count("primary") != 1:
        errs.append(f"E_SCREEN_PRIMARY exactly one screen must be role=primary "
                    f"(found {roles.count('primary')})")
    elif roles[0] != "primary":
        errs.append("E_SCREEN_PRIMARY the primary screen must be screens[0] (consumers index "
                    "screens[0] as the primary)")
    if len(screens) > 1:
        missing = [i for i, s in enumerate(screens) if "id" not in s]
        if missing:
            errs.append(f"E_SCREEN_ID screens{missing} need an 'id' (required once a device has "
                        f"more than one screen)")
    dups = sorted({x for x in sids if x is not None and sids.count(x) > 1})
    if dups:
        errs.append(f"E_SCREEN_ID duplicate screen id(s): {', '.join(dups)}")
    for s, sid in zip(screens, sids):
        t = s.get("touch")
        if not t:
            continue
        where = f"screen '{sid}' touch"
        if primary_node is not None and t.get("source") == primary_node:
            errs.append(f"E_SCREEN_TOUCH {where}: source '{primary_node}' is the primary gamepad "
                        f"node; a touchscreen is its own evdev node")
        if t.get("protocol") == "st" and "slots" in t:
            errs.append(f"E_SCREEN_TOUCH {where}: 'slots' is only meaningful for protocol=mt-b")
        axis_errs = []
        for ax in ("x", "y", "pressure"):
            if ax in t:
                _axis_ok(ax, t[ax], where, axis_errs)
        errs += [f"E_SCREEN_TOUCH {e}" for e in axis_errs]

    # [physical]: body envelope (per-panel facts live on [[screens]]).
    phys = data.get("physical")
    if phys:
        env = phys.get("envelope_mm", {})
        bad = [k for k in ("w", "h", "d") if not env.get(k, 0) > 0]
        if bad:
            errs.append(f"E_PHYSICAL [physical].envelope_mm {', '.join(bad)} must be > 0 mm")
        if "mass_g" in phys and not phys["mass_g"] > 0:
            errs.append("E_PHYSICAL [physical].mass_g must be > 0 (omit it when unmeasured)")

    # [model]: the glb exists and parses; under pf-semantic-v1 every bound name is a glb node.
    model = data.get("model")
    glb_nodes = None
    if model:
        glb = model.get("glb", "")
        gl = _glb_json(os.path.join(ROOT, glb))
        if isinstance(gl, str):
            errs.append(f"E_MODEL_GLB [model].glb '{glb}': {gl}")
        else:
            names = [n.get("name") for n in gl.get("nodes", []) if isinstance(n, dict)]
            glb_nodes = set(names)
            twice = sorted({n for n in names if n and names.count(n) > 1})
            if twice:
                errs.append(f"E_MODEL_NODE [model].glb '{glb}': node name(s) {', '.join(twice)} "
                            f"occur more than once (a binding must resolve to one node)")
        src = model.get("source")
        if src is not None and not os.path.isdir(os.path.join(ROOT, src)):
            errs.append(f"E_MODEL_SOURCE [model].source '{src}' is not a model package directory")
    if glb_nodes is not None:
        wanted = ([(i.get("skin_part"), f"input '{i.get('id')}' skin_part") for i in inputs]
                  + [(s.get("node"), f"screen '{sid}' node") for s, sid in zip(screens, sids)]
                  + [(j.get("node"), f"joint '{j.get('id')}' node") for j in data.get("joints", [])])
        for name, what in wanted:
            if name and name not in glb_nodes:
                errs.append(f"E_MODEL_NODE {what} '{name}' is not a node in [model].glb")

    # [[joints]] pass 1: per-joint facts.
    sensors = {s.get("id"): s for s in data.get("sensors", [])}
    joints = data.get("joints", [])
    by_id, node_owner = {}, {}
    for j in joints:
        jid = j.get("id", "?")
        where = f"joint '{jid}'"
        if jid in by_id:
            errs.append(f"E_JOINT_DUPLICATE {where}: duplicate joint id")
        else:
            by_id[jid] = j
        node = j.get("node")
        if node in node_owner and node_owner[node] != jid:
            errs.append(f"E_JOINT_DUPLICATE {where}: pivot node '{node}' is already joint "
                        f"'{node_owner[node]}'s")
        node_owner.setdefault(node, jid)
        if model and node != f"pivot_{jid}":
            errs.append(f"E_JOINT_NODE {where}: node '{node}' must be 'pivot_{jid}' under "
                        f"[model].naming = pf-semantic-v1")
        if all(a == 0 for a in j.get("axis", [])):
            errs.append(f"E_JOINT_AXIS {where}: axis is the zero vector")
        sname = j.get("sensor")
        if sname is not None:
            if sname not in sensors:
                errs.append(f"E_JOINT_REF {where}: sensor '{sname}' is not a [[sensors]] id")
            elif sensors[sname].get("kind") != "hinge_angle":
                errs.append(f"E_JOINT_REF {where}: sensor '{sname}' is kind="
                            f"{sensors[sname].get('kind')}, a joint sensor must be kind=hinge_angle")
        lo, hi = j.get("range", [0, 0])
        if not lo < hi:
            errs.append(f"E_JOINT_RANGE {where}: range [{lo}, {hi}] needs min < max")
            continue  # every check below is relative to the range
        for key in ("rest", "default"):
            if key in j and not lo <= j[key] <= hi:
                errs.append(f"E_JOINT_RANGE {where}: {key} {j[key]} outside range [{lo}, {hi}]")
        for d in j.get("detents", []):
            if not lo <= d <= hi:
                errs.append(f"E_JOINT_RANGE {where}: detent {d} outside range [{lo}, {hi}]")
        for sw in j.get("switches", []):
            sw_where = f"{where} switch {sw.get('code')}"
            if sw.get("code") not in SW_CODES:
                errs.append(f"E_JOINT_SWITCH {sw_where}: not a known EV_SW code "
                            f"({', '.join(sorted(SW_CODES))})")
            if primary_node is not None and sw.get("source") == primary_node:
                errs.append(f"E_JOINT_SWITCH {sw_where}: source '{primary_node}' is the primary "
                            f"gamepad node; name the switch's own evdev node")
            alo, ahi = sw.get("active", [lo, hi])
            if not (lo <= alo <= ahi <= hi):
                errs.append(f"E_JOINT_SWITCH {sw_where}: active [{alo}, {ahi}] is not an "
                            f"ordered sub-range of the joint range [{lo}, {hi}]")
        postures = j.get("postures", [])
        if "drive" in j:
            if postures:
                errs.append(f"E_JOINT_DRIVE {where}: a driven joint follows another joint and "
                            f"has no postures of its own")
        else:
            errs += _tiling_errors(where, lo, hi, postures)
        seen_p = set()
        for p in postures:
            pw = f"{where} posture '{p.get('id', '?')}'"
            if p.get("id") in seen_p:
                errs.append(f"E_POSTURE_DUPLICATE {pw}: duplicate posture id")
            seen_p.add(p.get("id"))
            for s in p.get("active_screens", []):
                if s not in sids:
                    errs.append(f"E_POSTURE_REF {pw}: active_screens '{s}' is not a screen id")
            for i in p.get("reachable_inputs", []):
                if i not in input_ids:
                    errs.append(f"E_POSTURE_REF {pw}: reachable_inputs '{i}' is not an input id")
            for s in p.get("screen_rotation", {}):
                if s not in sids:
                    errs.append(f"E_POSTURE_REF {pw}: screen_rotation key '{s}' is not a screen id")

    # [[joints]] pass 2: references between joints (parent chains, drive coupling), acyclic.
    parents, drivers = {}, {}
    for j in joints:
        jid = j.get("id", "?")
        where = f"joint '{jid}'"
        par = j.get("parent")
        if par is not None:
            if par == jid or par not in by_id:
                errs.append(f"E_JOINT_REF {where}: parent '{par}' is not another joint id")
            else:
                parents[jid] = par
        drv = j.get("drive")
        if drv is None:
            continue
        src = drv.get("joint")
        if src == jid or src not in by_id:
            errs.append(f"E_JOINT_DRIVE {where}: drive.joint '{src}' is not another joint id")
            continue
        drivers[jid] = src
        pts = drv.get("map", [])
        xs = [p[0] for p in pts]
        if any(b <= a for a, b in zip(xs, xs[1:])):
            errs.append(f"E_JOINT_DRIVE {where}: drive.map inputs {xs} must strictly increase")
        slo, shi = by_id[src].get("range", [0, 0])
        lo, hi = j.get("range", [0, 0])
        for x, y in pts:
            if slo < shi and not slo <= x <= shi:
                errs.append(f"E_JOINT_DRIVE {where}: drive.map input {x} outside joint '{src}' "
                            f"range [{slo}, {shi}]")
            if lo < hi and not lo <= y <= hi:
                errs.append(f"E_JOINT_DRIVE {where}: drive.map output {y} outside this joint's "
                            f"range [{lo}, {hi}]")
    loop = _cycles(parents)
    if loop:
        errs.append(f"E_JOINT_REF joints {', '.join(loop)}: parent chain is a cycle")
    loop = _cycles(drivers)
    if loop:
        errs.append(f"E_JOINT_DRIVE joints {', '.join(loop)}: drive coupling is a cycle")

    # [maturity]: the declared rung may not exceed what the descriptor's content supports.
    declared = data.get("maturity", {}).get("declared")
    if declared in RUNGS:
        derived = derive_maturity(data)
        if RUNGS.index(declared) > RUNGS.index(derived):
            errs.append(f"E_MATURITY_EXCEEDS [maturity] declared '{declared}' exceeds the derived "
                        f"rung '{derived}' (sim-ready needs [model] plus a node for every screen "
                        f"and a skin_part for every input)")
    return errs, warns


# ---------------------------------------------------------------------------
# SDL gamecontrollerdb emit (tsp-9sx.4): the descriptor is ALSO the single source
# for the SDL3 gamepad mapping — no hand-maintained second file. Keyed by numeric
# evdev code value so either name spelling (BTN_A or BTN_SOUTH) yields the canonical
# mapping. Non-gamepad keys (e.g. KEY_HOMEPAGE on the system-key node) are excluded.
# ---------------------------------------------------------------------------
CODE_VAL = {
    "BTN_A": 0x130, "BTN_SOUTH": 0x130, "BTN_B": 0x131, "BTN_EAST": 0x131,
    "BTN_C": 0x132, "BTN_X": 0x133, "BTN_NORTH": 0x133, "BTN_Y": 0x134, "BTN_WEST": 0x134,
    "BTN_Z": 0x135, "BTN_TL": 0x136, "BTN_TR": 0x137, "BTN_TL2": 0x138, "BTN_TR2": 0x139,
    "BTN_SELECT": 0x13a, "BTN_START": 0x13b, "BTN_MODE": 0x13c,
    "BTN_THUMBL": 0x13d, "BTN_THUMBR": 0x13e,
}
SDL_BTN_FIELD = {
    0x130: "a", 0x131: "b", 0x133: "x", 0x134: "y", 0x136: "leftshoulder",
    0x137: "rightshoulder", 0x13a: "back", 0x13b: "start", 0x13c: "guide",
    0x13d: "leftstick", 0x13e: "rightstick",
    # BTN_TL2/BTN_TR2: SDL allows a button to drive the trigger field (`lefttrigger:bN`) ->
    # full-press reads 0/32767. Kept for descriptors that genuinely emit these codes; the
    # TrimUI 5040/5050 pads do NOT (SPIKE-0 on-silicon 2026-07-11: no TL2/TR2 advertised,
    # L2/R2 fire the ABS_Z/ABS_RZ axes -> those descriptors emit a2/a5).
    0x138: "lefttrigger", 0x139: "righttrigger",
}
SDL_AXIS = {  # ABS code -> (SDL axis index, SDL field)
    "ABS_X": (0, "leftx"), "ABS_Y": (1, "lefty"), "ABS_Z": (2, "lefttrigger"),
    "ABS_RX": (3, "rightx"), "ABS_RY": (4, "righty"), "ABS_RZ": (5, "righttrigger"),
}
FIELD_ORDER = ["a", "b", "x", "y", "back", "guide", "start", "leftshoulder", "rightshoulder",
               "leftstick", "rightstick", "dpup", "dpdown", "dpleft", "dpright",
               "leftx", "lefty", "rightx", "righty", "lefttrigger", "righttrigger"]
SDL_FIELDS = set(FIELD_ORDER)


def build_sdldb_mapping(data):
    """Return (guid, name, {field: source}) derived from the descriptor's inputs."""
    ident = data.get("identity", {})
    guid, name = ident.get("sdl_guid", ""), ident.get("model", "")
    mapping = {}
    # Buttons: only true gamepad BTN_* codes; index = rank by ascending evdev value.
    # class=system rows (VOL±, etc.) are NEVER gamepad bindings — skip them so a system key
    # can never be synthesised into the SDL gamepad mapping (tsp-bwrg.16 owner ruling pt 3).
    # (KEY_* codes are already outside CODE_VAL, so this is belt-and-suspenders; it also guards
    # the hypothetical future system control that reuses a BTN_* code.)
    btn_inputs = []
    for inp in data.get("inputs", []):
        if inp.get("class") == "system":
            continue
        codes = [c for c in inp.get("code", "").split(",") if c]
        if inp.get("ev_type") == "EV_KEY" and len(codes) == 1 and codes[0] in CODE_VAL:
            btn_inputs.append(codes[0])
    for idx, code in enumerate(sorted(btn_inputs, key=lambda c: CODE_VAL[c])):
        field = SDL_BTN_FIELD.get(CODE_VAL[code])
        if field:
            mapping[field] = f"b{idx}"
    # Axes + dpad hat.
    for inp in data.get("inputs", []):
        if inp.get("class") == "system":
            continue
        if inp.get("ev_type") != "EV_ABS":
            continue
        codes = [c for c in inp.get("code", "").split(",") if c]
        if inp.get("kind") == "hat":
            mapping.update({"dpup": "h0.1", "dpright": "h0.2", "dpdown": "h0.4", "dpleft": "h0.8"})
        for c in codes:
            if c in SDL_AXIS:
                aidx, field = SDL_AXIS[c]
                mapping[field] = f"a{aidx}"
    return guid, name, mapping


def emit_sdldb(data):
    guid, name, mapping = build_sdldb_mapping(data)
    fields = ",".join(f"{f}:{mapping[f]}" for f in FIELD_ORDER if f in mapping)
    return f"{guid},{name},{fields},platform:Linux,"


def parse_sdldb(line):
    """Offline SDL3-grammar round-trip parser. Returns (guid, name, {field:source})
    or raises ValueError. Mirrors SDL_AddGamepadMapping's grammar closely enough to
    prove the emitted line is well-formed and re-ingestible."""
    parts = [p for p in line.split(",")]
    if len(parts) < 3:
        raise ValueError("too few fields")
    guid, name = parts[0], parts[1]
    if not re.fullmatch(r"[0-9a-f]{32}", guid):
        raise ValueError(f"bad GUID: {guid!r}")
    if not name:
        raise ValueError("empty name")
    out, saw_platform = {}, False
    for tok in parts[2:]:
        if not tok:
            continue
        if ":" not in tok:
            raise ValueError(f"bad token: {tok!r}")
        field, src = tok.split(":", 1)
        if field == "platform":
            saw_platform = True
            continue
        if field not in SDL_FIELDS:
            raise ValueError(f"unknown SDL field: {field!r}")
        if not re.fullmatch(r"b\d+|a\d+|h\d+\.\d+", src):
            raise ValueError(f"bad source for {field}: {src!r}")
        out[field] = src
    if not saw_platform:
        raise ValueError("missing platform:")
    return guid, name, out


def cmd_emit_sdldb(argv):
    dev_id = None
    if len(argv) >= 2 and argv[0] == "--device":
        dev_id = argv[1]
    elif len(argv) == 1:
        dev_id = argv[0]
    if not dev_id:
        sys.stderr.write("emit-sdldb: usage: emit-sdldb --device <id>\n")
        return 2
    cpath = os.path.join(DEVICES, dev_id, CAPS_FILE)
    if not os.path.isfile(cpath):
        sys.stderr.write(f"emit-sdldb: no {CAPS_FILE} for '{dev_id}'\n")
        return 2
    data = _load(cpath)
    line = emit_sdldb(data)
    try:  # self-check: the line must round-trip + the GUID must match the descriptor.
        guid, _, _ = parse_sdldb(line)
        if guid != data.get("identity", {}).get("sdl_guid"):
            raise ValueError("emitted GUID != identity.sdl_guid")
    except ValueError as e:
        sys.stderr.write(f"emit-sdldb: emitted line failed round-trip: {e}\n")
        return 1
    print(line)
    return 0


# ---------------------------------------------------------------------------
# SPIKE-0 (tsp-9sx.1): descriptor <-> evdev-probe ASYMMETRIC diff. descriptor =
# EXPECTATION, probe = GROUND TRUTH. RULE: every descriptor code MUST be advertised
# by the probe (descriptor codes SUBSET-OF probe codes) -> ERROR if not. Codes the
# probe advertises but the descriptor omits are EXPECTED (the shared Xbox-360 HID
# superset) -> INFO, never an error. absinfo (min/max) mismatch -> WARN (reconcile
# the descriptor to silicon). Feed it a capture from regression/caps/evdev-probe.py.
# ---------------------------------------------------------------------------
def probe_diff(dev_id, capture):
    errs, warns, infos = [], [], []
    cpath = os.path.join(DEVICES, dev_id, CAPS_FILE)
    if not os.path.isfile(cpath):
        return [f"{dev_id}: no {CAPS_FILE}"], [], []
    data = _load(cpath)
    nodes = capture.get("nodes", [])
    ident = data.get("identity", {})
    match = ident.get("match", {})

    # Find the gamepad node (by evdev name; vid/pid if present in the capture).
    pad = None
    for n in nodes:
        if n.get("name") == match.get("evdev_name"):
            if match.get("vid") and n.get("vendor") and n["vendor"] != match["vid"]:
                continue
            pad = n
            break
    if pad is None:
        errs.append(f"{dev_id}: no probe node matches identity.match.evdev_name "
                    f"'{match.get('evdev_name')}'")
        return errs, warns, infos

    pad_keys = set(pad.get("keys", []))
    pad_abs = pad.get("abs", {})
    all_keys = set()
    for n in nodes:
        all_keys.update(n.get("keys", []))

    # BTN_* comparison is by CODE VALUE, not name spelling (tsp-ozbp.14). The kernel gives the
    # four face buttons two names for one number -- BTN_A==BTN_SOUTH 0x130, BTN_B==BTN_EAST
    # 0x131, BTN_X==BTN_NORTH 0x133, BTN_Y==BTN_WEST 0x134 -- and the two sides of this diff
    # legitimately choose different ones: a probe capture names a code via evdev-probe.py's
    # alias-preferred table (0x134 -> "BTN_Y"), while a descriptor may spell the same code
    # positionally ("BTN_WEST") because its `id` IS the position. Comparing the strings makes a
    # descriptor that is CORRECT to the byte look absent from the probe, which is a false ERROR
    # on the exact axis this project just spent a bug on. Resolve both sides through CODE_VAL and
    # compare numbers; names outside the table (KEY_*, anything new) fall back to the name so an
    # unknown code can never silently compare equal.
    def _key_id(name):
        """A comparable identity for an EV_KEY name: its numeric code if known, else the name."""
        return CODE_VAL.get(name, name)

    pad_key_ids = {_key_id(k) for k in pad_keys}

    used_keys, used_abs = set(), set()
    for inp in data.get("inputs", []):
        iid = inp.get("id", "?")
        codes = [c for c in inp.get("code", "").split(",") if c]
        for c in codes:
            if c.startswith("ABS_"):
                used_abs.add(c)
                if c not in pad_abs:
                    errs.append(f"{dev_id}: input '{iid}' claims {c} but the gamepad node "
                                f"does not advertise it (descriptor not subset-of probe)")
            elif c.startswith("BTN_"):
                used_keys.add(c)
                if _key_id(c) not in pad_key_ids:
                    errs.append(f"{dev_id}: input '{iid}' claims {c} but the gamepad node "
                                f"does not advertise it")
            elif c.startswith("KEY_"):
                if c not in all_keys:
                    errs.append(f"{dev_id}: input '{iid}' claims system key {c} but NO probe "
                                f"node advertises it")
        # absinfo reconcile (min/max) for ranged inputs
        axis_map = []
        if inp.get("kind") == "stick" and len(codes) == 2:
            axis_map = [(codes[0], inp.get("x")), (codes[1], inp.get("y"))]
        elif inp.get("kind") == "trigger" and len(codes) == 1:
            axis_map = [(codes[0], inp.get("range"))]
        for code, ax in axis_map:
            if ax and code in pad_abs:
                p = pad_abs[code]
                for k in ("min", "max"):
                    if k in ax and p.get(k) is not None and ax[k] != p[k]:
                        # WARN, deliberately NOT ERROR (tsp-ozbp.13): probe-diff compares the
                        # descriptor against ONE live unit's EVIOCGABS, where per-unit min/max
                        # variation is expected (a stick that doesn't quite reach 4095, a slightly
                        # shifted rest). A hard ERROR here would false-fail on normal unit variance.
                        # The DECLARED range is instead pinned deterministically + unit-independently
                        # by the shipped-descriptor self-test (regression/caps/test_caps.py), which is
                        # where a signed16↔unsigned-12bit regression is caught. Keep this a reconcile
                        # HINT against silicon, not the range guard.
                        warns.append(f"{dev_id}: input '{iid}' {code}.{k}={ax[k]} but probe "
                                     f"reads {p[k]} (reconcile descriptor to ground truth)")

    # Extra advertised codes = expected X360 superset (INFO, not error). Value-compared for the
    # same reason as above, so a positionally-spelled descriptor row does not make the probe's
    # alias spelling of the SAME code look like an extra one.
    used_key_ids = {_key_id(k) for k in used_keys}
    extra_keys = sorted(
        k for k in pad_keys if k.startswith("BTN_") and _key_id(k) not in used_key_ids
    )
    if extra_keys:
        infos.append(f"{dev_id}: gamepad advertises {len(extra_keys)} BTN_* code(s) the "
                     f"descriptor omits (expected HID superset): {', '.join(extra_keys)}")
    extra_abs = sorted(a for a in pad_abs if a not in used_abs)
    if extra_abs:
        infos.append(f"{dev_id}: gamepad advertises ABS code(s) the descriptor omits: "
                     f"{', '.join(extra_abs)}")
    # Sensors are IIO, not evdev — flag for separate SPIKE-0 confirmation.
    for s in data.get("sensors", []):
        infos.append(f"{dev_id}: sensor '{s.get('id')}' (iio {s.get('iio_device')}) is IIO, "
                     f"not evdev — confirm it BINDS separately (R3 hazard)")
    return errs, warns, infos


def cmd_probe_diff(argv):
    dev_id, probe_path = None, None
    i = 0
    while i < len(argv):
        if argv[i] == "--device" and i + 1 < len(argv):
            dev_id = argv[i + 1]; i += 2
        elif argv[i] == "--probe" and i + 1 < len(argv):
            probe_path = argv[i + 1]; i += 2
        else:
            i += 1
    if not dev_id or not probe_path:
        sys.stderr.write("probe-diff: usage: probe-diff --device <id> --probe <capture.json>\n")
        return 2
    try:
        with open(probe_path) as f:
            capture = json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write(f"probe-diff: cannot read capture {probe_path}: {e}\n")
        return 2
    errs, warns, infos = probe_diff(dev_id, capture)
    for m in infos:
        print(f"INFO  {m}")
    for m in warns:
        print(f"WARN  {m}")
    for m in errs:
        print(f"ERROR {m}")
    if not errs:
        print(f"OK    {dev_id}: descriptor codes are a subset of the probe (asymmetric rule)")
    return 1 if errs else 0


# ---------------------------------------------------------------------------
# CI gate matrix (infra-113 B4 / D6): derive device rows + per-device posture
# from ci-matrix.toml, and validate that data for completeness + coherence.
# ---------------------------------------------------------------------------
def _device_dirs():
    """Every subdirectory under devices/ — the full set that MUST be classified."""
    if not os.path.isdir(DEVICES):
        return []
    return sorted(d for d in os.listdir(DEVICES)
                  if os.path.isdir(os.path.join(DEVICES, d)))


def _has_caps(dev_id):
    return os.path.isfile(os.path.join(DEVICES, dev_id, CAPS_FILE))


def load_matrix():
    """Parse ci-matrix.toml -> {device_id: posture}. Returns ({}, None) if the file is
    absent (validation then flags every unclassified dir), or ({}, error) on a parse error."""
    if not os.path.isfile(MATRIX_PATH):
        return {}, None
    try:
        data = _load(MATRIX_PATH)
    except Exception as e:  # noqa: BLE001 — surface any TOML error as a validation error
        return {}, f"cannot parse {MATRIX_FILE}: {e}"
    return dict(data.get("devices", {})), None


def resolve_matrix():
    """Resolve every devices/ dir to a posture.

    Returns rows = [(dev_id, posture)] sorted. Posture is:
      - the explicit ci-matrix value when listed;
      - when ci-matrix.toml is PRESENT: DEFAULT_POSTURE (advisory) for an unlisted
        descriptor'd dir (D6 auto-join), else None (UNCLASSIFIED — a profile-only dir
        with no explicit entry; validate() flags it as a silent-skip error);
      - when ci-matrix.toml is ABSENT (a pre-B4 baked platform pin whose tree predates
        this file): FAIL-CLOSED — every descriptor'd dir defaults to 'blocking' (the
        pre-B4 "every device gates" behavior, so a consumer on a stale pin never SILENTLY
        relaxes a device to non-blocking), profile-only dirs stay None (never ran).
    This makes the three gate workflows robust to the pin cascade: they derive a correct,
    list-free device matrix whether or not the baked/checked platform yet carries the data;
    the a523→advisory relaxation activates only once the consumed pin includes ci-matrix.toml.
    """
    explicit, perr = load_matrix()
    present = os.path.isfile(MATRIX_PATH) and not perr
    unlisted_default = DEFAULT_POSTURE if present else "blocking"
    rows = []
    for d in _device_dirs():
        if d in explicit:
            rows.append((d, explicit[d]))
        elif _has_caps(d):
            rows.append((d, unlisted_default))
        else:
            rows.append((d, None))  # profile-only dir — never silently skipped (flagged when present)
    return rows


def matrix_errors():
    """Validate ci-matrix.toml against the devices/ tree. Returns (errors, warnings).

    Enforces (infra-113 §5): every device dir is EXPLICITLY accounted for (a profile-only
    dir must be excluded — never a silent skip); every posture is legal; a gating posture
    (blocking/advisory) requires a real descriptor; no stale entry points at a missing dir.
    """
    errs, warns = [], []
    if not os.path.isfile(MATRIX_PATH):
        # The platform repo MUST carry the matrix data (infra-113 B4). Its absence is a data
        # error HERE (guards the source repo). Consumers never call validate against a stale
        # baked pin — they call `matrix list`, whose resolve_matrix() fail-closes to blocking.
        return [f"ci-matrix: {MATRIX_FILE} is missing (the data-driven CI gate matrix — "
                f"infra-113 B4 / D6); create it classifying every devices/ directory)"], []
    explicit, perr = load_matrix()
    if perr:
        return [perr], []
    dirs = set(_device_dirs())

    # Stale entries: a matrix row must point at a real devices/<id>/ dir.
    for dev_id, posture in explicit.items():
        if posture not in POSTURES:
            errs.append(f"ci-matrix: device '{dev_id}' has unknown posture {posture!r} "
                        f"(must be one of {', '.join(POSTURES)})")
        if dev_id not in dirs:
            errs.append(f"ci-matrix: entry '{dev_id}' has no devices/{dev_id}/ directory "
                        f"(stale row — remove it or add the device)")

    # Completeness + coherence: every dir classified, gating posture ⇒ descriptor present.
    for d in sorted(dirs):
        posture = explicit.get(d)
        has_caps = _has_caps(d)
        if posture is None:
            if not has_caps:
                errs.append(f"ci-matrix: devices/{d}/ has no {CAPS_FILE} and no explicit "
                            f"posture — classify it (add '{d} = \"excluded\"' for a build-only "
                            f"profile) so it is never a SILENT SKIP")
            # else: descriptor'd + unlisted -> auto-joins as advisory (D6), no error.
        elif posture in ("blocking", "advisory") and not has_caps:
            errs.append(f"ci-matrix: devices/{d}/ posture {posture!r} requires a {CAPS_FILE} "
                        f"but none exists (a gate cannot run a device with no descriptor)")
        elif posture == "excluded" and has_caps:
            warns.append(f"ci-matrix: devices/{d}/ is excluded but ships a {CAPS_FILE} "
                         f"(descriptor present but deliberately not gated — confirm intended)")
    return errs, warns


def cmd_matrix(argv):
    if not argv:
        sys.stderr.write("matrix: usage: matrix {list|validate} [--posture P] [--format tsv|ids]\n")
        return 2
    sub = argv[0]
    rest = argv[1:]
    if sub == "validate":
        errs, warns = matrix_errors()
        for w in warns:
            print(f"WARN  {w}")
        for e in errs:
            print(f"ERROR {e}")
        if not errs:
            rows = [f"{d}={p}" for d, p in resolve_matrix() if p]
            print(f"OK    ci-matrix valid: {', '.join(rows)}")
        return 1 if errs else 0
    if sub == "list":
        posture_filter = None
        fmt = "tsv"
        i = 0
        while i < len(rest):
            if rest[i] == "--posture" and i + 1 < len(rest):
                posture_filter = rest[i + 1]; i += 2
            elif rest[i] == "--format" and i + 1 < len(rest):
                fmt = rest[i + 1]; i += 2
            else:
                sys.stderr.write(f"matrix list: unknown arg {rest[i]!r}\n"); return 2
        if posture_filter is not None and posture_filter not in POSTURES:
            sys.stderr.write(f"matrix list: --posture must be one of {', '.join(POSTURES)}\n")
            return 2
        rows = resolve_matrix()
        if posture_filter is not None:
            ids = [d for d, p in rows if p == posture_filter]
            if fmt == "ids":
                print(" ".join(ids))
            else:
                for d in ids:
                    print(f"{d}\t{posture_filter}")
            return 0
        # No filter: full picture (UNCLASSIFIED rendered explicitly, never hidden).
        if fmt == "ids":
            print(" ".join(d for d, p in rows if p in ("blocking", "advisory")))
        else:
            for d, p in rows:
                print(f"{d}\t{p or 'UNCLASSIFIED'}")
        return 0
    sys.stderr.write(f"matrix: unknown subcommand {sub!r} (use list|validate)\n")
    return 2


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def list_caps_devices():
    if not os.path.isdir(DEVICES):
        return []
    return sorted(d for d in os.listdir(DEVICES)
                  if os.path.isfile(os.path.join(DEVICES, d, CAPS_FILE)))


def validate_one(dev_id, schema):
    cpath = os.path.join(DEVICES, dev_id, CAPS_FILE)
    if not os.path.isfile(cpath):
        return [f"{dev_id}: no {CAPS_FILE} at devices/{dev_id}/"], []
    try:
        data = _load(cpath)
    except Exception as e:
        return [f"{dev_id}: cannot parse {CAPS_FILE}: {e}"], []
    errs = [f"{dev_id}: {e}" for e in model_sha_errors(data) + schema_errors(data, schema)]
    if errs:  # schema must pass before semantic checks are meaningful
        return errs, []
    se, sw = semantic_errors(dev_id, data)
    return [f"{dev_id}: {e}" for e in se], [f"{dev_id}: {w}" for w in sw]


def _read_schema(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write(f"FATAL: cannot read schema {path}: {e}\n")
        return None


# ---------------------------------------------------------------------------
# Device catalog (tsp-h5ed.46.3): devices/catalog.toml. Rung DERIVED per row from the artefacts:
#   sim-ready  — platform_id has a capabilities.toml that validates AND the model package exists;
#   model-only — the model package exists;
#   planned    — neither.
# A row's declared maturity may not exceed its derived rung.
# ---------------------------------------------------------------------------
def catalog_path():
    return os.path.join(DEVICES, CATALOG_FILE)


def catalog_rows(schema):
    """Validate the catalog. Returns (rows, errors, warnings); each row gains 'derived'."""
    path = catalog_path()
    rel = os.path.relpath(path, ROOT)
    try:
        data = _load(path)
    except FileNotFoundError:
        return [], [f"catalog: {rel} is missing"], []
    except Exception as e:  # noqa: BLE001 — any TOML error is a catalog error
        return [], [f"catalog: cannot parse {rel}: {e}"], []
    cschema = _read_schema(CATALOG_SCHEMA_PATH)
    if cschema is None:
        return [], [f"catalog: cannot read {CATALOG_SCHEMA_PATH}"], []
    errs = [f"catalog: {e}" for e in schema_errors(data, cschema)]
    if errs:
        return [], errs, []
    warns, rows, seen = [], [], set()
    referenced = set()
    for row in data.get("devices", []):
        rid = row["id"]
        where = f"catalog '{rid}'"
        if rid in seen:
            errs.append(f"{where}: E_CATALOG_DUPLICATE duplicate product id")
        seen.add(rid)
        plat, pkg = row.get("platform_id"), row.get("package")
        has_desc = has_pkg = False
        if plat is not None:
            referenced.add(plat)
            if not _has_caps(plat):
                errs.append(f"{where}: E_CATALOG_REF platform_id '{plat}' has no "
                            f"devices/{plat}/{CAPS_FILE}")
            else:
                prof = os.path.join(DEVICES, plat, "profile.toml")
                base = _load(prof).get("device", {}).get("base") if os.path.isfile(prof) else None
                if base:
                    errs.append(f"{where}: E_CATALOG_REF platform_id '{plat}' is a build variant "
                                f"of '{base}'; the catalog names base devices only")
                derrs, _ = validate_one(plat, schema)
                has_desc = not derrs
                if derrs:
                    warns.append(f"{where}: platform '{plat}' descriptor does not validate "
                                 f"({len(derrs)} error(s)), so it cannot count as sim-ready")
                else:
                    ident = _load(os.path.join(DEVICES, plat, CAPS_FILE)).get("identity", {})
                    if (ident.get("manufacturer"), ident.get("model")) != (row["manufacturer"], row["name"]):
                        warns.append(f"{where}: manufacturer/name '{row['manufacturer']} "
                                     f"{row['name']}' != descriptor identity '"
                                     f"{ident.get('manufacturer')} {ident.get('model')}'")
        if pkg is not None:
            has_pkg = os.path.isdir(os.path.join(ROOT, pkg))
            if not has_pkg:
                errs.append(f"{where}: E_CATALOG_REF package '{pkg}' is not a directory")
        derived = "sim-ready" if (has_desc and has_pkg) else ("model-only" if has_pkg else "planned")
        if RUNGS.index(row["maturity"]) > RUNGS.index(derived):
            errs.append(f"{where}: E_CATALOG_MATURITY declared '{row['maturity']}' exceeds the "
                        f"derived rung '{derived}' (sim-ready = valid descriptor + model package; "
                        f"model-only = model package)")
        rows.append(dict(row, derived=derived))
    for dev in list_caps_devices():
        if dev not in referenced:
            warns.append(f"catalog: devices/{dev}/{CAPS_FILE} is not the platform_id of any "
                         f"catalog row")
    return rows, errs, warns


def cmd_catalog(argv):
    sub = "list"
    if argv and argv[0] in ("list", "validate"):
        sub, argv = argv[0], argv[1:]
    fmt = "tsv"
    if argv[:1] == ["--format"] and len(argv) == 2 and argv[1] in ("tsv", "json"):
        fmt = argv[1]
    elif argv:
        sys.stderr.write("catalog: usage: catalog [list|validate] [--format tsv|json]\n")
        return 2
    schema = _read_schema(SCHEMA_PATH)
    if schema is None:
        return 3
    rows, errs, warns = catalog_rows(schema)
    if sub == "list":
        cols = ("id", "manufacturer", "name", "code_name", "platform_id", "maturity", "derived")
        if fmt == "json":
            print(json.dumps([{c: r.get(c) for c in cols} for r in rows], indent=2))
        else:
            print("\t".join(cols[:5] + ("declared", "derived")))
            for r in rows:
                print("\t".join(str(r.get(c) or "-") for c in cols))
    for w in warns:
        print(f"WARN  {w}")
    for e in errs:
        print(f"ERROR {e}")
    if sub == "validate" and not errs:
        print(f"OK    catalog: {len(rows)} product(s), declared rungs within derived")
    return 1 if errs else 0


def cmd_validate(argv):
    schema = _read_schema(SCHEMA_PATH)
    if schema is None:
        return 3
    validate_all = not argv or argv[0] == "--all"
    if validate_all:
        targets = list_caps_devices()
        if not targets:
            print("(no capabilities.toml descriptors found)")
    else:
        targets = argv
    total_err = 0
    for d in targets:
        errs, warns = validate_one(d, schema)
        for w in warns:
            print(f"WARN  {w}")
        for e in errs:
            print(f"ERROR {e}")
        if not errs:
            print(f"OK    {d}: capabilities valid")
        total_err += len(errs)
    # --all also validates the CI gate matrix (infra-113 B4): a bad posture, an
    # unclassified device dir, or a gating posture without a descriptor is an error.
    # A --root fixture tree is not a platform checkout: there a missing matrix/catalog is a SKIP.
    if validate_all:
        if not os.path.isfile(MATRIX_PATH) and not _at_repo_root():
            print(f"SKIP  ci-matrix: no {MATRIX_FILE} under --root {ROOT} (fixture tree)")
        else:
            merrs, mwarns = matrix_errors()
            for w in mwarns:
                print(f"WARN  {w}")
            for e in merrs:
                print(f"ERROR {e}")
            if not merrs:
                print("OK    ci-matrix: posture data valid")
            total_err += len(merrs)
        if not os.path.isfile(catalog_path()) and not _at_repo_root():
            print(f"SKIP  catalog: no devices/{CATALOG_FILE} under --root {ROOT} (fixture tree)")
        else:
            rows, cerrs, cwarns = catalog_rows(schema)
            for w in cwarns:
                print(f"WARN  {w}")
            for e in cerrs:
                print(f"ERROR {e}")
            if not cerrs:
                print(f"OK    catalog: {len(rows)} product(s), declared rungs within derived")
            total_err += len(cerrs)
    return 1 if total_err else 0


def main(argv):
    if argv and argv[0].startswith("--root"):
        if argv[0] == "--root" and len(argv) >= 2:
            root, argv = argv[1], argv[2:]
        elif argv[0].startswith("--root="):
            root, argv = argv[0][len("--root="):], argv[1:]
        else:
            sys.stderr.write("caps: --root needs a directory\n")
            return 2
        if not os.path.isdir(os.path.join(root, "devices")):
            sys.stderr.write(f"caps: --root {root} has no devices/ directory\n")
            return 2
        set_root(root)
    if not argv:
        sys.stderr.write(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "catalog":
        return cmd_catalog(argv[1:])
    if cmd == "list":
        print("\n".join(list_caps_devices()))
        return 0
    if cmd == "validate":
        return cmd_validate(argv[1:])
    if cmd == "matrix":
        return cmd_matrix(argv[1:])
    if cmd == "emit-sdldb":
        return cmd_emit_sdldb(argv[1:])
    if cmd == "probe-diff":
        return cmd_probe_diff(argv[1:])
    sys.stderr.write(f"caps: unknown subcommand: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
