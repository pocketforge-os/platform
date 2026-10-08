#!/usr/bin/env python3
"""Profile-scoped, SHA-pinned CTS image payload contract."""
import copy
import importlib.util
import pathlib
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pf_profile_cts", ROOT / "core/profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)

SELECTED = "a133-open-7x-gpu-cts"
BASE = "a133-open-7x-gpu"
SHA256 = "9ce9b9c252c1b288ffb4a58dd8e976fd35110b4e2b1d9cc1a3a0cd3be13e5125"
URL = (
    "http://10.0.40.90:8790/artifacts/sha256/"
    f"{SHA256}/pf-deqp-gles-aarch64.tar.gz"
)
EXPECTED_ARGS = {
    "PF_CTS_BUNDLE_MODE": "v1",
    "PF_CTS_BUNDLE_URL": URL,
    "PF_CTS_BUNDLE_SHA256": SHA256,
}
EXPECTED_RECEIPT_ARGS = {
    "PF_CTS_SOURCE_TAG": "opengl-es-cts-3.2.14.1",
    "PF_CTS_SOURCE_COMMIT": "067e8832315e79817ede1c4863804e440f5d1c80",
    "PF_CTS_SOURCE_ARCHIVE_SHA256":
        "ce9f37f536373b6d616cdf854876477be79503999b655d90bb2e0e9483d502df",
    "PF_CTS_LIST_COUNT": "13",
    "PF_CTS_CASE_COUNT": "124248",
    "PF_CTS_SURFACES": "pbuffer:256x256,pbuffer:64x64",
    "PF_CTS_SOURCE_DATE_EPOCH": "0",
}


class CtsPayloadTest(unittest.TestCase):
    def test_profile_inherits_base_and_selects_exact_dev_payload(self):
        selected, _ = profile.resolve(SELECTED)
        base, _ = profile.resolve(BASE)
        self.assertEqual(selected["device"]["id"], SELECTED)
        self.assertEqual(selected["device"]["base"], BASE)
        for section in selected:
            if section != "device":
                self.assertEqual(selected[section], base[section], section)

        args, _, missing = profile.build_args(SELECTED, "dev")
        self.assertEqual(missing, [])
        self.assertEqual({key: args[key] for key in EXPECTED_ARGS}, EXPECTED_ARGS)
        self.assertEqual(
            {key: args[key] for key in EXPECTED_RECEIPT_ARGS},
            EXPECTED_RECEIPT_ARGS,
        )
        base_args, _, base_missing = profile.build_args(BASE, "dev")
        self.assertEqual(base_missing, [])
        inherited_runtime = {
            key: value for key, value in base_args.items()
            if key == "PF_STEAMLINK_FFMPEG59_MODE" or key.startswith("PF_FFMPEG_")
        }
        self.assertEqual(
            {key: args[key] for key in inherited_runtime}, inherited_runtime)

    def test_base_other_profiles_and_release_do_not_select_cts(self):
        payload_keys = set(EXPECTED_ARGS)
        for device in profile.list_devices():
            if device == SELECTED:
                continue
            with self.subTest(device=device):
                args, _, _ = profile.build_args(device, "dev")
                self.assertTrue(payload_keys.isdisjoint(args))
        release_args, _, _ = profile.build_args(SELECTED, "release")
        self.assertTrue(payload_keys.isdisjoint(release_args))

    def test_lock_schema_rejects_wrong_sha_url_profile_and_variant(self):
        good = profile._load(ROOT / "platform.lock")
        cases = {}
        for label, key, value in (
            ("sha", "artifact_sha256", "0" * 64),
            ("url", "artifact_url", "http://store.invalid/not-content-addressed"),
            ("profile", "profile", "a133-open-7x-gpu-missing"),
            ("variant", "variants", ["release"]),
        ):
            malformed = copy.deepcopy(good)
            malformed["platform_payload"]["cts_bundle_v1"][key] = value
            cases[label] = malformed
        for label, document in cases.items():
            with self.subTest(label=label), mock.patch.object(
                    profile, "_load", return_value=document):
                with self.assertRaises(profile.ProfileSchemaError):
                    profile.load_lock()

    def test_core_payload_resolver_stays_implementation_agnostic(self):
        source = (ROOT / "core/profile.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("deqp", source)
        self.assertNotIn("khronos", source)


if __name__ == "__main__":
    unittest.main()
