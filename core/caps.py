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
  caps.py list                      # device ids that have a capabilities.toml
  caps.py validate <id|--all>       # schema + semantic validation; non-zero exit on error
"""
import sys, os, re, json

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
DEVICES = os.path.join(ROOT, "devices")
SCHEMA_PATH = os.path.join(ROOT, "schemas", "capabilities.schema.json")
CAPS_FILE = "capabilities.toml"

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

    # 3) sensors / actuators — unique ids, actuator code membership.
    for section, codes_ok in (("sensors", None), ("actuators", FF_CODES)):
        seen = set()
        for row in data.get(section, []):
            rid = row.get("id", "?")
            if rid in seen:
                errs.append(f"{section} '{rid}': duplicate id")
            seen.add(rid)
            if codes_ok is not None and "code" in row and row["code"] not in codes_ok:
                errs.append(f"{section} '{rid}': unknown FF code '{row['code']}'")

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
    return errs, warns


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
    errs = [f"{dev_id}: {e}" for e in schema_errors(data, schema)]
    if errs:  # schema must pass before semantic checks are meaningful
        return errs, []
    se, sw = semantic_errors(dev_id, data)
    return [f"{dev_id}: {e}" for e in se], [f"{dev_id}: {w}" for w in sw]


def cmd_validate(argv):
    try:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
    except OSError as e:
        sys.stderr.write(f"FATAL: cannot read schema {SCHEMA_PATH}: {e}\n")
        return 3
    if argv and argv[0] == "--all":
        targets = list_caps_devices()
        if not targets:
            print("(no capabilities.toml descriptors found)")
            return 0
    else:
        targets = argv
        if not targets:
            sys.stderr.write("validate: give a device id or --all\n")
            return 2
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
    return 1 if total_err else 0


def main(argv):
    if not argv:
        sys.stderr.write(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "list":
        print("\n".join(list_caps_devices()))
        return 0
    if cmd == "validate":
        return cmd_validate(argv[1:])
    sys.stderr.write(f"caps: unknown subcommand: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
