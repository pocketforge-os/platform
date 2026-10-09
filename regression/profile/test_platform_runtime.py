#!/usr/bin/env python3
"""Lock-owned, exact-profile platform runtime selection (tsp-mc9m.41.996.2)."""
import copy
import importlib.util
import pathlib
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pf_profile_runtime", ROOT / "core/profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)

SELECTED = "a133-open-7x-gpu"
UAPI_SHA = "16d3cc8e1204f074000fb4a44d95b1ee0e46e3dc"
EXPECTED_ARGS = {
    "PF_STEAMLINK_FFMPEG59_MODE": "v1",
    "PF_FFMPEG_DEBIAN_VERSION": "7:5.1.8-0+deb12u1",
    "PF_FFMPEG_DSC_SHA256": "5c84a3fb58051cb60564ca58e7ba3a91d7140f501883ba02adba5a770f508154",
    "PF_FFMPEG_ORIG_SHA256": "56d4daf10c17330a45c8fe11bc260997677ca2432d3d5951dbeb5515c26028cb",
    "PF_FFMPEG_ORIG_ASC_SHA256": "ee93598ac566d1be4a80801e0a58f91ede2e6a5e9e670f681723b447f23c59d0",
    "PF_FFMPEG_DEBIAN_SHA256": "16f8a5bd8209f55490cb94d5f8da116c7ab800f622e9a39512921680090952e1",
    "PF_FFMPEG_PATCH_SERIES_SHA256": "e4deeb6282ef6eeebf4a88da8c821d960f405474af3a1ba291b711dee56e90e9",
    "PF_FFMPEG_UAPI_SHA": UAPI_SHA,
}


class PlatformRuntimeTest(unittest.TestCase):
    def test_exact_profile_gets_exact_lock_owned_build_args(self):
        lock = profile.load_lock()
        runtime = lock["platform_runtime"]["steamlink_ffmpeg59_v1"]
        self.assertEqual(runtime["profile"], SELECTED)
        self.assertEqual(runtime["runtime_path"],
                         "/usr/lib/pocketforge/platform-runtimes/steamlink-ffmpeg59/v1")
        self.assertEqual(runtime["source_repo"], "kernel-sunxi-7.x")
        self.assertEqual(runtime["source_sha"], UAPI_SHA)
        self.assertEqual(lock["repos"][runtime["source_repo"]]["sha"], UAPI_SHA)

        args, _, missing = profile.build_args(SELECTED)
        self.assertEqual(missing, [])
        self.assertEqual(
            {key: args[key] for key in EXPECTED_ARGS if key in args}, EXPECTED_ARGS)

    def test_only_selected_profile_and_explicit_child_select_payload(self):
        payload_keys = set(EXPECTED_ARGS)
        for device in profile.list_devices():
            if device in {SELECTED, "a133-open-7x-gpu-cts"}:
                continue
            with self.subTest(device=device):
                args, _, _ = profile.build_args(device)
                self.assertTrue(payload_keys.isdisjoint(args))

    def test_source_revision_must_match_profile_resolved_kernel(self):
        lock = copy.deepcopy(profile.load_lock())
        lock["platform_runtime"]["steamlink_ffmpeg59_v1"]["source_sha"] = "1" * 40
        with mock.patch.object(profile, "load_lock", return_value=lock):
            with self.assertRaisesRegex(profile.ProfileSchemaError, "does not match"):
                profile.build_args(SELECTED)

    def test_runtime_selector_must_name_an_existing_profile(self):
        lock_document = copy.deepcopy(profile._load(ROOT / "platform.lock"))
        lock_document["platform_runtime"]["steamlink_ffmpeg59_v1"]["profile"] = \
            "a133-open-7x-gp"
        with mock.patch.object(profile, "_load", return_value=lock_document):
            with self.assertRaisesRegex(profile.ProfileSchemaError, "is not a device profile"):
                profile.load_lock()

    def test_lock_schema_fails_closed(self):
        good = profile._load(ROOT / "platform.lock")
        cases = {}
        malformed = copy.deepcopy(good)
        malformed["platform_runtime"] = []
        cases["not-table"] = malformed
        malformed = copy.deepcopy(good)
        malformed["platform_runtime"]["steamlink_ffmpeg59_v1"]["schema_version"] = 2
        cases["schema"] = malformed
        malformed = copy.deepcopy(good)
        malformed["platform_runtime"]["steamlink_ffmpeg59_v1"]["mode_arg"] = "unsafe"
        cases["mode-arg"] = malformed
        malformed = copy.deepcopy(good)
        malformed["platform_runtime"]["steamlink_ffmpeg59_v1"]["source_sha"] = "2" * 40
        cases["canonical-source"] = malformed
        malformed = copy.deepcopy(good)
        malformed["platform_runtime"]["steamlink_ffmpeg59_v1"]["build_args"]["lower"] = "x"
        cases["build-arg"] = malformed
        for label, document in cases.items():
            with self.subTest(label=label), mock.patch.object(profile, "_load", return_value=document):
                with self.assertRaises(profile.ProfileSchemaError):
                    profile.load_lock()

    def test_core_runtime_resolver_stays_implementation_agnostic(self):
        source = (ROOT / "core/profile.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("steamlink", source)
        self.assertNotIn("ffmpeg", source)


if __name__ == "__main__":
    unittest.main()
