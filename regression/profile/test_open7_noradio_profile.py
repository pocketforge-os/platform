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
NORADIO_DEVICE = "a133-open-7x-gpu-noradio"
NORMAL_KERNEL_SHA = "ea46664cf1695e83be3bd3bfb2bc14c0276b2e59"
# tsp-mc9m.41.923.42 lock: the explicit no-radio kernel pin equalled the canonical pin
# (the bisect-era 0a475ab5 predates FB_DEVICE and the PL8 SD fix). gpu-14 kernel batch
# lock: it is NOT moved with the canonical 23cdf7bf -> 6955e721, so it now differs
# (no automation gate requires equality; run-build.sh only checks the resolved noradio
# kernel against this pin). It stays a separate lock-owned entry. gpu-14 lock k#67: again
# NOT moved with the canonical 6955e721 -> a5418af4. gpu-14 lock k#68: again NOT moved
# with the canonical a5418af4 -> 3434d3fd (#69's TSP USB1-disabled DTS change does not
# reach this frozen checkout; see platform.lock's note). The reboot-rail pin likewise leaves
# the override held while the canonical pin moves 3434d3fd -> 40ea8fd9. The PowerVR recovery
# batch again leaves it held while the canonical pin moves 40ea8fd9 -> a75bf257. The
# Cedrus SRAM/poll fix likewise leaves it held while the canonical pin moves to 671e7090.
# The PowerVR MMU/freelist and DTB-guard batch again leaves it held while the canonical
# pin moves to a65b6107; it remains an explicit diagnostic override.
NORADIO_KERNEL_SHA = "23cdf7bf4642c234901caf0bcd4f70dd89c73276"
NORMAL_UBOOT_SHA = "db70249c8b25b7c3271cce71a19005b361527aaf"


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
    """Keep this sibling-profile assertion independent of selected payload args."""
    return {
        key: value for key, value in args.items()
        if not (key == "PF_STEAMLINK_FFMPEG59_MODE" or key.startswith("PF_FFMPEG_")
                or key.startswith("PF_GAMESCOPE_"))
    }


class Open7NoradioProfileTest(unittest.TestCase):
    def test_profile_is_a_sibling_with_only_diagnostic_identity_and_dtb(self):
        normal_path = ROOT / "devices" / NORMAL_DEVICE / "profile.toml"
        noradio_path = ROOT / "devices" / NORADIO_DEVICE / "profile.toml"
        with normal_path.open("rb") as handle:
            normal_raw = tomllib.load(handle)
        with noradio_path.open("rb") as handle:
            noradio_raw = tomllib.load(handle)

        expected = {
            "device.id": (NORMAL_DEVICE, NORADIO_DEVICE),
            "device.name": (
                "TrimUI Smart Pro (v7.x open GPU)",
                "TrimUI Smart Pro (v7.x open GPU, no radios)",
            ),
            "kernel.dtb": (
                "sun50i-a133-pocketforge-odyssey.dtb",
                "sun50i-a133-pocketforge-odyssey-a133-open-7x-gpu-noradio.dtb",
            ),
        }
        self.assertEqual(noradio_raw["device"]["base"], "a133")
        normal_raw.pop("gamescope")
        self.assertEqual(differences(normal_raw, noradio_raw), expected)

        normal_resolved, _ = profile.resolve(NORMAL_DEVICE)
        noradio_resolved, _ = profile.resolve(NORADIO_DEVICE)
        lock = profile.load_lock()
        normal_errors, _ = profile.validate(NORMAL_DEVICE, lock)
        noradio_errors, _ = profile.validate(NORADIO_DEVICE, lock)
        self.assertEqual(normal_errors, [])
        self.assertEqual(noradio_errors, [])
        normal_resolved.pop("gamescope")
        self.assertEqual(differences(normal_resolved, noradio_resolved), expected)

        golden_path = ROOT / "regression/profile" / f"{NORADIO_DEVICE}-resolved.json"
        self.assertEqual(noradio_resolved, json.loads(golden_path.read_text()))

    def test_build_args_change_only_identity_dtb_and_held_kernel(self):
        normal_args, _, normal_missing = profile.build_args(NORMAL_DEVICE)
        noradio_args, _, noradio_missing = profile.build_args(NORADIO_DEVICE)
        self.assertEqual(normal_missing, [])
        self.assertEqual(noradio_missing, [])
        self.assertEqual(
            differences(without_platform_runtime(normal_args), noradio_args),
            # The identity, selected DTB, and held kernel override (since the gpu-14
            # kernel batch lock; the in-tree GPU KM SHA follows the kernel) differ.
            {
                "PF_DEVICE_ID": (NORMAL_DEVICE, NORADIO_DEVICE),
                "PF_KERNEL_DTB": (
                    "sun50i-a133-pocketforge-odyssey.dtb",
                    "sun50i-a133-pocketforge-odyssey-a133-open-7x-gpu-noradio.dtb",
                ),
                "PF_KERNEL_SHA": (NORMAL_KERNEL_SHA, NORADIO_KERNEL_SHA),
                "PF_GPU_KM_SHA": (NORMAL_KERNEL_SHA, NORADIO_KERNEL_SHA),
            },
        )
        self.assertEqual(normal_args["PF_KERNEL_SHA"], NORMAL_KERNEL_SHA)
        self.assertEqual(normal_args["PF_GPU_KM_SHA"], NORMAL_KERNEL_SHA)
        self.assertEqual(noradio_args["PF_KERNEL_SHA"], NORADIO_KERNEL_SHA)
        self.assertEqual(noradio_args["PF_GPU_KM_SHA"], NORADIO_KERNEL_SHA)
        self.assertEqual(normal_args["PF_UBOOT_SHA"], NORMAL_UBOOT_SHA)
        self.assertEqual(noradio_args["PF_UBOOT_SHA"], NORMAL_UBOOT_SHA)

    def test_noradio_pins_are_lock_owned_without_repinning_normal(self):
        lock = profile.load_lock()
        self.assertEqual(
            lock["repos"]["kernel-sunxi-7.x"]["sha"],
            NORMAL_KERNEL_SHA,
        )
        self.assertNotIn(NORMAL_DEVICE, lock["profile_pins"])
        self.assertEqual(
            lock["profile_pins"][NORADIO_DEVICE],
            {"kernel": NORADIO_KERNEL_SHA},
        )

    def test_malformed_profile_pin_fails_closed(self):
        lock_data = profile._load(ROOT / "platform.lock")
        cases = {
            "profile-entry-not-table": "not-a-table",
            "kernel-not-full-sha": {"kernel": "0a475ab"},
            "uboot-not-full-sha": {"uboot": "dfcc777"},
            "unknown-key": {"kernel": NORADIO_KERNEL_SHA, "image": "0" * 40},
        }
        for label, pins in cases.items():
            with self.subTest(label=label):
                malformed = copy.deepcopy(lock_data)
                malformed["profile_pins"] = {NORADIO_DEVICE: pins}
                with mock.patch.object(profile, "_load", return_value=malformed):
                    with self.assertRaises(profile.ProfileSchemaError):
                        profile.load_lock()

    def test_noradio_override_does_not_hide_missing_kernel_repo_or_pin(self):
        for missing in ("repo", "sha"):
            lock = copy.deepcopy(profile.load_lock())
            if missing == "repo":
                del lock["repos"]["kernel-sunxi-7.x"]
            else:
                del lock["repos"]["kernel-sunxi-7.x"]["sha"]
            with self.subTest(missing=missing):
                with mock.patch.object(profile, "load_lock", return_value=lock):
                    for device in (NORMAL_DEVICE, NORADIO_DEVICE):
                        with self.subTest(device=device):
                            args, _, missing_pins = profile.build_args(device)
                            self.assertEqual(args["PF_KERNEL_SHA"], "")
                            self.assertEqual(args["PF_GPU_KM_SHA"], "")
                            self.assertIn("PF_KERNEL_SHA", missing_pins)
                            self.assertIn("PF_GPU_KM_SHA", missing_pins)

    def test_unknown_and_near_match_selectors_fail_closed(self):
        for device in (
            "a133-open-7x-gpu-noradio-extra",
            "a133-open-7x-gpu-no-radio",
            "unknown",
        ):
            with self.subTest(device=device):
                with self.assertRaises(FileNotFoundError):
                    profile.resolve(device)


if __name__ == "__main__":
    unittest.main()
