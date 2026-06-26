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
EV_NAMES = {0x00: "EV_SYN", 0x01: "EV_KEY", 0x02: "EV_REL", 0x03: "EV_ABS",
            0x04: "EV_SW", 0x11: "EV_LED", 0x15: "EV_FF"}

# Reverse code->name tables (gamepad/handheld subset; shared with the descriptor's vocab).
BTN = {0x130: "BTN_A", 0x131: "BTN_B", 0x132: "BTN_C", 0x133: "BTN_X", 0x134: "BTN_Y",
       0x135: "BTN_Z", 0x136: "BTN_TL", 0x137: "BTN_TR", 0x138: "BTN_TL2", 0x139: "BTN_TR2",
       0x13a: "BTN_SELECT", 0x13b: "BTN_START", 0x13c: "BTN_MODE", 0x13d: "BTN_THUMBL",
       0x13e: "BTN_THUMBR"}
KEY = {0x66: "KEY_HOME", 0x172: "KEY_HOMEPAGE", 0x8b: "KEY_MENU", 0x9e: "KEY_BACK",
       0x74: "KEY_POWER", 0x73: "KEY_VOLUMEUP", 0x72: "KEY_VOLUMEDOWN"}
ABS = {0x00: "ABS_X", 0x01: "ABS_Y", 0x02: "ABS_Z", 0x03: "ABS_RX", 0x04: "ABS_RY",
       0x05: "ABS_RZ", 0x10: "ABS_HAT0X", 0x11: "ABS_HAT0Y"}


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


def main(argv):
    paths = argv or sorted(glob.glob("/dev/input/event*"))
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
