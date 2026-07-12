#!/usr/bin/env python3
"""regression/abi/appmanifest-test.py — unit tests for the E8 per-family ABI view + the
static app-descriptor validator (tsp-ziac.1). Plain asserts, no pytest dependency (matches
the repo's dependency-light regression style). Exit 0 = all pass; 1 = a failure.

Covers the bead's acceptance: the named-family view resolves per family from platform.lock;
the view NEVER drifts from the lock (derived); an app.toml `[runtime]` pin is PARSED + VALIDATED
(unknown family / out-of-lock version / unsupported abi / malformed use rejected); the a523 SDL
provenance gap is stated honestly."""
import os, sys

CORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "core")
sys.path.insert(0, os.path.abspath(CORE))
import abi_view          # noqa: E402
import appmanifest       # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"ok   - {name}")
    else:
        print(f"FAIL - {name} {detail}")
        FAILS.append(name)


# ── the per-family view resolves from the lock ─────────────────────────────────────────────
view = abi_view.derive_view()
ids = {f["id"] for f in view["families"]}
check("view has both starter families",
      ids == {"pocketforge/a133-powervr", "pocketforge/a523-mali"}, ids)

a133 = abi_view.find_family(view, "pocketforge/a133-powervr")
a523 = abi_view.find_family(view, "pocketforge/a523-mali")

check("a133 kernel resolves from lock", bool(a133["kernel"]["sha"]) and a133["kernel"]["repo"] == "kernel-sunxi-4.9")
check("a133 gpu resolves from lock", a133["gpu_km"]["repo"] == "gpu-km-tsp" and bool(a133["gpu_km"]["sha"]))
check("a133 SDL is OWNED (libsdl3-sunxifb, pinned)",
      a133["sdl"]["status"] == "owned" and a133["sdl"]["repo"] == "libsdl3-sunxifb" and bool(a133["sdl"]["sha"]))
check("a133 is marked reproducible-from-clean", a133["reproducible"] is True)

check("a523 kernel resolves from lock", a523["kernel"]["repo"] == "kernel-sunxi-5.15" and bool(a523["kernel"]["sha"]))
check("a523 gpu resolves from lock", a523["gpu_km"]["repo"] == "gpu-km-tsp-a523" and bool(a523["gpu_km"]["sha"]))
check("a523 SDL provenance gap is HONEST (not-owned, no phantom SHA)",
      a523["sdl"]["status"] == "not-owned" and a523["sdl"]["sha"] is None, a523["sdl"])
check("a523 is marked NOT reproducible", a523["reproducible"] is False)

# alias resolution (E2 SoC-only draft ids still resolve to the canonical GPU-IP-bearing family)
check("E2 alias pocketforge/sun50i-a133 resolves to a133-powervr",
      abi_view.find_family(view, "pocketforge/sun50i-a133") is a133)
check("E2 alias pocketforge/sun55i-a523 resolves to a523-mali",
      abi_view.find_family(view, "pocketforge/sun55i-a523") is a523)

# ── the view CANNOT diverge from the lock: comparison catches a moved SHA ───────────────────
tampered = {"platform_abi_schema": view["platform_abi_schema"], "lock_state": view["lock_state"],
            "families": [dict(f) for f in view["families"]]}
tampered["families"][0] = dict(tampered["families"][0])
tampered["families"][0]["kernel"] = dict(tampered["families"][0]["kernel"], sha="deadbeef" * 5)
check("drift comparison detects a moved kernel SHA", tampered != view)

# ── the static validator PARSES + VALIDATES [runtime] ──────────────────────────────────────
VALID = """
[app]
id = "com.test.ok"
use = ["input", "imu?", "egress:example.com"]
[runtime]
family = "pocketforge/a523-mali"
abi = "1"
platform-version = "1"
"""
check("valid descriptor passes", appmanifest.validate_toml_text(VALID) == [], appmanifest.validate_toml_text(VALID))

check("valid descriptor via ALIAS passes",
      appmanifest.validate_toml_text(VALID.replace("pocketforge/a523-mali", "pocketforge/sun55i-a523")) == [])


def has(viols, needle):
    return any(needle in v for v in viols)


UNKNOWN_FAMILY = """
[app]
id = "com.test.x"
[runtime]
family = "pocketforge/rk3566-mali"
abi = "1"
"""
check("UnknownFamily rejected", has(appmanifest.validate_toml_text(UNKNOWN_FAMILY), "UnknownFamily"))

OUT_OF_LOCK = """
[app]
id = "com.test.x"
[runtime]
family = "pocketforge/a133-powervr"
abi = "1"
platform-version = "42"
"""
check("OutOfLockVersion rejected", has(appmanifest.validate_toml_text(OUT_OF_LOCK), "OutOfLockVersion"))

BAD_ABI = """
[app]
id = "com.test.x"
[runtime]
family = "pocketforge/a133-powervr"
abi = "9"
"""
check("UnsupportedAbi rejected", has(appmanifest.validate_toml_text(BAD_ABI), "UnsupportedAbi"))

MALFORMED_USE = """
[app]
id = "com.test.x"
use = ["input", "input", "location:teleport"]
[runtime]
family = "pocketforge/a523-mali"
abi = "1"
"""
mv = appmanifest.validate_toml_text(MALFORMED_USE)
check("DuplicateCapability rejected", has(mv, "DuplicateCapability"))
check("BadModifier rejected", has(mv, "BadModifier"))

NO_RUNTIME = """
[app]
id = "com.test.x"
"""
check("missing [runtime] rejected", has(appmanifest.validate_toml_text(NO_RUNTIME), "[runtime]"))

# the shipped example fixtures agree with the validator
HERE = os.path.dirname(os.path.abspath(__file__))
EX = os.path.abspath(os.path.join(HERE, "..", "..", "abi", "examples"))
for good in ("app-a133-powervr.toml", "app-a523-mali.toml"):
    with open(os.path.join(EX, good)) as fh:
        check(f"example {good} validates", appmanifest.validate_toml_text(fh.read()) == [])
with open(os.path.join(EX, "app-invalid.toml")) as fh:
    check("example app-invalid.toml is rejected", appmanifest.validate_toml_text(fh.read()) != [])

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s): {', '.join(FAILS)}")
    sys.exit(1)
print("ALL ABI/appmanifest checks passed")
