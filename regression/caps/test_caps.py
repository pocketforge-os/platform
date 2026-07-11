#!/usr/bin/env python3
"""regression/caps/test_caps.py — self-test for core/caps.py (E1 / tsp-9sx.2).

Device-free. Exercises the stdlib JSON-Schema-subset engine + the semantic checks
with a known-good descriptor and a battery of negatives (the bead's negative-test
requirement). When the reference `jsonschema` library is importable, it ALSO asserts
that our engine AGREES with it (both accept / both reject) on every case — so the
hand-rolled subset engine is pinned to the real spec.

Run:  python3 regression/caps/test_caps.py   (exit 0 = all pass)
"""
import os, sys, json, copy, struct, zlib, re, subprocess, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CAPS_PY = os.path.join(ROOT, "core", "caps.py")
SCHEMA_PATH = os.path.join(ROOT, "schemas", "capabilities.schema.json")
PROBE_PY = os.path.join(HERE, "evdev-probe.py")
GEN_PY = os.path.join(HERE, "gen_evdev_probe_codes.py")

spec = importlib.util.spec_from_file_location("caps", CAPS_PY)
caps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(caps)

# evdev-probe.py has a hyphen (not a valid module name) — load via importlib. It runs on
# device with stdlib only; importing it here doesn't touch /dev/input.
_pspec = importlib.util.spec_from_file_location("evdev_probe", PROBE_PY)
evdev_probe = importlib.util.module_from_spec(_pspec)
_pspec.loader.exec_module(evdev_probe)

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
        # L2/R2 are the X360 TRIGGER AXES (SPIKE-0 on-silicon 2026-07-11: full-swing ABS_Z/RZ,
        # no BTN_TL2/TR2 advertised — tsp-5p1's digital-button claim refuted), so they emit as
        # lefttrigger:a2/righttrigger:a5 and back/start/guide sit at their CANONICAL upstream
        # X360 indices b6/b7/b8 (L3/R3 on a523 follow at b9/b10).
        for f, s in [("a", "b0"), ("b", "b1"), ("x", "b2"), ("y", "b3"),
                     ("leftshoulder", "b4"), ("rightshoulder", "b5"),
                     ("lefttrigger", "a2"), ("righttrigger", "a5"),
                     ("back", "b6"), ("start", "b7"), ("guide", "b8"),
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
    # R3 adjudicated on silicon (2026-07-11): qmi8658/mmc5603 UNBOUND on stock -> the a523
    # descriptor OMITS [[sensors]] entirely (row omission, never a fabricated row), so
    # probe-diff emits no IIO confirm-bind INFO for it.
    _a523 = caps._load(os.path.join(caps.DEVICES, "a523", caps.CAPS_FILE))
    check("a523 descriptor omits [[sensors]] (R3: unbound on stock)", not _a523.get("sensors"))
    check("probe-diff a523: no IIO sensor INFO (nothing claimed)", not any("IIO" in x for x in i))
    e, w, i = caps.probe_diff("a523", xpad_capture(home=False))
    check("probe-diff a523: home advertised nowhere -> ERROR", any("KEY_HOMEPAGE" in x for x in e))

    # --- evdev-probe reverse tables (tsp-9sx.5) ---
    # The old hand-maintained table decimal/hex-slipped KEY_HOMEPAGE (0x172 instead of
    # 172/0xac), which made a real code-172 key decode as raw "0xac" and probe-diff ERROR
    # even when the a523 hardware was correct. The tables are now GENERATED from the kernel
    # ABI restricted to the caps.py schema vocab — these tests pin that.
    check("KEY_HOMEPAGE reverse maps 172 (0xac), not 0x172 (=370)",
          evdev_probe.KEY.get(172) == "KEY_HOMEPAGE" and 0x172 not in evdev_probe.KEY)
    # Decode simulation: mirror the exact expression the probe uses on an EVIOCGBIT bitmap,
    # feed it code 172, verify it does NOT fall through to the raw "0xac" fallback.
    decoded = [evdev_probe.BTN.get(c) or evdev_probe.KEY.get(c) or f"0x{c:x}" for c in [172]]
    check("evdev-probe decodes code 172 as 'KEY_HOMEPAGE' (not raw '0xac')",
          decoded == ["KEY_HOMEPAGE"])

    # Every schema-vocab code must have a canonical name in the appropriate reverse table
    # (no schema code decodes as raw "0x.." — the bead's coverage rule). Resolve names via
    # the kernel header so this is pinned to the same ABI the generator reads.
    _header = {}
    _DEFINE = re.compile(r"^#define\s+([A-Z][A-Z0-9_]*)\s+(\S+)")
    for _hdr in ("/usr/include/linux/input-event-codes.h", "/usr/include/linux/input.h"):
        try:
            with open(_hdr) as _f:
                for _line in _f:
                    _m = _DEFINE.match(_line)
                    if _m:
                        _header[_m.group(1)] = _m.group(2)
        except OSError:
            pass

    def _resolve(nm, seen=None):
        seen = seen or set()
        if nm in seen: return None
        seen.add(nm)
        tok = _header.get(nm)
        if tok is None: return None
        try: return int(tok, 0)
        except ValueError:
            return _resolve(tok, seen) if re.fullmatch(r"[A-Z][A-Z0-9_]*", tok) else None

    def _raw_fallback_names(vocab, table, prefix):
        missing = []
        for nm in sorted(vocab):
            code = _resolve(nm)
            if code is None: continue
            if code not in table:
                missing.append(f"{nm}={code:#x}")
        return missing

    if not _header:
        # No kernel headers available (unusual on any dev host but skip gracefully).
        check("no header found — skipping schema-code coverage", True)
    else:
        miss_b = _raw_fallback_names(caps.BTN_CODES, evdev_probe.BTN, "BTN_")
        miss_k = _raw_fallback_names(caps.KEY_CODES, evdev_probe.KEY, "KEY_")
        miss_a = _raw_fallback_names(caps.ABS_CODES, evdev_probe.ABS, "ABS_")
        check("no BTN_ schema code decodes as raw 0x.." + (f" (missing: {miss_b})" if miss_b else ""),
              not miss_b)
        check("no KEY_ schema code decodes as raw 0x.." + (f" (missing: {miss_k})" if miss_k else ""),
              not miss_k)
        check("no ABS_ schema code decodes as raw 0x.." + (f" (missing: {miss_a})" if miss_a else ""),
              not miss_a)

    # End-to-end: `pf caps probe-diff --device a523` must go green vs the vendored a523
    # fixture (tsp-9sx.5 AC). Runs the CLI so both invocation path + reverse-table decode
    # ride the gate.
    _fixture = os.path.join(HERE, "fixtures", "a523-capture.json")
    _pf = os.path.join(ROOT, "pf")
    if os.path.isfile(_fixture) and os.access(_pf, os.X_OK):
        r = subprocess.run([_pf, "caps", "probe-diff", "--device", "a523", "--probe", _fixture],
                           capture_output=True, text=True)
        check("pf caps probe-diff --device a523 (vendored fixture) exits 0",
              r.returncode == 0)
        if r.returncode != 0:
            print("  probe-diff stderr: " + (r.stderr or "").strip())
            print("  probe-diff stdout: " + (r.stdout or "").strip())

    # --- watch mode (SPIKE-0 press-test substitute for evtest on stock images) ---
    # struct input_event decode on synthetic bytes (native bitness, like the target).
    _ev = struct.pack(evdev_probe._EVENT_FMT, 12, 340000, 0x01, 0x130, 1)   # EV_KEY BTN_A press
    _t, _c, _v = evdev_probe.decode_event(_ev)
    check("watch decode: EV_KEY BTN_A press round-trips",
          (_t, _c, _v) == (0x01, 0x130, 1)
          and evdev_probe.event_name(_t, _c) == "BTN_A")
    _ev2 = struct.pack(evdev_probe._EVENT_FMT, 12, 340001, 0x03, 0x10, -1)  # EV_ABS ABS_HAT0X=-1
    _t2, _c2, _v2 = evdev_probe.decode_event(_ev2)
    check("watch decode: EV_ABS ABS_HAT0X=-1 round-trips (signed value)",
          (_t2, _c2, _v2) == (0x03, 0x10, -1)
          and evdev_probe.event_name(_t2, _c2) == "ABS_HAT0X")
    _ev3 = struct.pack(evdev_probe._EVENT_FMT, 12, 340002, 0x01, 172, 1)    # KEY_HOMEPAGE press
    _t3, _c3, _v3 = evdev_probe.decode_event(_ev3)
    check("watch decode: KEY_HOMEPAGE(172) press decodes by name",
          evdev_probe.event_name(_t3, _c3) == "KEY_HOMEPAGE" and _v3 == 1)
    # EV bit labels follow the kernel ABI: EV_MSC=0x04, EV_SW=0x05 (the TRIMUI pad's EV=2b
    # includes bit 5 = SW; an earlier revision mislabeled 0x04 as EV_SW).
    check("EV_NAMES matches kernel ABI (EV_MSC=0x04, EV_SW=0x05)",
          evdev_probe.EV_NAMES.get(0x04) == "EV_MSC" and evdev_probe.EV_NAMES.get(0x05) == "EV_SW")

    # evdev-dump.c (static-C fallback for python-less stock userlands) must compile clean
    # and emit the SAME JSON capture shape. Soft-skipped when no C compiler is present.
    _dump_c = os.path.join(HERE, "evdev-dump.c")
    _cc = None
    for _cand in ("cc", "gcc", "clang"):
        try:
            if subprocess.run([_cand, "--version"], capture_output=True).returncode == 0:
                _cc = _cand
                break
        except OSError:
            continue
    if _cc and os.path.isfile(_dump_c):
        with tempfile.TemporaryDirectory() as _td:
            _bin = os.path.join(_td, "evdev-dump")
            r = subprocess.run([_cc, "-Wall", "-Wextra", "-Werror", "-O2", "-o", _bin, _dump_c],
                               capture_output=True, text=True)
            check("evdev-dump.c compiles clean (-Wall -Wextra -Werror)", r.returncode == 0)
            if r.returncode != 0:
                print("  cc stderr: " + (r.stderr or "").strip()[:500])
            else:
                r2 = subprocess.run([_bin, "/nonexistent"], capture_output=True, text=True)
                try:
                    cap = json.loads(r2.stdout)
                    ok_shape = (isinstance(cap.get("nodes"), list) and len(cap["nodes"]) == 1
                                and cap["nodes"][0]["path"] == "/nonexistent"
                                and "error" in cap["nodes"][0])
                except ValueError:
                    ok_shape = False
                check("evdev-dump emits the evdev-probe.py JSON capture shape", ok_shape)
    else:
        check("no C compiler — skipping evdev-dump.c gate", True)

    # Drift gate: the generator's --check mode must be green on the committed probe file.
    if os.path.isfile(GEN_PY) and _header:
        r = subprocess.run([sys.executable, GEN_PY, "--platform", ROOT, "--check"],
                           capture_output=True, text=True)
        check("gen_evdev_probe_codes.py --check clean (no drift vs kernel + caps.py vocab)",
              r.returncode == 0)
        if r.returncode != 0:
            print("  gen --check stderr: " + (r.stderr or "").strip())

    print()
    if _failures:
        print(f"{len(_failures)} FAILURE(S): " + ", ".join(_failures))
        return 1
    print("ALL CAPS SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
