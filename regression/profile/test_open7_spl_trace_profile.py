#!/usr/bin/env python3
import copy
import importlib.util
import json
import pathlib
import tomllib
import unittest
from unittest import mock
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pf_profile", ROOT / "core/profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)

NORMAL_DEVICE = "a133-open-7x-gpu"
TRACE_DEVICE = "a133-open-7x-gpu-spl-trace"
NORMAL_UBOOT_SHA = "1bc129ad26229bfe6037cf038c3d087a2450a18c"
TRACE_UBOOT_SHA = "1bc129ad26229bfe6037cf038c3d087a2450a18c"


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, dict):
        return {prefix: value}
    result = {}
    for key, nested_value in value.items():
        path = f"{prefix}.{key}" if prefix else key
        result.update(flatten(nested_value, path))
    return result


def differences(left: dict[str, Any], right: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    left_flat = flatten(left)
    right_flat = flatten(right)
    return {
        key: (left_flat.get(key), right_flat.get(key))
        for key in sorted(left_flat.keys() | right_flat.keys())
        if left_flat.get(key) != right_flat.get(key)
    }


class Open7SplTraceProfileTest(unittest.TestCase):
    def test_profile_is_a_sibling_with_only_the_guarded_trace_defconfig(self):
        normal_path = ROOT / "devices" / NORMAL_DEVICE / "profile.toml"
        trace_path = ROOT / "devices" / TRACE_DEVICE / "profile.toml"
        with normal_path.open("rb") as handle:
            normal_raw = tomllib.load(handle)
        with trace_path.open("rb") as handle:
            trace_raw = tomllib.load(handle)

        self.assertEqual(trace_raw["device"]["base"], "a133")
        self.assertEqual(
            differences(normal_raw, trace_raw),
            {
                "bootchain.uboot.defconfig": (
                    "tg5040_defconfig",
                    "tg5040_mmc_trace_defconfig",
                ),
                "device.id": (NORMAL_DEVICE, TRACE_DEVICE),
                "device.name": (
                    "TrimUI Smart Pro (v7.x open GPU)",
                    "TrimUI Smart Pro (v7.x open GPU, SPL trace)",
                ),
            },
        )

        normal_resolved, _ = profile.resolve(NORMAL_DEVICE)
        trace_resolved, _ = profile.resolve(TRACE_DEVICE)
        lock = profile.load_lock()
        normal_errors, _ = profile.validate(NORMAL_DEVICE, lock)
        trace_errors, _ = profile.validate(TRACE_DEVICE, lock)
        self.assertEqual(normal_errors, [])
        self.assertEqual(trace_errors, [])
        self.assertEqual(
            differences(normal_resolved, trace_resolved),
            {
                "bootchain.uboot.defconfig": (
                    "tg5040_defconfig",
                    "tg5040_mmc_trace_defconfig",
                ),
                "device.id": (NORMAL_DEVICE, TRACE_DEVICE),
                "device.name": (
                    "TrimUI Smart Pro (v7.x open GPU)",
                    "TrimUI Smart Pro (v7.x open GPU, SPL trace)",
                ),
            },
        )

        golden_path = ROOT / "regression/profile" / f"{TRACE_DEVICE}-resolved.json"
        self.assertEqual(trace_resolved, json.loads(golden_path.read_text()))

        normal_args, _, normal_missing = profile.build_args(NORMAL_DEVICE)
        trace_args, _, trace_missing = profile.build_args(TRACE_DEVICE)
        self.assertEqual(normal_missing, [])
        self.assertEqual(trace_missing, [])
        self.assertEqual(
            differences(normal_args, trace_args),
            {
                "PF_DEVICE_ID": (NORMAL_DEVICE, TRACE_DEVICE),
                "PF_UBOOT_DEFCONFIG": (
                    "tg5040_defconfig",
                    "tg5040_mmc_trace_defconfig",
                ),
            },
        )
        self.assertEqual(normal_args["PF_UBOOT_REPO"], "u-boot-tsp-a133")
        self.assertEqual(trace_args["PF_UBOOT_REPO"], "u-boot-tsp-a133")
        self.assertEqual(normal_args["PF_UBOOT_SHA"], NORMAL_UBOOT_SHA)
        self.assertEqual(trace_args["PF_UBOOT_SHA"], TRACE_UBOOT_SHA)

    def test_trace_pin_is_lock_owned_without_changing_the_normal_repo_pin(self):
        lock = profile.load_lock()
        self.assertEqual(
            lock["repos"]["u-boot-tsp-a133"]["sha"],
            NORMAL_UBOOT_SHA,
        )
        self.assertEqual(
            lock["profile_pins"][TRACE_DEVICE],
            {"uboot": TRACE_UBOOT_SHA},
        )

    def test_malformed_profile_pin_fails_closed(self):
        lock_data = profile._load(ROOT / "platform.lock")
        cases = {
            "profile-entry-not-table": "not-a-table",
            "uboot-not-full-sha": {"uboot": "1299474"},
        }
        for label, pins in cases.items():
            with self.subTest(label=label):
                malformed = copy.deepcopy(lock_data)
                malformed["profile_pins"] = {TRACE_DEVICE: pins}
                with mock.patch.object(profile, "_load", return_value=malformed):
                    with self.assertRaises(profile.ProfileSchemaError):
                        profile.load_lock()

    def test_trace_override_does_not_hide_a_missing_source_repo_or_pin(self):
        for missing in ("repo", "sha"):
            lock = copy.deepcopy(profile.load_lock())
            if missing == "repo":
                del lock["repos"]["u-boot-tsp-a133"]
            else:
                del lock["repos"]["u-boot-tsp-a133"]["sha"]
            with self.subTest(missing=missing):
                with mock.patch.object(profile, "load_lock", return_value=lock):
                    for device in (NORMAL_DEVICE, TRACE_DEVICE):
                        with self.subTest(device=device):
                            args, _, missing_pins = profile.build_args(device)
                            self.assertEqual(args["PF_UBOOT_REPO"], "u-boot-tsp-a133")
                            self.assertEqual(args["PF_UBOOT_SHA"], "")
                            self.assertIn("PF_UBOOT_SHA", missing_pins)


if __name__ == "__main__":
    unittest.main()
