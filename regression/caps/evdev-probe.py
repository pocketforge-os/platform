#!/usr/bin/env python3
"""regression/caps/evdev-probe.py — dump what /dev/input/event* ACTUALLY advertises.

The GROUND-TRUTH half of SPIKE-0 (tsp-9sx.1): the descriptor is the EXPECTATION, this
dump is the truth. Runs ON the device (over the Dell serial console, travel-mode), stdlib
ONLY (no python-evdev on the target) — it issues EVIOCGID / EVIOCGNAME / EVIOCGBIT /
EVIOCGABS ioctls directly and prints a JSON capture that `pf caps probe-diff` diffs against
capabilities.toml under the asymmetric rule.

  on device:   python3 evdev-probe.py > /tmp/a133-probe.json
  on host:     pf caps probe-diff --device a133 --probe a133-probe.json

NOTE: the ioctl plumbing is validated on silicon during SPIKE-0 (it needs real input
nodes to exercise). The diff logic it feeds is unit-tested device-free. evtest remains the
companion for confirming a code FIRES on a physical press (presence != advertised).
"""
import sys, os, glob, json, struct, fcntl

# asm-generic _IOC encoding (aarch64/x86_64): dir<<30 | size<<16 | type<<8 | nr
_IOC_READ = 2
def _IOC(d, t, nr, size): return (d << 30) | (size << 16) | (ord(t) << 8) | nr
def EVIOCGID():        return _IOC(_IOC_READ, 'E', 0x02, 8)             # struct input_id (4x u16)
def EVIOCGNAME(n):     return _IOC(_IOC_READ, 'E', 0x06, n)
def EVIOCGBIT(ev, n):  return _IOC(_IOC_READ, 'E', 0x20 + ev, n)
def EVIOCGABS(a):      return _IOC(_IOC_READ, 'E', 0x40 + a, 24)        # struct input_absinfo (6x s32)

EV_SYN, EV_KEY, EV_ABS, EV_FF = 0x00, 0x01, 0x03, 0x15
# Kernel ABI (input-event-codes.h): EV_MSC=0x04, EV_SW=0x05. (An earlier revision
# mislabeled 0x04 as EV_SW; the SW bit the TRIMUI pad advertises is bit 5.)
EV_NAMES = {0x00: "EV_SYN", 0x01: "EV_KEY", 0x02: "EV_REL", 0x03: "EV_ABS",
            0x04: "EV_MSC", 0x05: "EV_SW", 0x11: "EV_LED", 0x15: "EV_FF"}

# Reverse code->name tables — GENERATED from the kernel ABI (input-event-codes.h) restricted
# to exactly the core/caps.py schema vocab. Do NOT edit by hand: the old hand-maintained map
# decimal/hex-slipped KEY_HOMEPAGE (had 0x172 for what the kernel defines as 172/0xac) and was
# missing schema codes (BTN_TL2/BTN_TR2, ABS_THROTTLE/GAS/BRAKE ...), which made
# `pf caps probe-diff --device a523` ERROR on the a523 Home key even when the hardware was
# correct. See gen_evdev_probe_codes.py.
# --- BEGIN GENERATED reverse tables (gen_evdev_probe_codes.py) ---
# Regenerate: python3 regression/caps/gen_evdev_probe_codes.py --platform <dir>
# Verify   : python3 regression/caps/gen_evdev_probe_codes.py --platform <dir> --check
# Values are kernel ABI (input-event-codes.h), restricted to core/caps.py vocab.
BTN = {
    0x120: 'BTN_TRIGGER',
    0x121: 'BTN_THUMB',
    0x130: 'BTN_A',
    0x131: 'BTN_B',
    0x132: 'BTN_C',
    0x133: 'BTN_X',
    0x134: 'BTN_Y',
    0x135: 'BTN_Z',
    0x136: 'BTN_TL',
    0x137: 'BTN_TR',
    0x138: 'BTN_TL2',
    0x139: 'BTN_TR2',
    0x13a: 'BTN_SELECT',
    0x13b: 'BTN_START',
    0x13c: 'BTN_MODE',
    0x13d: 'BTN_THUMBL',
    0x13e: 'BTN_THUMBR',
    0x220: 'BTN_DPAD_UP',
    0x221: 'BTN_DPAD_DOWN',
    0x222: 'BTN_DPAD_LEFT',
    0x223: 'BTN_DPAD_RIGHT',
}
KEY = {
    0x1: 'KEY_ESC',
    0x1c: 'KEY_ENTER',
    0x66: 'KEY_HOME',
    0x72: 'KEY_VOLUMEDOWN',
    0x73: 'KEY_VOLUMEUP',
    0x74: 'KEY_POWER',
    0x8b: 'KEY_MENU',
    0x9e: 'KEY_BACK',
    0xac: 'KEY_HOMEPAGE',
}
ABS = {
    0x0: 'ABS_X',
    0x1: 'ABS_Y',
    0x2: 'ABS_Z',
    0x3: 'ABS_RX',
    0x4: 'ABS_RY',
    0x5: 'ABS_RZ',
    0x6: 'ABS_THROTTLE',
    0x7: 'ABS_RUDDER',
    0x9: 'ABS_GAS',
    0xa: 'ABS_BRAKE',
    0x10: 'ABS_HAT0X',
    0x11: 'ABS_HAT0Y',
    0x12: 'ABS_HAT1X',
    0x13: 'ABS_HAT1Y',
}
# --- END GENERATED reverse tables ---


def _bits(buf):
    out = []
    for byte_i, byte in enumerate(buf):
        for bit in range(8):
            if byte & (1 << bit):
                out.append(byte_i * 8 + bit)
    return out


def probe(path):
    node = {"path": path}
    with open(path, "rb") as f:
        fd = f.fileno()
        try:
            buf = bytearray(256)
            n = fcntl.ioctl(fd, EVIOCGNAME(len(buf)), buf)
            node["name"] = bytes(buf[:n]).split(b"\x00")[0].decode("utf-8", "replace")
        except OSError:
            node["name"] = ""
        try:
            iid = bytearray(8)
            fcntl.ioctl(fd, EVIOCGID(), iid)
            bus, ven, prod, ver = struct.unpack("HHHH", iid)
            node.update(bustype=bus, vendor=f"{ven:04x}", product=f"{prod:04x}", version=f"{ver:04x}")
        except OSError:
            pass
        evbuf = bytearray(4)
        fcntl.ioctl(fd, EVIOCGBIT(0, len(evbuf)), evbuf)
        evs = _bits(evbuf)
        node["ev"] = [EV_NAMES.get(e, f"EV_{e:#x}") for e in evs]
        if EV_KEY in evs:
            kb = bytearray((0x2ff // 8) + 1)
            fcntl.ioctl(fd, EVIOCGBIT(EV_KEY, len(kb)), kb)
            node["keys"] = [BTN.get(c) or KEY.get(c) or f"0x{c:x}" for c in _bits(kb)]
        if EV_ABS in evs:
            ab = bytearray((0x3f // 8) + 1)
            fcntl.ioctl(fd, EVIOCGBIT(EV_ABS, len(ab)), ab)
            absinfo = {}
            for a in _bits(ab):
                try:
                    raw = bytearray(24)
                    fcntl.ioctl(fd, EVIOCGABS(a), raw)
                    _val, mn, mx, fz, fl, res = struct.unpack("iiiiii", raw)
                    absinfo[ABS.get(a, f"0x{a:x}")] = {"min": mn, "max": mx, "fuzz": fz,
                                                       "flat": fl, "resolution": res}
                except OSError:
                    pass
            node["abs"] = absinfo
        if EV_FF in evs:
            node["ev_ff"] = True
    return node


# --- press-test watch mode (SPIKE-0: physical presence => a real event, not a bitfield;
# stock images may lack evtest, so this is the stdlib substitute) -------------------------
_EVENT_FMT = "llHHi"          # struct input_event, native sizes (matches userland bitness)
_EVENT_SIZE = struct.calcsize(_EVENT_FMT)


def decode_event(buf, offset=0):
    """Decode one struct input_event -> (type, code, value). Native-bitness layout."""
    _sec, _usec, etype, code, value = struct.unpack_from(_EVENT_FMT, buf, offset)
    return etype, code, value


def event_name(etype, code):
    if etype == EV_KEY:
        return BTN.get(code) or KEY.get(code) or f"0x{code:x}"
    if etype == EV_ABS:
        return ABS.get(code, f"0x{code:x}")
    return f"0x{code:x}"


def watch(paths, seconds):
    """Print decoded EV_KEY/EV_ABS events live; end with a JSON codes-seen summary.

    ABS events are deduped per (node, code) with a delta of (max-min)/64 from the node's
    own EVIOCGABS absinfo, so idle stick jitter doesn't flood a serial/SSH transcript.
    """
    import select, time
    fds, meta = [], {}
    for p in paths:
        try:
            info = probe(p)
            f = open(p, "rb", buffering=0)
            os.set_blocking(f.fileno(), False)
            deltas = {}
            for aname, ai in (info.get("abs") or {}).items():
                deltas[aname] = max(1, (ai["max"] - ai["min"]) // 64)
            fds.append(f)
            meta[f.fileno()] = {"path": p, "name": info.get("name", ""), "deltas": deltas,
                                "last": {}, "seen": set(), "file": f}
        except OSError as e:
            print(f"# {p}: {e}", flush=True)
    if not fds:
        print("# watch: no readable nodes", flush=True)
        return 1
    for m in meta.values():
        print(f"# watching {m['path']} \"{m['name']}\"", flush=True)
    t0 = time.time()
    deadline = t0 + seconds
    try:
        while time.time() < deadline:
            r, _, _ = select.select(fds, [], [], min(1.0, max(0.0, deadline - time.time())))
            for f in r:
                m = meta[f.fileno()]
                try:
                    buf = f.read(_EVENT_SIZE * 64)
                except OSError:
                    continue
                if not buf:
                    continue
                for off in range(0, len(buf) - len(buf) % _EVENT_SIZE, _EVENT_SIZE):
                    etype, code, value = decode_event(buf, off)
                    if etype not in (EV_KEY, EV_ABS):
                        continue
                    name = event_name(etype, code)
                    if etype == EV_ABS:
                        last = m["last"].get(name)
                        delta = m["deltas"].get(name, 1)
                        if last is not None and abs(value - last) < delta:
                            continue
                        m["last"][name] = value
                    m["seen"].add(name)
                    print(f"[{time.time() - t0:7.2f}s] {os.path.basename(m['path'])} "
                          f"{EV_NAMES.get(etype, hex(etype))} {name} {value}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        summary = {m["path"]: {"name": m["name"], "codes_seen": sorted(m["seen"])}
                   for m in meta.values()}
        print(json.dumps({"watch_summary": summary}, indent=2), flush=True)
        for m in meta.values():
            m["file"].close()
    return 0


def main(argv):
    argv = list(argv)
    do_watch, seconds = False, 120.0
    if "--watch" in argv:
        do_watch = True
        argv.remove("--watch")
    if "--seconds" in argv:
        i = argv.index("--seconds")
        seconds = float(argv[i + 1])
        del argv[i:i + 2]
    paths = argv or sorted(glob.glob("/dev/input/event*"))
    if do_watch:
        return watch(paths, seconds)
    nodes = []
    for p in paths:
        try:
            nodes.append(probe(p))
        except OSError as e:
            nodes.append({"path": p, "error": str(e)})
    json.dump({"nodes": nodes}, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
