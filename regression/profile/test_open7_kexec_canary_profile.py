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
CANARY_DEVICE = "a133-open-7x-gpu-kexec-canary"
KERNEL_SHA = "d84c506667f1b67645a95af871d194ac694477fb"


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


def without_platform_runtime(args: dict[str, Any]) -> dict[str, Any]:
    """Keep the sibling assertion independent of the normal-only payload selector."""
    return {
        key: value for key, value in args.items()
        if not (key == "PF_STEAMLINK_FFMPEG59_MODE" or key.startswith("PF_FFMPEG_"))
    }


class Open7KexecCanaryProfileTest(unittest.TestCase):
    def test_canary_is_bounded_to_identity_and_kernel_defconfig(self):
        with (ROOT / "devices" / NORMAL_DEVICE / "profile.toml").open("rb") as handle:
            normal_raw = tomllib.load(handle)
        with (ROOT / "devices" / CANARY_DEVICE / "profile.toml").open("rb") as handle:
            canary_raw = tomllib.load(handle)

        expected = {
            "device.id": (NORMAL_DEVICE, CANARY_DEVICE),
            "device.name": (
                "TrimUI Smart Pro (v7.x open GPU)",
                "TrimUI Smart Pro (v7.x open GPU, kexec canary)",
            ),
            "kernel.defconfig": ("a133_defconfig", "a133_kexec_canary.config"),
        }
        self.assertEqual(differences(normal_raw, canary_raw), expected)

        normal_resolved, _ = profile.resolve(NORMAL_DEVICE)
        canary_resolved, _ = profile.resolve(CANARY_DEVICE)
        self.assertEqual(differences(normal_resolved, canary_resolved), expected)
        lock = profile.load_lock()
        self.assertEqual(profile.validate(NORMAL_DEVICE, lock)[0], [])
        self.assertEqual(profile.validate(CANARY_DEVICE, lock)[0], [])

        golden_path = ROOT / "regression/profile" / f"{CANARY_DEVICE}-resolved.json"
        self.assertEqual(canary_resolved, json.loads(golden_path.read_text()))

    def test_buildargs_change_only_identity_and_defconfig(self):
        normal_args, _, normal_missing = profile.build_args(NORMAL_DEVICE)
        canary_args, _, canary_missing = profile.build_args(CANARY_DEVICE)
        self.assertEqual(normal_missing, [])
        self.assertEqual(canary_missing, [])
        self.assertEqual(
            differences(without_platform_runtime(normal_args), canary_args),
            {
                "PF_DEVICE_ID": (NORMAL_DEVICE, CANARY_DEVICE),
                "PF_KERNEL_DEFCONFIG": (
                    "a133_defconfig",
                    "a133_kexec_canary.config",
                ),
            },
        )
        self.assertEqual(normal_args["PF_KERNEL_DEFCONFIG"], "a133_defconfig")
        self.assertEqual(normal_args["PF_KERNEL_SHA"], KERNEL_SHA)
        self.assertEqual(canary_args["PF_KERNEL_SHA"], KERNEL_SHA)
        self.assertEqual(normal_args["PF_GPU_KM_SHA"], canary_args["PF_GPU_KM_SHA"])

    def test_canary_inherits_the_canonical_kernel_pin(self):
        lock = profile.load_lock()
        self.assertEqual(lock["repos"]["kernel-sunxi-7.x"]["sha"], KERNEL_SHA)
        self.assertNotIn(CANARY_DEVICE, lock["profile_pins"])


if __name__ == "__main__":
    unittest.main()
