#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tomllib
import unittest
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pf_profile", ROOT / "core/profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)

NORMAL_DEVICE = "a133-open-7x-gpu"
TRACE_DEVICE = "a133-open-7x-gpu-spl-trace"
MERGED_UBOOT_SHA = "c7595dcf4edb28abfed2ba9e377a4a350cd0a53b"


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
        self.assertEqual(normal_args["PF_UBOOT_SHA"], MERGED_UBOOT_SHA)
        self.assertEqual(trace_args["PF_UBOOT_SHA"], MERGED_UBOOT_SHA)


if __name__ == "__main__":
    unittest.main()
