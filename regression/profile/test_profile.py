#!/usr/bin/env python3
import copy
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pf_profile", ROOT / "core/profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ProfileTest(unittest.TestCase):
    def test_closed_and_open_resolve_exact_shas(self):
        closed, _, closed_missing = profile.build_args("a133")
        opened, _, open_missing = profile.build_args("a133-open")
        self.assertEqual(closed_missing, [])
        self.assertEqual(open_missing, [])
        self.assertEqual(closed["PF_KERNEL_SHA"], "a7cfec247898bb2c22e51bb705a7f18fd5910285")
        self.assertEqual(closed["PF_GPU_MODEL"], "ddk")
        self.assertEqual(closed["PF_GPU_REPO"], "gpu-km-tsp")
        self.assertIn("pvr-ddk-22.102.54.38", closed["PF_BLOB_GROUPS"])
        self.assertEqual(opened["PF_KERNEL_SHA"], "136518888335c0b23494690ed08f933e64a3f3dd")
        self.assertEqual(opened["PF_GPU_MODEL"], "open")
        self.assertEqual(opened["PF_GPU_KM_SHA"], opened["PF_KERNEL_SHA"])
        self.assertEqual(opened["PF_GPU_UM_SHA"], "43fc908f65edb4625a3553c0b62799539be16899")
        self.assertNotIn("pvr-ddk-22.102.54.38", opened["PF_BLOB_GROUPS"])

    def test_is_a133_signal_resolves_for_every_variant(self):
        # tsp-mc9m.41.924.2 / B1: PF_SOC is the declarative is-a133 discriminator that
        # replaces the PF_GPU_REPO proxy in Dockerfile.pf's gates (B2-B4). It must be
        # BASE-inherited so every a133 variant (closed/open/owned) resolves the same
        # value, and must clearly diverge for a523.
        for dev_id in ("a133", "a133-open", "a133-owned"):
            args, _, missing = profile.build_args(dev_id)
            self.assertEqual(missing, [], dev_id)
            self.assertEqual(args["PF_SOC"], "sun50iw10p1", dev_id)
        a523_args, _, a523_missing = profile.build_args("a523")
        self.assertEqual(a523_missing, [])
        self.assertEqual(a523_args["PF_SOC"], "sun55iw3")

    def test_missing_soc_fails_closed(self):
        # tsp-mc9m.41.924.2 / B1 review fix: PF_SOC is the ONLY is-a133 signal every
        # Dockerfile.pf gate trusts. A profile that omits [device].soc must fail LOUDLY
        # at validate() — never silently resolve to an empty PF_SOC that then silently
        # NOT-SHIPs every gated component with no error anywhere in the chain.
        original = profile.resolve
        resolved, family = original("a133-open")
        broken = copy.deepcopy(resolved)
        del broken["device"]["soc"]
        profile.resolve = lambda _dev: (broken, family)
        try:
            errors, _ = profile.validate("a133-open", profile.load_lock())
        finally:
            profile.resolve = original
        self.assertIn("a133-open: [device].soc is required", errors)

    def test_open_profile_missing_field_fails_closed(self):
        original = profile.resolve
        resolved, family = original("a133-open")
        broken = copy.deepcopy(resolved)
        del broken["gpu"]["um_ref"]
        profile.resolve = lambda _dev: (broken, family)
        try:
            errors, _ = profile.validate("a133-open", profile.load_lock())
        finally:
            profile.resolve = original
        self.assertIn("a133-open: open [gpu].um_ref is required", errors)

    def test_open_profile_legacy_repo_is_ambiguous(self):
        original = profile.resolve
        resolved, family = original("a133-open")
        broken = copy.deepcopy(resolved)
        broken["gpu"]["repo"] = "gpu-km-tsp"
        profile.resolve = lambda _dev: (broken, family)
        try:
            errors, _ = profile.validate("a133-open", profile.load_lock())
        finally:
            profile.resolve = original
        self.assertIn(
            "a133-open: open [gpu] is ambiguous: legacy repo/ref must be cleared",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
