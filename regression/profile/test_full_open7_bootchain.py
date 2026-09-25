#!/usr/bin/env python3
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pf_profile", ROOT / "core/profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)

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
            "PF_UBOOT_SHA": "ec2adf4c1d139ce2c0906354a26fc541490b67c6",
            "PF_UBOOT_DEFCONFIG": "tg5040_defconfig",
            "PF_TFA_REPO": "tfa-tsp-a133",
            "PF_TFA_SHA": "199316464722231e1a818e0d3f927be9c0fc2798",
            "PF_TFA_PLAT": "sun50i_a133",
            "PF_SPL_OFFSET_KIB": "128",
        }
        self.assertEqual({key: args[key] for key in expected}, expected)

    def test_full7_non_boot_contract_is_the_preexisting_contract(self):
        resolved, _ = profile.resolve("a133-open-7x-gpu")
        non_boot = copy.deepcopy(resolved)
        del non_boot["bootchain"]
        canonical = json.dumps(non_boot, sort_keys=True, separators=(",", ":"))
        self.assertEqual(
            hashlib.sha256(canonical.encode()).hexdigest(),
            "3fb46fb498f9f1e35c47d856d848e50a9dd4d7d70221f8c720e2af3f70d38515",
        )

        args, _, missing = profile.build_args("a133-open-7x-gpu")
        self.assertEqual(missing, [])
        expected = {
            "PF_KERNEL_REPO": "kernel-sunxi-7.x",
            "PF_KERNEL_SHA": "3e0a7373bddd5a801f5f07a71d02cf4d6e97e99d",
            "PF_KERNEL_DTB": "sun50i-a133-pocketforge-odyssey.dtb",
            "PF_KERNEL_REQUIRED_MODULES": "powervr",
            "PF_GPU_MODEL": "open",
            "PF_GPU_KM_MODEL": "in-tree-7.x",
            "PF_GPU_KM_REPO": "kernel-sunxi-7.x",
            "PF_GPU_KM_SHA": "3e0a7373bddd5a801f5f07a71d02cf4d6e97e99d",
            "PF_GPU_UM_REPO": "gpu-um-tsp",
            "PF_GPU_UM_SHA": "0dc9d15a65481267b79d9123c7add84e7e03eda2",
            "PF_LIBSDL3_SHA": "f5e73b52840129cdaaa288a71463cd548a91e2c5",
            "PF_DISPLAY_PIPELINE": "fbdev",
            "PF_LAUNCHER_REPO": "launcher",
            "PF_LAUNCHER_SHA": "bb8c9bc8c9ea15238d08cfee5376049bf67cf855",
            "PF_RECOVERY_REPO": "recovery",
            "PF_RECOVERY_SHA": "443a84e47c96d83de967948844d8e5eaa41d7413",
            "PF_BLOBS_SHA": "02ad8b7158ae39797f2693607ea9f2e6975f9ffd",
            "PF_VENDOR_MANIFEST_SHA": "3c8c5c537028e6f749f7888b05e85aa95aa88db4",
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


if __name__ == "__main__":
    unittest.main()
