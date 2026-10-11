#!/usr/bin/env python3
"""regression/caps/test_caps_v3.py — descriptor schema v3 self-test (tsp-ihne1.3).

Device-free, stdlib only. Covers what test_caps_v2.py does not:
  - the shipped descriptors (a133/a523) are v3, validate, flip accept_default to `east`
    (X18: Nintendo-arranged chassis — the printed A button is the east position) and carry
    [input_profile] device_class + reserved_controls;
  - every v3 rule is shown to FAIL on a hostile mutation of a REAL shipped descriptor and to
    PASS on the unmutated descriptor in the SAME evaluation loop (positive and negative
    controls together): each case mutates the loaded dict, then re-runs the exact validator
    pipeline (model-sha + JSON schema first, semantic rules only when the schema is clean, as
    `validate_one` does). A case passes only when the set of named E_* rules equals the
    expected set, or — for schema-owned shape errors — when an untagged error names the needle.

Run:  python3 regression/caps/test_caps_v3.py   (exit 0 = all pass)
"""
import os, sys, re, subprocess, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CAPS_PY = os.path.join(ROOT, "core", "caps.py")
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


SCHEMA = caps._read_schema(caps.SCHEMA_PATH)


def evaluate(dev_id, mutate=None):
    """Load the REAL devices/<dev_id>/capabilities.toml, optionally mutate the dict, then run
    the validate_one pipeline in-process: model-sha + schema errors first; semantic rules only
    when the schema is clean (so a shape defect never masks itself as a semantic pass)."""
    data = caps._load(os.path.join(ROOT, "devices", dev_id, "capabilities.toml"))
    if mutate:
        mutate(data)
    errs = caps.model_sha_errors(data) + caps.schema_errors(data, SCHEMA)
    if errs:
        return errs, []
    return caps.semantic_errors(dev_id, data)


def drop_inputs(data, ids):
    data["inputs"] = [row for row in data["inputs"] if row.get("id") not in ids]


STICKS = ("lstick", "rstick")
SHOULDERS_AND_TRIGGERS = ("l1", "r1", "ltrig", "rtrig")


def profile_mutate(dev_id, fn):
    def mutate(data):
        fn(data.setdefault("input_profile", {}))
    return mutate


# (case_id, dev_id, mutator, expected tag set, needle).
# expected = set() means "a SCHEMA error, untagged"; then `needle` must appear in an error line.
# expected = POS means the pipeline is clean (positive control, same loop as the negatives).
POS = None
CASES = [
    ("pos-a133-unmutated", "a133", None, POS, None),
    ("pos-a523-unmutated", "a523", None, POS, None),
    # version gate: 4 is beyond the validator; v3 keys at v2 are refused by name.
    ("neg-schema-version-4", "a133", lambda d: d.update(schema_version=4),
     {"E_SCHEMA_VERSION"}, None),
    ("neg-v3-key-at-v2", "a133", lambda d: d.update(schema_version=2),
     {"E_V3_KEY"}, None),
    # table shape is owned by the JSON schema (untagged), coherence by E_INPUT_PROFILE.
    ("neg-device-class-unknown", "a133",
     profile_mutate("a133", lambda p: p.update(device_class="three_stick")), set(), "device_class"),
    ("neg-reserved-controls-not-a-list", "a133",
     profile_mutate("a133", lambda p: p.update(reserved_controls="guide")), set(), "reserved_controls"),
    # device_class against the derived presence facts (bindings key on the retail product).
    ("neg-class-no-stick-with-sticks", "a133",
     profile_mutate("a133", lambda p: p.update(device_class="no_stick")),
     {"E_INPUT_PROFILE"}, "forbids kind='stick'"),
    ("neg-class-minimal-with-shoulders", "a133",
     profile_mutate("a133", lambda p: p.update(device_class="minimal")),
     {"E_INPUT_PROFILE"}, "forbids shoulders"),
    ("neg-two-stick-without-sticks", "a133",
     lambda d: drop_inputs(d, STICKS), {"E_INPUT_PROFILE"}, "two kind='stick'"),
    ("neg-stick-click-without-stick", "a523",
     lambda d: drop_inputs(d, STICKS), {"E_INPUT_PROFILE"}, "stick-click"),
    ("neg-minimal-needs-hat", "a133",
     lambda d: (drop_inputs(d, STICKS + SHOULDERS_AND_TRIGGERS + ("dpad",)),
                d.setdefault("input_profile", {}).update(device_class="minimal")),
     {"E_INPUT_PROFILE"}, "D-pad"),
    # reserved_controls: real, non-system, unique ids.
    ("neg-reserved-ghost", "a133",
     profile_mutate("a133", lambda p: p.update(reserved_controls=["ghost"])),
     {"E_INPUT_PROFILE"}, "not an [[inputs]] id"),
    ("neg-reserved-system-row", "a133",
     profile_mutate("a133", lambda p: p.update(reserved_controls=["vol_up"])),
     {"E_INPUT_PROFILE"}, "class='system'"),
    ("neg-reserved-duplicate", "a523",
     profile_mutate("a523", lambda p: p.update(reserved_controls=["home", "home"])),
     {"E_INPUT_PROFILE"}, "more than once"),
]


def main():
    # --- 1. shipped descriptors: v3, accept_default east (X18), [input_profile] present ---
    rc, out, err = run("validate", "a133", "a523")
    check("validate a133 a523: exit 0", rc == 0, out + err)
    for d, reserved in (("a133", ["guide"]), ("a523", ["guide", "home"])):
        data = caps._load(os.path.join(ROOT, "devices", d, "capabilities.toml"))
        profile = data.get("input_profile", {})
        check(f"{d}: v3 descriptor with accept_default 'east' (X18, tsp-ihne1.3)",
              data.get("schema_version") == 3 and data.get("accept_default") == "east")
        check(f"{d}: [input_profile] declares device_class two_stick",
              profile.get("device_class") == "two_stick")
        check(f"{d}: reserved_controls = {reserved}",
              profile.get("reserved_controls") == reserved)

    # --- 2. hostile mutations of the REAL descriptors, judged in one loop with the positives ---
    for case_id, dev_id, mutate, expected, needle in CASES:
        errs, warns = evaluate(dev_id, mutate)
        tags = {t for e in errs for t in TAG.findall(e)}
        if expected is POS:
            check(f"{case_id}: pipeline clean (positive control, same loop)",
                  not errs, "\n".join(errs + warns))
        elif not expected:
            check(f"{case_id}: schema rejects, naming '{needle}'",
                  errs and not tags and any(needle in e for e in errs), "\n".join(errs))
        else:
            check(f"{case_id}: rejected by exactly {sorted(expected)}"
                  + (f" ({needle})" if needle else ""),
                  errs and tags == expected
                  and (needle is None or any(needle in e for e in errs))
                  and not any("cannot parse" in e for e in errs), "\n".join(errs))

    print()
    if _failures:
        print(f"{len(_failures)} FAILURES:")
        for name in _failures:
            print("  " + name)
        return 1
    print(f"all checks passed ({len(CASES)} mutation cases + shipped-descriptor facts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
