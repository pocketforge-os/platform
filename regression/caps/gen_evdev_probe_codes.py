#!/usr/bin/env python3
"""gen_evdev_probe_codes.py — regenerate the managed reverse tables in evdev-probe.py.

The GROUND-TRUTH half of SPIKE-0 (tsp-9sx.1) is `regression/caps/evdev-probe.py` — it
runs ON the device (stdlib only) and turns EVIOCGBIT bitmaps into the descriptor's
BTN_/KEY_/ABS_ vocab. Those code<->name tables MUST match the kernel ABI: the previous
hand-maintained map decimal/hex-slipped KEY_HOMEPAGE (0x172 instead of 172/0xac) and
was missing schema codes (BTN_TL2/BTN_TR2, ABS_THROTTLE/GAS/BRAKE ...), which made
`pf caps probe-diff --device a523` ERROR on the a523 Home key even when the hardware
was correct.

Same ethos as `sim/synth/gen_evdev_codes.py`: read the kernel headers, cross-reference
the schema vocab exported by `core/caps.py`, resolve aliases (BTN_A -> BTN_SOUTH -> 0x130),
emit the tables. Kept next to the probe (not in core/) because it patches the probe's
managed region in place — evdev-probe.py stays a single-file, stdlib-only tool that
scp'd onto a stock BusyBox userland Just Works, no adjacent module required.

Alias tiebreak: descriptors + the xpad driver emit `BTN_A`, not `BTN_SOUTH`, so when
two vocab names share a code we PREFER the alias (BTN_A -> BTN_SOUTH -> 0x130 wins
over BTN_SOUTH's direct literal). Same for BTN_B/EAST, BTN_X/NORTH, BTN_Y/WEST.

Usage:
  gen_evdev_probe_codes.py --platform <dir>            # patch evdev-probe.py in place
  gen_evdev_probe_codes.py --platform <dir> --check    # assert no drift (CI)
"""
import argparse
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE_PATH = os.path.join(HERE, "evdev-probe.py")

HEADER_IEC = "/usr/include/linux/input-event-codes.h"
HEADER_INPUT = "/usr/include/linux/input.h"

BEGIN_MARK = "# --- BEGIN GENERATED reverse tables (gen_evdev_probe_codes.py) ---"
END_MARK = "# --- END GENERATED reverse tables ---"

_DEFINE = re.compile(r"^#define\s+([A-Z][A-Z0-9_]*)\s+(\S+)")


def _import_caps(platform_dir):
    caps_path = os.path.join(platform_dir, "core", "caps.py")
    if not os.path.isfile(caps_path):
        sys.exit(f"FATAL: no caps.py at {caps_path} (pass --platform <platform checkout>)")
    spec = importlib.util.spec_from_file_location("caps", caps_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse_header(path):
    """Return {name: raw_token} for every simple `#define` in a header."""
    raw = {}
    try:
        with open(path) as f:
            for line in f:
                m = _DEFINE.match(line)
                if m:
                    raw[m.group(1)] = m.group(2)
    except OSError as e:
        sys.exit(f"FATAL: cannot read {path}: {e}")
    return raw


def _resolve(name, raw, seen=None):
    """Follow alias chains to an integer; None if the token isn't a number/alias."""
    seen = seen or set()
    if name in seen:
        return None
    seen.add(name)
    tok = raw.get(name)
    if tok is None:
        return None
    try:
        return int(tok, 0)
    except ValueError:
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", tok):
            return _resolve(tok, raw, seen)
        return None


def _is_alias(name, raw):
    """True if name's #define is `#define NAME OTHER_NAME` (not a numeric literal)."""
    tok = raw.get(name)
    if tok is None:
        return False
    try:
        int(tok, 0)
        return False
    except ValueError:
        return bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", tok))


def _reverse_for(vocab, raw, family):
    """{code:int -> canonical_name:str} restricted to `vocab`; prefer alias name on ties."""
    resolved = {}
    missing = []
    for n in sorted(vocab):
        v = _resolve(n, raw)
        if v is None:
            missing.append(n)
        else:
            resolved.setdefault(v, []).append(n)
    if missing:
        sys.exit(f"FATAL: {family}: names not found/resolved in kernel headers: "
                 f"{', '.join(missing)} (header drift or a typo in the schema vocab)")
    out = {}
    for code, names in resolved.items():
        # Tiebreak: aliases (BTN_A) beat literals (BTN_SOUTH); then alphabetic.
        names.sort(key=lambda n: (0 if _is_alias(n, raw) else 1, n))
        out[code] = names[0]
    return out


def _build_tables(platform_dir):
    caps = _import_caps(platform_dir)
    raw = {}
    raw.update(_parse_header(HEADER_IEC))
    raw.update(_parse_header(HEADER_INPUT))
    return {
        "BTN": _reverse_for(caps.BTN_CODES, raw, "BTN_* (caps.BTN_CODES)"),
        "KEY": _reverse_for(caps.KEY_CODES, raw, "KEY_* (caps.KEY_CODES)"),
        "ABS": _reverse_for(caps.ABS_CODES, raw, "ABS_* (caps.ABS_CODES)"),
    }


def _emit_block(tables):
    def one(name, d):
        lines = [f"{name} = {{"]
        for code in sorted(d):
            lines.append(f"    {code:#x}: {d[code]!r},")
        lines.append("}")
        return "\n".join(lines)

    body = "\n".join(one(n, tables[n]) for n in ("BTN", "KEY", "ABS"))
    return (
        BEGIN_MARK + "\n"
        "# Regenerate: python3 regression/caps/gen_evdev_probe_codes.py --platform <dir>\n"
        "# Verify   : python3 regression/caps/gen_evdev_probe_codes.py --platform <dir> --check\n"
        "# Values are kernel ABI (input-event-codes.h), restricted to core/caps.py vocab.\n"
        + body + "\n"
        + END_MARK
    )


def _splice(probe_src, block):
    b = probe_src.find(BEGIN_MARK)
    e = probe_src.find(END_MARK)
    if b < 0 or e < 0 or e < b:
        sys.exit(f"FATAL: {PROBE_PATH} missing BEGIN/END generated markers")
    e += len(END_MARK)
    return probe_src[:b] + block + probe_src[e:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True, help="platform checkout (for core/caps.py vocab)")
    ap.add_argument("--check", action="store_true", help="fail if evdev-probe.py drifts")
    a = ap.parse_args()

    block = _emit_block(_build_tables(a.platform))
    with open(PROBE_PATH) as f:
        current = f.read()
    updated = _splice(current, block)

    if a.check:
        if current != updated:
            sys.exit(f"FAIL: {PROBE_PATH} is STALE vs kernel headers + caps.py vocab.\n"
                     f"      Regenerate: python3 {os.path.relpath(__file__)} --platform {a.platform}")
        print("OK    evdev-probe.py reverse tables match kernel ABI + caps.py vocab")
        return 0

    with open(PROBE_PATH, "w") as f:
        f.write(updated)
    print(f"wrote {PROBE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
