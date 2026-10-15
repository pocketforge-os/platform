#!/usr/bin/env python3
"""Problem report v1: strict canonical CBOR codec and validator (stdlib only).

This is the second, independent implementation of README.md; the runtime crate
pf-problem-report is the first. Both must reach the same verdict, with the same
typed reason, on every fixture. Check order is part of the contract (README
"Refusal order").

    python3 problem_report.py report.cbor   # prints the JSON mapping or the refusal
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from typing import Any

MAX_BYTES = 4096
MAX_FRAMES = 48
MAX_SAMPLES = 2
MAX_KFRAMES = 32
MAX_OFFSET = 2**48 - 1
MAX_KOFFSET = 2**32 - 1
MAX_DEPTH = 8

KINDS = ("crash", "hang", "oom", "component", "kernel")
SIGNALS = ("SIGSEGV", "SIGABRT", "SIGBUS", "SIGILL", "SIGFPE", "SIGTRAP", "SIGSYS", "SIGQUIT", "SIGXCPU", "SIGXFSZ")
HOW = {
    "crash": SIGNALS,
    "hang": ("no-reply-menu", "stop-timeout"),
    "oom": ("oom-kill",),
    "component": SIGNALS + ("start-timeout", "stop-timeout", "no-reply-menu"),
    "kernel": ("oops", "panic", "watchdog"),
}
ORIGINS = ("image", "catalog", "sideloaded")
BUCKETS = ("<1m", "1-10m", "10-60m", ">1h")

REASONS = (
    "too-large",
    "malformed",
    "unsupported",
    "non-canonical",
    "type",
    "unknown-field",
    "version",
    "missing-field",
    "forbidden-field",
    "vocabulary",
    "grammar",
    "range",
    "inconsistent",
)

# Every top-level field. True = required for the kind, False = forbidden, None = optional.
NOT_KERNEL = {"crash": True, "hang": True, "oom": True, "component": True, "kernel": False}
PRESENCE = {
    "v": dict.fromkeys(KINDS, True),
    "kind": dict.fromkeys(KINDS, True),
    "how": dict.fromkeys(KINDS, True),
    "day": dict.fromkeys(KINDS, True),
    "build": dict.fromkeys(KINDS, True),
    "model": dict.fromkeys(KINDS, True),
    "app": NOT_KERNEL,
    "uptime": dict.fromkeys(KINDS, True),
    "session": NOT_KERNEL,
    "mem": NOT_KERNEL,
    "frames": NOT_KERNEL,
    "samples": {"crash": False, "hang": True, "oom": False, "component": False, "kernel": False},
    "kframes": {"crash": False, "hang": False, "oom": False, "component": False, "kernel": True},
    "panic_at": {"crash": None, "hang": False, "oom": False, "component": None, "kernel": False},
    "del": dict.fromkeys(KINDS, True),
}

DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
BUILD = re.compile(r"[0-9a-f]{12}\Z")
MODEL = re.compile(r"[a-z0-9][a-z0-9-]{0,31}\Z")
LABEL = re.compile(r"[a-z0-9]([a-z0-9_-]*[a-z0-9])?\Z")
VER = re.compile(r"(0|[1-9][0-9]{0,8})(\.(0|[1-9][0-9]{0,8})){0,3}\Z")
PANIC_AT = re.compile(r"crates/[A-Za-z0-9_/.-]+\.rs:[0-9]+:[0-9]+\Z")
KSYM = re.compile(r"[A-Za-z0-9_]{1,48}\Z")
KMOD = re.compile(r"[A-Za-z0-9_]{1,24}\Z")
HEX = re.compile(r"(?:[0-9a-f]{2})*\Z")


class Refused(ValueError):
    def __init__(self, reason: str, at: str = "") -> None:
        assert reason in REASONS, reason
        super().__init__("%s at %s" % (reason, at or "<report>"))
        self.reason = reason
        self.at = at


# --- canonical CBOR (RFC 8949 section 4.2.1 subset) -------------------------


def _head(major: int, arg: int) -> bytes:
    if arg < 24:
        return bytes([major << 5 | arg])
    for ai, width in ((24, 1), (25, 2), (26, 4), (27, 8)):
        if arg < 1 << (8 * width):
            return bytes([major << 5 | ai]) + arg.to_bytes(width, "big")
    raise Refused("range")


def encode_generic(value: Any) -> bytes:
    """Deterministic encoding of the generic value model, valid or not."""
    if value is None:
        return b"\xf6"
    if value is False:
        return b"\xf4"
    if value is True:
        return b"\xf5"
    if isinstance(value, int):
        if value < 0:
            raise Refused("unsupported")
        return _head(0, value)
    if isinstance(value, bytes):
        return _head(2, len(value)) + value
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return _head(3, len(raw)) + raw
    if isinstance(value, list):
        return _head(4, len(value)) + b"".join(encode_generic(item) for item in value)
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise Refused("unsupported")
        pairs = sorted((encode_generic(key), encode_generic(item)) for key, item in value.items())
        return _head(5, len(pairs)) + b"".join(key + item for key, item in pairs)
    raise Refused("unsupported")


def parse(data: bytes) -> Any:
    """Strict decode: every accepted input is its own canonical encoding."""
    value, pos = _item(data, 0, 0)
    if pos != len(data):
        raise Refused("malformed", "trailing bytes")
    return value


def _item(data: bytes, pos: int, depth: int) -> tuple[Any, int]:
    if pos >= len(data):
        raise Refused("malformed", "truncated")
    initial = data[pos]
    major, ai = initial >> 5, initial & 31
    pos += 1
    if major == 7:
        if ai == 20:
            return False, pos
        if ai == 21:
            return True, pos
        if ai == 22:
            return None, pos
        if 28 <= ai <= 30:
            raise Refused("malformed", "reserved")
        raise Refused("unsupported", "simple/float")
    if major in (1, 6):
        raise Refused("unsupported", "negative/tag")
    if 28 <= ai <= 30:
        raise Refused("malformed", "reserved")
    if ai == 31:
        raise Refused("malformed" if major == 0 else "unsupported", "indefinite")
    if ai < 24:
        arg = ai
    else:
        width = 1 << (ai - 24)
        if pos + width > len(data):
            raise Refused("malformed", "truncated")
        arg = int.from_bytes(data[pos : pos + width], "big")
        pos += width
        if arg < (24 if width == 1 else 1 << (4 * width)):
            raise Refused("non-canonical", "argument not shortest")
    if major == 0:
        return arg, pos
    if major in (2, 3):
        if arg > len(data) - pos:
            raise Refused("malformed", "truncated")
        raw = data[pos : pos + arg]
        pos += arg
        if major == 2:
            return bytes(raw), pos
        try:
            return raw.decode("utf-8"), pos
        except UnicodeDecodeError:
            raise Refused("malformed", "utf-8") from None
    if depth >= MAX_DEPTH:
        raise Refused("unsupported", "nesting")
    if major == 4:
        if arg > len(data) - pos:
            raise Refused("malformed", "truncated")
        items = []
        for _ in range(arg):
            item, pos = _item(data, pos, depth + 1)
            items.append(item)
        return items, pos
    if arg > (len(data) - pos) // 2:
        raise Refused("malformed", "truncated")
    out: dict = {}
    previous = b""
    for _ in range(arg):
        start = pos
        key, pos = _item(data, pos, depth + 1)
        if not isinstance(key, str):
            raise Refused("unsupported", "non-text key")
        raw_key = bytes(data[start:pos])
        if previous and raw_key <= previous:
            raise Refused("non-canonical", "duplicate key" if raw_key == previous else "key order")
        previous = raw_key
        out[key], pos = _item(data, pos, depth + 1)
    return out, pos


# --- schema -----------------------------------------------------------------


def _is_uint(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _str(value: Any, at: str) -> str:
    if not isinstance(value, str):
        raise Refused("type", at)
    return value


def _grammar(value: Any, pattern: re.Pattern, at: str, limit: int = 4096) -> None:
    if not (_str(value, at).isascii() and len(value) <= limit and pattern.match(value)):
        raise Refused("grammar", at)


def _closed_map(value: Any, at: str, required: tuple, optional: tuple = ()) -> dict:
    if not isinstance(value, dict):
        raise Refused("type", at)
    for key in value:
        if key not in required and key not in optional:
            raise Refused("unknown-field", "%s.%s" % (at, key))
    for key in required:
        if key not in value:
            raise Refused("missing-field", "%s.%s" % (at, key))
    return value


def valid_app_id(value: str) -> bool:
    """pf-app-manifest validate_app_id: 3..=200 ASCII, two or more labels."""
    labels = value.split(".")
    return value.isascii() and 3 <= len(value) <= 200 and len(labels) >= 2 and all(LABEL.match(x) for x in labels)


def _check_day(value: Any) -> None:
    _grammar(value, DAY, "day")
    try:
        day = datetime.date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        raise Refused("grammar", "day") from None
    if not 2020 <= day.year <= 2099:
        raise Refused("grammar", "day")


def _check_app(value: Any) -> None:
    app = _closed_map(value, "app", ("origin",), ("id", "ver"))
    origin = _str(app["origin"], "app.origin")
    if origin not in ORIGINS:
        raise Refused("vocabulary", "app.origin")
    if origin == "sideloaded":
        for key in ("id", "ver"):
            if key in app:
                raise Refused("forbidden-field", "app." + key)
    if origin != "sideloaded" and "id" not in app:
        raise Refused("missing-field", "app.id")
    if origin == "catalog" and "ver" not in app:
        raise Refused("missing-field", "app.ver")
    if "id" in app and not valid_app_id(_str(app["id"], "app.id")):
        raise Refused("grammar", "app.id")
    if "ver" in app:
        _grammar(app["ver"], VER, "app.ver", 32)


def _check_frames(value: Any) -> None:
    if not isinstance(value, list):
        raise Refused("type", "frames")
    if len(value) > MAX_FRAMES:
        raise Refused("range", "frames")
    for index, frame in enumerate(value):
        at = "frames[%d]" % index
        if not isinstance(frame, list) or len(frame) != 2:
            raise Refused("type", at)
        if frame == [None, None]:
            continue
        build_id, offset = frame
        if not isinstance(build_id, bytes) or not _is_uint(offset):
            raise Refused("type", at)
        if not 8 <= len(build_id) <= 32:
            raise Refused("grammar", at + ".build_id")
        if offset > MAX_OFFSET:
            raise Refused("range", at + ".offset")


def _check_samples(value: Any) -> None:
    if not isinstance(value, list):
        raise Refused("type", "samples")
    if len(value) > MAX_SAMPLES:
        raise Refused("range", "samples")
    for index, count in enumerate(value):
        if not _is_uint(count):
            raise Refused("type", "samples[%d]" % index)
        if not 1 <= count <= MAX_FRAMES:
            raise Refused("range", "samples[%d]" % index)


def _check_kframes(value: Any) -> None:
    if not isinstance(value, list):
        raise Refused("type", "kframes")
    if len(value) > MAX_KFRAMES:
        raise Refused("range", "kframes")
    for index, frame in enumerate(value):
        at = "kframes[%d]" % index
        if not isinstance(frame, list) or len(frame) != 4:
            raise Refused("type", at)
        sym, off, size, module = frame
        if not _is_uint(off) or not _is_uint(size):
            raise Refused("type", at)
        _grammar(sym, KSYM, at + ".sym")
        if off > MAX_KOFFSET or size > MAX_KOFFSET:
            raise Refused("range", at)
        if module is not None:
            _grammar(module, KMOD, at + ".module")


def _check_bucket(value: Any, at: str) -> None:
    if _str(value, at) not in BUCKETS:
        raise Refused("vocabulary", at)


def _check_mem(value: Any) -> None:
    mem = _closed_map(value, "mem", ("oom", "pressure"))
    for key in ("oom", "pressure"):
        if not isinstance(mem[key], bool):
            raise Refused("type", "mem." + key)


def validate(value: Any) -> None:
    """Schema check of a parsed generic value; raises Refused."""
    if not isinstance(value, dict):
        raise Refused("type")
    for key in value:
        if key not in PRESENCE:
            raise Refused("unknown-field", key)
    if "v" not in value:
        raise Refused("missing-field", "v")
    if not _is_uint(value["v"]):
        raise Refused("type", "v")
    if value["v"] != 1:
        raise Refused("version", "v")
    if "kind" not in value:
        raise Refused("missing-field", "kind")
    kind = _str(value["kind"], "kind")
    if kind not in KINDS:
        raise Refused("vocabulary", "kind")
    for key in sorted(PRESENCE, key=lambda k: (len(k), k)):
        rule = PRESENCE[key][kind]
        if rule is True and key not in value:
            raise Refused("missing-field", key)
        if rule is False and key in value:
            raise Refused("forbidden-field", key)
    checks = {
        "app": _check_app,
        "day": _check_day,
        "del": lambda x: _check_del(x),
        "how": lambda x: _check_how(x, kind),
        "mem": _check_mem,
        "build": lambda x: _grammar(x, BUILD, "build"),
        "model": lambda x: _grammar(x, MODEL, "model"),
        "frames": _check_frames,
        "uptime": lambda x: _check_bucket(x, "uptime"),
        "kframes": _check_kframes,
        "samples": _check_samples,
        "session": lambda x: _check_bucket(x, "session"),
        "panic_at": lambda x: _grammar(x, PANIC_AT, "panic_at", 128),
    }
    for key in sorted(value, key=lambda k: (len(k), k)):
        if key in checks:
            checks[key](value[key])
    if kind == "component" and value["app"]["origin"] != "image":
        raise Refused("inconsistent", "app.origin")
    if kind == "oom" and not value["mem"]["oom"]:
        raise Refused("inconsistent", "mem.oom")
    if kind == "hang" and sum(value["samples"]) != len(value["frames"]):
        raise Refused("inconsistent", "samples")
    if "panic_at" in value and (value["app"]["origin"] != "image" or value["how"] != "SIGABRT"):
        raise Refused("inconsistent", "panic_at")


def _check_del(value: Any) -> None:
    if not isinstance(value, bytes):
        raise Refused("type", "del")
    if len(value) != 32:
        raise Refused("grammar", "del")


def _check_how(value: Any, kind: str) -> None:
    if _str(value, "how") not in HOW[kind]:
        raise Refused("vocabulary", "how")


# --- JSON mapping -----------------------------------------------------------


def to_json(value: Any) -> Any:
    """Generic value -> JSON mapping: byte strings become lowercase hex."""
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, list):
        return [to_json(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    return value


def to_tagged_value(report: Any) -> Any:
    """JSON mapping -> generic value, schema-directed and tolerant of bad input.

    Only `del` and a frame's first element are byte strings; they convert when
    they are lowercase hex, and stay text (a `type` refusal) otherwise.
    """

    def hexbytes(item: Any) -> Any:
        return bytes.fromhex(item) if isinstance(item, str) and HEX.match(item) else item

    if not isinstance(report, dict):
        return report
    out = dict(report)
    if "del" in out:
        out["del"] = hexbytes(out["del"])
    if isinstance(out.get("frames"), list):
        out["frames"] = [
            [hexbytes(frame[0])] + frame[1:] if isinstance(frame, list) and frame else frame for frame in out["frames"]
        ]
    return out


def from_tagged_json(value: Any) -> Any:
    """Invalid-fixture notation: {"$bytes": "<hex>"} is a byte string."""
    if isinstance(value, dict):
        if set(value) == {"$bytes"}:
            return bytes.fromhex(value["$bytes"])
        return {key: from_tagged_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [from_tagged_json(item) for item in value]
    return value


# --- public API -------------------------------------------------------------


def decode(data: bytes) -> dict:
    """Wire bytes -> JSON mapping, or Refused."""
    if len(data) > MAX_BYTES:
        raise Refused("too-large")
    value = parse(data)
    validate(value)
    return to_json(value)


def encode(report: dict) -> bytes:
    """JSON mapping -> canonical wire bytes; refuses exactly what decode refuses."""
    data = encode_generic(to_tagged_value(report))
    if decode(data) != report:
        raise Refused("type", "JSON mapping does not round-trip")
    return data


def worst_case(kind: str) -> dict:
    """The largest valid report of a kind: every bounded field at its bound."""
    report: dict = {
        "v": 1,
        "kind": kind,
        "how": max(HOW[kind], key=len),
        "day": "2099-12-31",
        "build": "f" * 12,
        "model": "m" * 32,
        "uptime": "10-60m",
        "del": "ff" * 32,
    }
    if kind == "kernel":
        report["kframes"] = [["s" * 48, MAX_KOFFSET, MAX_KOFFSET, "m" * 24]] * MAX_KFRAMES
        return report
    origin = "image" if kind in ("crash", "component") else "catalog"
    report["app"] = {"id": "a" * 99 + "." + "b" * 100, "ver": "123456789.123456789.123456789.12", "origin": origin}
    report["session"] = "10-60m"
    report["mem"] = {"pressure": True, "oom": True}
    report["frames"] = [["ff" * 32, MAX_OFFSET]] * MAX_FRAMES
    if kind == "hang":
        report["samples"] = [MAX_FRAMES // 2, MAX_FRAMES // 2]
    if kind in ("crash", "component"):
        report["how"] = "SIGABRT"
        report["panic_at"] = "crates/" + "p" * 108 + ".rs:99999:999"
    return report


def main(argv: list) -> int:
    if len(argv) != 2:
        print("usage: problem_report.py <report.cbor>", file=sys.stderr)
        return 2
    with open(argv[1], "rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    try:
        print(json.dumps(decode(data), indent=2))
    except Refused as error:
        print("refused: %s (%s)" % (error.reason, error.at or "<report>"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
