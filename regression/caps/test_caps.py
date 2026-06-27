#!/usr/bin/env python3
"""regression/caps/test_caps.py — self-test for core/caps.py (E1 / tsp-9sx.2).

Device-free. Exercises the stdlib JSON-Schema-subset engine + the semantic checks
with a known-good descriptor and a battery of negatives (the bead's negative-test
requirement). When the reference `jsonschema` library is importable, it ALSO asserts
that our engine AGREES with it (both accept / both reject) on every case — so the
hand-rolled subset engine is pinned to the real spec.

Run:  python3 regression/caps/test_caps.py   (exit 0 = all pass)
"""
import os, sys, json, copy, struct, zlib, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CAPS_PY = os.path.join(ROOT, "core", "caps.py")
SCHEMA_PATH = os.path.join(ROOT, "schemas", "capabilities.schema.json")

spec = importlib.util.spec_from_file_location("caps", CAPS_PY)
caps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(caps)

with open(SCHEMA_PATH) as f:
    SCHEMA = json.load(f)

_failures = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        _failures.append(name)


def make_png(path, w, h):
    """Write a minimal valid 8-bit RGB PNG of size w x h."""
    def chunk(typ, data):
        body = typ + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + (b"\x00\x00\x00" * w) for _ in range(h))
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                 + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def valid_descriptor(bezel_path):
    # Shaped like the base a133 (device.id join resolves against the real
    # devices/a133/profile.toml). bezel 600x1200; all rects fit.
    return {
        "identity": {
            "id": "a133", "manufacturer": "TrimUI", "model": "Smart Pro", "codename": "5040",
            "sdl_guid": "030000005e0400008e02000010010000",
            "match": {"evdev_name": "TRIMUI Player1", "vid": "045e", "pid": "028e"},
        },
        "screens": [{
            "role": "primary", "render_canvas": {"w": 1280, "h": 720},
            "present": "portrait", "rotation": "cw90",
            "display_rect": {"x": 40, "y": 60, "w": 520, "h": 1080},
        }],
        "inputs": [
            {"id": "south", "kind": "button", "ev_type": "EV_KEY", "code": "BTN_A", "label": "A", "skin_part": "btn_south"},
            {"id": "dpad", "kind": "hat", "ev_type": "EV_ABS", "code": "ABS_HAT0X,ABS_HAT0Y", "skin_part": "dpad"},
            {"id": "lstick", "kind": "stick", "ev_type": "EV_ABS", "code": "ABS_X,ABS_Y",
             "x": {"min": -32768, "max": 32767, "flat": 1024},
             "y": {"min": -32768, "max": 32767, "flat": 1024}, "skin_part": "stick_l"},
            {"id": "ltrig", "kind": "trigger", "ev_type": "EV_ABS", "code": "ABS_Z",
             "range": {"min": 0, "max": 255, "flat": 0}, "skin_part": "trig_l", "ui": "slider_above"},
        ],
        "actuators": [{"id": "leds", "kind": "led_array", "controller": "sunxi_led", "count": 23}],
        "accept_default": "south",
        "skin": {"body": bezel_path, "parts": {
            "btn_south": {"x": 400, "y": 900, "w": 48, "h": 48},
            "dpad":    {"x": 80,  "y": 880, "w": 120, "h": 120},
            "stick_l": {"x": 120, "y": 1000, "w": 100, "h": 100},
            "trig_l":  {"x": 40,  "y": 120, "w": 40, "h": 140},
        }},
    }


def reference_agrees(data, our_has_errors):
    """If `jsonschema` is importable, return whether it agrees with our SCHEMA verdict.
    (Reference only checks SCHEMA structure, so only call for schema-level cases.)"""
    try:
        import jsonschema
    except ImportError:
        return None
    try:
        jsonschema.validate(data, SCHEMA)
        ref_has_errors = False
    except jsonschema.ValidationError:
        ref_has_errors = True
    return ref_has_errors == our_has_errors


def main():
    tmp = tempfile.mkdtemp()
    bezel = os.path.join(tmp, "bezel.png")
    make_png(bezel, 600, 1200)

    # --- PNG reader ---
    check("png_size reads IHDR dims", caps.png_size(bezel) == (600, 1200))
    check("png_size rejects non-PNG", caps.png_size(SCHEMA_PATH) is None)

    base = valid_descriptor(bezel)

    # --- positive ---
    se = caps.schema_errors(base, SCHEMA)
    check("valid: schema clean", se == [])
    errs, warns = caps.semantic_errors("a133", base)
    check("valid: semantic clean (errors)", errs == [])
    check("valid: semantic clean (warnings)", warns == [])
    ref = reference_agrees(base, our_has_errors=bool(se))
    check("valid: agrees with reference jsonschema", ref in (True, None))

    # --- schema negatives (also cross-checked against reference) ---
    def schema_neg(name, mut):
        d = copy.deepcopy(base); mut(d)
        se = caps.schema_errors(d, SCHEMA)
        check(name + ": schema rejects", len(se) > 0)
        agree = reference_agrees(d, our_has_errors=bool(se))
        check(name + ": agrees with reference", agree in (True, None))

    schema_neg("unknown top-level key", lambda d: d.update(bogus=1))
    schema_neg("unknown input key", lambda d: d["inputs"][0].update(zzz=1))
    schema_neg("missing required input.code", lambda d: d["inputs"][0].pop("code"))
    schema_neg("bad kind enum", lambda d: d["inputs"][0].update(kind="wiggle"))
    schema_neg("bad rotation enum (magic number)", lambda d: d["screens"][0].update(rotation="768"))
    schema_neg("bad sdl_guid pattern", lambda d: d["identity"].update(sdl_guid="nope"))
    schema_neg("empty inputs array", lambda d: d.update(inputs=[]))
    schema_neg("code pattern violation", lambda d: d["inputs"][0].update(code="lowercase_btn"))
    schema_neg("bad label_kind enum", lambda d: d["inputs"][0].update(label_kind="weird"))

    # --- semantic negatives (beyond what JSON-Schema can express) ---
    def sem_neg(name, dev, mut, needle=None):
        d = copy.deepcopy(base); mut(d)
        check(name + ": schema still clean", caps.schema_errors(d, SCHEMA) == [])
        errs, _ = caps.semantic_errors(dev, d)
        hit = len(errs) > 0 and (needle is None or any(needle in e for e in errs))
        check(name + ": semantic rejects" + (f" ({needle})" if needle else ""), hit)

    sem_neg("unknown ev code", "a133",
            lambda d: d["inputs"][0].update(code="BTN_WIGGLE"), "unknown ev code")
    sem_neg("ev_type/code mismatch", "a133",
            lambda d: d["inputs"][0].update(ev_type="EV_ABS"), "not ABS_")
    sem_neg("range min>max", "a133",
            lambda d: d["inputs"][3]["range"].update(min=300), "min")
    sem_neg("incoherent geometry (forgot rotation)", "a133",
            lambda d: d["screens"][0].update(rotation="none"), "incoherent")
    sem_neg("duplicate input id", "a133",
            lambda d: d["inputs"].append(copy.deepcopy(d["inputs"][0])), "duplicate")
    sem_neg("skin_part with no parts entry", "a133",
            lambda d: d["inputs"][0].update(skin_part="ghost"), "no [skin.parts]")
    sem_neg("skin rect exceeds bezel", "a133",
            lambda d: d["skin"]["parts"]["btn_south"].update(x=590, w=50), "exceeds bezel")
    sem_neg("device.id != directory", "zzz",
            lambda d: None, "!= device directory")
    sem_neg("device.id join: identity != profile", "a133",
            lambda d: d["identity"].update(id="a133x"), None)  # id!=dir AND no profile
    sem_neg("accept_default references a non-existent input id", "a133",
            lambda d: d.update(accept_default="ghost"), "accept_default")

    # --- gamecontrollerdb emit (against the REAL authored descriptors) ---
    for did, expect_thumb in (("a133", False), ("a523", True)):
        cpath = os.path.join(caps.DEVICES, did, caps.CAPS_FILE)
        if not os.path.isfile(cpath):
            check(f"{did} emit: descriptor present", False); continue
        d = caps._load(cpath)
        line = caps.emit_sdldb(d)
        try:
            guid, name, m = caps.parse_sdldb(line); rt = True
        except ValueError:
            guid, name, m, rt = "", "", {}, False
        check(f"{did} emit: round-trips through SDL grammar", rt)
        check(f"{did} emit: GUID matches sdl_guid", guid == d["identity"]["sdl_guid"])
        # L2/R2 are DIGITAL buttons (tsp-5p1), so they emit as lefttrigger:b6/righttrigger:b7
        # (NOT the ABS axes a2/a5), which inserts at evdev 0x138/0x139 and pushes back/start/guide
        # to b8/b9/b10 (L3/R3 on a523 follow at b11/b12).
        for f, s in [("a", "b0"), ("b", "b1"), ("x", "b2"), ("y", "b3"),
                     ("leftshoulder", "b4"), ("rightshoulder", "b5"),
                     ("lefttrigger", "b6"), ("righttrigger", "b7"),
                     ("back", "b8"), ("start", "b9"), ("guide", "b10"),
                     ("leftx", "a0"), ("lefty", "a1"), ("rightx", "a3"), ("righty", "a4"),
                     ("dpup", "h0.1"), ("dpdown", "h0.4")]:
            check(f"{did} emit: {f}:{s}", m.get(f) == s)
        check(f"{did} emit: L3/R3 present == {expect_thumb}",
              ("leftstick" in m) == expect_thumb and ("rightstick" in m) == expect_thumb)
        check(f"{did} emit: only known SDL fields (home/KEY_HOMEPAGE excluded)",
              all(f in caps.SDL_FIELDS for f in m))

    # --- SPIKE-0 probe-diff (asymmetric rule) against a synthetic xpad capture ---
    def xpad_capture(home=True, drop=None, absx_min=-32768):
        # BTN_TL2/BTN_TR2 = the DIGITAL L2/R2 the node advertises (tsp-5p1). The X360-presented
        # ABS_Z/ABS_RZ axes below stay too -> they're now an unused advertised superset (INFO).
        keys = ["BTN_A", "BTN_B", "BTN_C", "BTN_X", "BTN_Y", "BTN_Z", "BTN_TL", "BTN_TR",
                "BTN_TL2", "BTN_TR2",
                "BTN_SELECT", "BTN_START", "BTN_MODE", "BTN_THUMBL", "BTN_THUMBR"]
        if drop:
            keys = [k for k in keys if k != drop]
        absd = {a: {"min": -32768, "max": 32767, "fuzz": 16, "flat": 128, "resolution": 0}
                for a in ("ABS_X", "ABS_Y", "ABS_RX", "ABS_RY")}
        absd["ABS_X"]["min"] = absx_min
        absd["ABS_Z"] = {"min": 0, "max": 255, "fuzz": 0, "flat": 0, "resolution": 0}
        absd["ABS_RZ"] = {"min": 0, "max": 255, "fuzz": 0, "flat": 0, "resolution": 0}
        absd["ABS_HAT0X"] = {"min": -1, "max": 1, "fuzz": 0, "flat": 0, "resolution": 0}
        absd["ABS_HAT0Y"] = {"min": -1, "max": 1, "fuzz": 0, "flat": 0, "resolution": 0}
        pad = {"path": "/dev/input/event3", "name": "TRIMUI Player1", "vendor": "045e",
               "product": "028e", "ev": ["EV_SYN", "EV_KEY", "EV_ABS"], "keys": keys, "abs": absd}
        kbd = {"path": "/dev/input/event0", "name": "sunxi-keyboard",
               "keys": (["KEY_HOMEPAGE"] if home else [])}
        return {"nodes": [kbd, pad]}

    e, w, i = caps.probe_diff("a133", xpad_capture())
    check("probe-diff a133: subset holds (no errors)", e == [])
    check("probe-diff a133: HID superset reported as INFO", any("superset" in x for x in i))
    e, w, i = caps.probe_diff("a133", xpad_capture(drop="BTN_A"))
    check("probe-diff a133: descriptor code not advertised -> ERROR", any("BTN_A" in x for x in e))
    e, w, i = caps.probe_diff("a133", xpad_capture(absx_min=-1000))
    check("probe-diff a133: absinfo mismatch -> WARN (reconcile)", any("reconcile" in x for x in w))
    e, w, i = caps.probe_diff("a523", xpad_capture(home=True))
    check("probe-diff a523: home on keyboard node -> no error", e == [])
    check("probe-diff a523: IMU flagged as IIO (confirm bind)", any("IIO" in x for x in i))
    e, w, i = caps.probe_diff("a523", xpad_capture(home=False))
    check("probe-diff a523: home advertised nowhere -> ERROR", any("KEY_HOMEPAGE" in x for x in e))

    print()
    if _failures:
        print(f"{len(_failures)} FAILURE(S): " + ", ".join(_failures))
        return 1
    print("ALL CAPS SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
