#!/usr/bin/env python3
"""Transition-matrix regression tests for the frozen Platform ABI version gate."""
import copy
import importlib.util
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("abi_view", os.path.join(ROOT, "core", "abi_view.py"))
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)


def family(fid="f/a", version="1"):
    return {"id": fid, "platform_version": version,
            "kernel": {"repo": "kernel", "ref": "main", "sha": "k1"},
            "gpu_km": {"repo": "gpu", "ref": "main", "sha": "g1"},
            "sdl": {"status": "owned", "repo": "sdl", "backend": "fb", "sha": "s1"}}


def view(state="authoritative", families=None):
    return {"lock_state": state, "families": families or [family()]}


def assert_reason(old, new, reason):
    errors = abi.validate_version_transition(old, new)
    assert reason in [error["reason"] for error in errors], errors


def assert_green(old, new):
    assert abi.validate_version_transition(old, new) == []


base = view()
for component, field, value in [
        ("kernel", "sha", "k2"), ("gpu_km", "sha", "g2"), ("sdl", "sha", "s2"),
        ("sdl", "status", "not-owned"), ("kernel", "repo", "kernel-new"),
        ("kernel", "ref", "release")]:
    changed = copy.deepcopy(base)
    changed["families"][0][component][field] = value
    assert_reason(base, changed, "frozen_set_moved_without_version_bump")

version_two = view(families=[family(version="2")])
decreased = view(families=[family(version="1")])
assert_reason(version_two, decreased, "platform_version_decreased")
changed_decreased = copy.deepcopy(decreased)
changed_decreased["families"][0]["kernel"]["sha"] = "k2"
assert_reason(version_two, changed_decreased, "platform_version_decreased")

for bad in (None, "", "-1", "1.2", True):
    malformed = view(families=[family(version=bad)])
    try:
        abi.validate_version_transition(base, malformed)
    except abi.VersionPolicyError:
        pass
    else:
        raise AssertionError(f"malformed version accepted: {bad!r}")

duplicate = view(families=[family(), family()])
for old, new in ((duplicate, base), (base, duplicate)):
    try:
        abi.validate_version_transition(old, new)
    except abi.VersionPolicyError:
        pass
    else:
        raise AssertionError("duplicate family accepted")

two_old = view(families=[family("f/a", "1"), family("f/b", "4")])
two_new = copy.deepcopy(two_old)
for item in two_new["families"]:
    item["kernel"]["sha"] = "k2"
two_new["families"][0]["platform_version"] = "2"
errors = abi.validate_version_transition(two_old, two_new)
assert [e["family"] for e in errors] == ["f/b"], errors
two_new["families"][1]["platform_version"] = "5"
assert_green(two_old, two_new)

interim_old = view("interim")
interim_moved = copy.deepcopy(interim_old)
interim_moved["families"][0]["kernel"]["sha"] = "k2"
assert_green(interim_old, interim_moved)
authoritative_bumped = copy.deepcopy(base)
authoritative_bumped["families"][0]["kernel"]["sha"] = "k2"
authoritative_bumped["families"][0]["platform_version"] = "2"
assert_green(base, authoritative_bumped)
assert_green(base, base)

metadata = copy.deepcopy(base)
metadata["families"][0]["alias"] = ["old/a"]
metadata["families"][0]["reproducible"] = True
metadata["families"][0]["provenance_ref"] = "ticket"
assert_green(base, metadata)
assert_green(base, view(families=[family(), family("f/new", "1")]))

older_set = copy.deepcopy(base)
older_set["families"][0]["kernel"]["sha"] = "old"
older_set["families"][0]["platform_version"] = "2"
assert_green(base, older_set)
assert_reason(base, view(families=[dict(family(), kernel={"repo": "kernel", "ref": "main", "sha": "old"})]),
              "frozen_set_moved_without_version_bump")
assert_reason(interim_old, base, "frozen_set_moved_without_version_bump")
assert_reason(base, interim_old, "authoritative_lock_downgrade")
assert_reason(two_old, view(families=[family("f/a", "1")]), "baseline_family_missing")

with tempfile.TemporaryDirectory() as tmp:
    missing = os.path.join(tmp, "missing.json")
    try:
        abi._load_baseline(path=missing)
    except abi.VersionPolicyError:
        pass
    else:
        raise AssertionError("missing baseline file accepted")

print("PLATFORM VERSION POLICY OK")
