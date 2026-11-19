#!/usr/bin/env python3
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import pathlib
import re
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pf_profile", ROOT / "core/profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)

# tsp-hqm1p.182.339: current pins are read from platform.lock, never copied here.
LOCK_PIN = {name: repo["sha"] for name, repo in profile.load_lock()["repos"].items()}
KERNEL_7X_SHA = profile.load_lock()["repos"]["kernel-sunxi-7.x"]["sha"]

OWNED_BOOTCHAIN = {
    "blob_group": "sunxi-a133-boot-chain",
    "boot_proto": "sunxi-spl-booti",
    "model": "sunxi-spl-uboot",
    "spl_offset_kib": 128,
    "tfa": {
        "plat": "sun50i_a133",
        "ref": "main",
        "repo": "tfa-tsp-a133",
    },
    "uboot": {
        "defconfig": "tg5040_defconfig",
        "ref": "main",
        "repo": "u-boot-tsp-a133",
    },
}

VENDOR_BOOTCHAIN = {
    "blob_group": "sunxi-a133-boot-chain",
    "boot_proto": "boot_package_fex",
    "model": "sunxi-boot0-fex",
}


class FullOpen7BootchainTest(unittest.TestCase):
    def test_full7_resolves_owned_bootchain_and_locked_source_pins(self):
        resolved, _ = profile.resolve("a133-open-7x-gpu")
        self.assertEqual(resolved["bootchain"], OWNED_BOOTCHAIN)

        args, _state, missing = profile.build_args("a133-open-7x-gpu")
        self.assertEqual(missing, [])
        expected = {
            "PF_BOOTCHAIN_MODEL": "sunxi-spl-uboot",
            "PF_BOOT_PROTO": "sunxi-spl-booti",
            "PF_UBOOT_REPO": "u-boot-tsp-a133",
            "PF_UBOOT_SHA": LOCK_PIN["u-boot-tsp-a133"],
            "PF_UBOOT_DEFCONFIG": "tg5040_defconfig",
            "PF_TFA_REPO": "tfa-tsp-a133",
            "PF_TFA_SHA": LOCK_PIN["tfa-tsp-a133"],
            "PF_TFA_PLAT": "sun50i_a133",
            "PF_SPL_OFFSET_KIB": "128",
        }
        self.assertEqual({key: args[key] for key in expected}, expected)

    def test_full7_non_boot_contract_is_the_preexisting_contract(self):
        resolved, _ = profile.resolve("a133-open-7x-gpu")
        non_boot = copy.deepcopy(resolved)
        del non_boot["bootchain"]
        # App-runtime and the profile-local Gamescope package selector are the
        # admitted non-boot additions; everything beneath them remains fixed.
        non_boot.pop("app_runtime", None)
        non_boot.pop("gamescope", None)
        canonical = json.dumps(non_boot, sort_keys=True, separators=(",", ":"))
        self.assertEqual(
            hashlib.sha256(canonical.encode()).hexdigest(),
            "3fb46fb498f9f1e35c47d856d848e50a9dd4d7d70221f8c720e2af3f70d38515",
        )

        args, _, missing = profile.build_args("a133-open-7x-gpu")
        self.assertEqual(missing, [])
        expected = {
            "PF_IMAGE_SHA": "945c5310fe63a3be3c16b166ebaaa8d9616c0fc0",
            "PF_RUNTIME_SHA": LOCK_PIN["runtime"],
            "PF_KERNEL_REPO": "kernel-sunxi-7.x",
            "PF_KERNEL_SHA": KERNEL_7X_SHA,
            "PF_KERNEL_DTB": "sun50i-a133-pocketforge-odyssey.dtb",
            "PF_KERNEL_REQUIRED_MODULES": "powervr",
            "PF_GPU_MODEL": "open",
            "PF_GPU_KM_MODEL": "in-tree-7.x",
            "PF_GPU_KM_REPO": "kernel-sunxi-7.x",
            "PF_GPU_KM_SHA": KERNEL_7X_SHA,
            "PF_GPU_UM_REPO": "gpu-um-tsp",
            "PF_GPU_UM_SHA": LOCK_PIN["gpu-um-tsp"],
            "PF_LIBSDL3_SHA": LOCK_PIN["libsdl3-sunxifb"],
            "PF_DISPLAY_PIPELINE": "fbdev",
            "PF_LAUNCHER_REPO": "launcher",
            "PF_LAUNCHER_SHA": LOCK_PIN["launcher"],
            "PF_RECOVERY_REPO": "recovery",
            "PF_RECOVERY_SHA": LOCK_PIN["recovery"],
            "PF_BLOBS_SHA": LOCK_PIN["blobs"],
            "PF_VENDOR_MANIFEST_SHA": LOCK_PIN["vendor-manifest"],
            "PF_BLOB_GROUPS": (
                "pvr-fw-open-22.102.54.38 sunxi-a133-boot-chain "
                "sunxi-a133-wifi-firmware"
            ),
        }
        self.assertEqual({key: args[key] for key in expected}, expected)

    def test_minimal_open7_remains_vendor_boot_and_gpu_less(self):
        resolved, _ = profile.resolve("a133-open-7x")
        self.assertEqual(resolved["bootchain"], VENDOR_BOOTCHAIN)
        self.assertEqual(resolved["gpu"]["model"], "none")
        self.assertEqual(resolved["gpu"]["modules"], [])
        self.assertEqual(resolved["display"]["pipeline"], "none")

    def test_noradio_profile_carries_the_canonical_kernel(self):
        args, _state, missing = profile.build_args("a133-open-7x-gpu-noradio")
        self.assertEqual(missing, [])
        canonical_kernel = KERNEL_7X_SHA
        self.assertEqual(args["PF_KERNEL_SHA"], canonical_kernel)
        self.assertEqual(args["PF_GPU_KM_SHA"], canonical_kernel)

    def test_existing_a133_bootchain_contracts_are_unchanged(self):
        expected = {
            "a133": VENDOR_BOOTCHAIN,
            "a133-open": VENDOR_BOOTCHAIN,
            "a133-owned": OWNED_BOOTCHAIN,
        }
        for device, bootchain in expected.items():
            with self.subTest(device=device):
                resolved, _ = profile.resolve(device)
                self.assertEqual(resolved["bootchain"], bootchain)

    def test_missing_owned_source_lock_entries_fail_closed(self):
        cases = {
            "u-boot-tsp-a133": "PF_UBOOT_SHA",
            "tfa-tsp-a133": "PF_TFA_SHA",
        }
        for repo_name, missing_arg in cases.items():
            with self.subTest(repo=repo_name, build_arg=missing_arg):
                lock = copy.deepcopy(profile.load_lock())
                del lock["repos"][repo_name]
                stdout = io.StringIO()
                stderr = io.StringIO()
                with mock.patch.object(profile, "load_lock", return_value=lock):
                    args, _state, missing = profile.build_args("a133-open-7x-gpu")
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        status = profile.main(["buildargs", "a133-open-7x-gpu"])
                self.assertEqual(args[missing_arg], "")
                self.assertEqual(missing, [missing_arg])
                # buildargs deliberately emits the missing-pin surface; pf-build.sh
                # treats any non-empty PF_LOCK_MISSING_SHAS value as a hard failure.
                self.assertEqual(status, 0)
                self.assertEqual(stderr.getvalue(), "")
                self.assertIn(f"{missing_arg}=\n", stdout.getvalue())
                self.assertIn(
                    f"PF_LOCK_MISSING_SHAS={missing_arg}\n",
                    stdout.getvalue(),
                )

    def test_full7_golden_is_exact_resolver_output(self):
        resolved, _ = profile.resolve("a133-open-7x-gpu")
        with open(
            ROOT / "regression/profile/a133-open-7x-gpu-resolved.json",
            encoding="utf-8",
        ) as golden_file:
            self.assertEqual(json.load(golden_file), resolved)

    def test_owned_spl_ledger_image_pin_matches_platform_lock(self):
        document = (ROOT / "docs/A133-OPEN-7X-OWNED-SPL.md").read_text(
            encoding="utf-8"
        )
        match = re.search(
            r"^- Image source pin: `([0-9a-f]{40})`",
            document,
            re.MULTILINE,
        )
        self.assertIsNotNone(match, "owned-SPL ledger lacks an image source pin")
        current = profile.load_lock()["repos"]["image"]["sha"]
        self.assertEqual(match.group(1), current)

        stale = document.replace(match.group(1), "0" * 40, 1)
        stale_match = re.search(
            r"^- Image source pin: `([0-9a-f]{40})`",
            stale,
            re.MULTILINE,
        )
        self.assertIsNotNone(stale_match)
        self.assertNotEqual(stale_match.group(1), current)


if __name__ == "__main__":
    unittest.main()
