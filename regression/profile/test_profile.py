#!/usr/bin/env python3
import copy
import hashlib
import importlib.util
import json
import pathlib
import re
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pf_profile", ROOT / "core/profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ProfileTest(unittest.TestCase):
    def test_existing_profiles_resolve_unchanged(self):
        # Canonical hashes were generated from origin/main (48d20a4) before this
        # branch added a133-open-7x. They pin every pre-existing profile's entire
        # resolved shape, not merely the fields consumed by today's build args.
        expected = {
            "a133": "123423ea4a97007817409cda84f6eb65cf717d1c5db1102e84fdf3dcceec595f",
            "a133-open": "309c3b76951dd73977a759a80372337ecf33308f28f9048a2ba1d0285e1d99ac",
            "a133-owned": "60d57c2b2f30f17abffcb5a3b6b812f78c7c2e3cb27bb412f916846b5cf273dc",
            "a523": "f6657f92c62dea6bbf6a8559568480e5ed8460c7084516d2c9e861d489e98eab",
            "sdm845": "7405a184a60591c3ede8a806046e74537ab9d328f83cf8b7889439427db048ff",
        }
        self.assertEqual(set(profile.list_devices()) - {"a133-open-7x"}, set(expected))
        for dev_id, digest in expected.items():
            resolved, _ = profile.resolve(dev_id)
            # Removing the one newly-added fact must reproduce the historical
            # complete-resolution digest exactly.
            without_display = copy.deepcopy(resolved)
            del without_display["display"]
            canonical = json.dumps(without_display, sort_keys=True, separators=(",", ":"))
            self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), digest, dev_id)

    def test_display_pipeline_is_pinned_for_every_profile(self):
        expected = {
            "a133": "fbdev",
            "a133-open": "fbdev",
            "a133-open-7x": "none",
            "a133-owned": "fbdev",
            "a523": "fbdev",
            "sdm845": "drm",
        }
        self.assertEqual(set(profile.list_devices()), set(expected))
        for dev_id, pipeline in expected.items():
            resolved, _ = profile.resolve(dev_id)
            self.assertEqual(resolved["display"]["pipeline"], pipeline, dev_id)
            args, _, _ = profile.build_args(dev_id)
            self.assertEqual(args["PF_DISPLAY_PIPELINE"], pipeline, dev_id)
            env = dict(line.removeprefix("export ").split("=", 1)
                       for line in profile.env_lines(dev_id))
            self.assertEqual(json.loads(env["PF_DISPLAY_PIPELINE"]), pipeline, dev_id)

    def test_a133_7x_complete_resolved_shape(self):
        resolved, _ = profile.resolve("a133-open-7x")
        with open(ROOT / "regression/profile/a133-open-7x-resolved.json", encoding="utf-8") as f:
            expected = json.load(f)
        self.assertEqual(resolved, expected)

    def test_hwprobe_and_sim_are_empty_only_for_release(self):
        dev, _, dev_missing = profile.build_args("a133", "dev")
        release, _, release_missing = profile.build_args("a133", "release")
        self.assertEqual(dev_missing, [])
        self.assertEqual(release_missing, [])
        self.assertRegex(dev["PF_HWPROBE_SHA"], r"^[0-9a-f]{40}$")
        self.assertRegex(dev["PF_SIM_SHA"], r"^[0-9a-f]{40}$")
        self.assertEqual(release["PF_HWPROBE_SHA"], "")
        self.assertEqual(release["PF_SIM_SHA"], "")

    def test_closed_and_open_resolve_exact_shas(self):
        closed, _, closed_missing = profile.build_args("a133")
        opened, _, open_missing = profile.build_args("a133-open")
        self.assertEqual(closed_missing, [])
        self.assertEqual(open_missing, [])
        self.assertEqual(closed["PF_KERNEL_SHA"], "a7cfec247898bb2c22e51bb705a7f18fd5910285")
        self.assertEqual(closed["PF_GPU_MODEL"], "ddk")
        self.assertEqual(closed["PF_GPU_REPO"], "gpu-km-tsp")
        self.assertIn("pvr-ddk-22.102.54.38", closed["PF_BLOB_GROUPS"])
        self.assertEqual(opened["PF_KERNEL_SHA"], "6ccb87902144babc2838b03840c0413bf0941ab4")
        self.assertEqual(opened["PF_GPU_MODEL"], "open")
        self.assertEqual(opened["PF_GPU_KM_SHA"], opened["PF_KERNEL_SHA"])
        self.assertEqual(opened["PF_GPU_UM_SHA"], "0dc9d15a65481267b79d9123c7add84e7e03eda2")
        self.assertIn("pvr-fw-open-22.102.54.38", opened["PF_BLOB_GROUPS"])
        self.assertNotIn("pvr-ddk-22.102.54.38", opened["PF_BLOB_GROUPS"])
        # pf-shell launcher (tsp-mc9m.41.924.4 / top-coord RULING B): OPEN-ONLY. The launcher
        # SHA is emitted (and required) ONLY for the open path; it resolves EMPTY for the ddk
        # path so the Dockerfile launcher-ddk NOT-SHIPPED stub keeps the ddk images byte-identical.
        self.assertEqual(opened["PF_LAUNCHER_SHA"], "bb8c9bc8c9ea15238d08cfee5376049bf67cf855")
        self.assertEqual(opened["PF_LAUNCHER_REPO"], "launcher")
        self.assertEqual(closed["PF_LAUNCHER_SHA"], "")
        self.assertEqual(closed["PF_LAUNCHER_REPO"], "")
        # recovery entry (F16) is the same op5a wave — also OPEN-ONLY (top-coord RULING B).
        self.assertEqual(opened["PF_RECOVERY_SHA"], "443a84e47c96d83de967948844d8e5eaa41d7413")
        self.assertEqual(opened["PF_RECOVERY_REPO"], "recovery")
        self.assertEqual(closed["PF_RECOVERY_SHA"], "")
        self.assertEqual(closed["PF_RECOVERY_REPO"], "")

    def test_is_a133_signal_resolves_for_every_variant(self):
        # tsp-mc9m.41.924.2 / B1: PF_SOC is the declarative is-a133 discriminator that
        # replaces the PF_GPU_REPO proxy in Dockerfile.pf's gates (B2-B4). It must be
        # BASE-inherited so every a133 variant (closed/open/owned) resolves the same
        # value, and must clearly diverge for a523.
        for dev_id in ("a133", "a133-open", "a133-open-7x", "a133-owned"):
            args, _, missing = profile.build_args(dev_id)
            self.assertEqual(missing, [], dev_id)
            self.assertEqual(args["PF_SOC"], "sun50iw10p1", dev_id)
        a523_args, _, a523_missing = profile.build_args("a523")
        self.assertEqual(a523_missing, [])
        self.assertEqual(a523_args["PF_SOC"], "sun55iw3")
        # a523 is a ddk device: the pf-shell launcher + recovery entry must NOT be wired for it
        # (open-only), so their SHAs stay empty and it never stages/references launcher/recovery-src.
        self.assertEqual(a523_args["PF_LAUNCHER_SHA"], "")
        self.assertEqual(a523_args["PF_RECOVERY_SHA"], "")

    def test_a133_7x_is_explicitly_gpu_less(self):
        args, _, missing = profile.build_args("a133-open-7x")
        self.assertEqual(missing, [])
        self.assertEqual(args["PF_KERNEL_REPO"], "kernel-sunxi-7.x")
        self.assertEqual(args["PF_KERNEL_SHA"], "94b1cafddaf0693d5c9fc837ec90c0a8a8dbabfa")
        self.assertEqual(args["PF_KERNEL_DTB"], "sun50i-a133-pocketforge-tsp.dtb")
        self.assertEqual(args["PF_GPU_MODEL"], "none")
        self.assertEqual(args["PF_GPU_REPO"], "")
        self.assertEqual(args["PF_GPU_KM_REPO"], "")
        self.assertEqual(args["PF_GPU_UM_REPO"], "")
        self.assertEqual(args["PF_GPU_MODULES"], "")
        self.assertEqual(args["PF_LAUNCHER_SHA"], "")
        self.assertEqual(args["PF_RECOVERY_SHA"], "")
        self.assertNotIn("pvr-fw-open-22.102.54.38", args["PF_BLOB_GROUPS"])

    def test_gpu_less_profile_rejects_inherited_gpu_inputs(self):
        original = profile.resolve
        resolved, family = original("a133-open-7x")
        broken = copy.deepcopy(resolved)
        broken["gpu"]["modules"] = ["powervr.ko"]
        profile.resolve = lambda _dev: (broken, family)
        try:
            errors, _ = profile.validate("a133-open-7x", profile.load_lock())
        finally:
            profile.resolve = original
        self.assertIn(
            "a133-open-7x: none [gpu] must not select repos, refs, KM/UM models, or modules",
            errors,
        )

    def test_missing_or_invalid_display_pipeline_fails_closed(self):
        original = profile.resolve
        resolved, family = original("a133")
        for value in (None, "gpu-implied"):
            broken = copy.deepcopy(resolved)
            if value is None:
                del broken["display"]
            else:
                broken["display"]["pipeline"] = value
            profile.resolve = lambda _dev, candidate=broken: (candidate, family)
            try:
                errors, _ = profile.validate("a133", profile.load_lock())
            finally:
                profile.resolve = original
            self.assertIn(
                "a133: [display].pipeline is required and must be 'fbdev', 'drm', or 'none'",
                errors,
            )

    def test_scalar_sections_fail_on_normal_validation_path(self):
        source = (ROOT / "devices/a133/profile.toml").read_text(encoding="utf-8")
        sections = profile.PROFILE_TABLE_SECTIONS
        with tempfile.TemporaryDirectory() as tmp:
            devices = pathlib.Path(tmp)
            device_dir = devices / "a133"
            device_dir.mkdir()
            with mock.patch.object(profile, "DEVICES", str(devices)):
                for section in sections:
                    with self.subTest(section=section):
                        without_section, count = re.subn(
                            rf"(?ms)^\[{re.escape(section)}\]\n.*?(?=^\[|\Z)",
                            "",
                            source,
                        )
                        self.assertEqual(count, 1, section)
                        # Root keys must precede every table header in TOML; putting
                        # this at the removed block's old position would attach it
                        # to the preceding table instead of malformed the section.
                        broken = f'{section} = "not-a-table"\n' + without_section
                        (device_dir / "profile.toml").write_text(broken, encoding="utf-8")
                        errors, _ = profile.validate("a133", profile.load_lock())
                        self.assertIn(f"a133: [{section}] must be a table", errors)
                        self.assertFalse(any("cannot load/parse" in error for error in errors))

                for section in ("uboot", "tfa"):
                    with self.subTest(section=f"bootchain.{section}"):
                        broken, count = re.subn(
                            r"(?m)^\[bootchain\]$",
                            f'[bootchain]\n{section} = "not-a-table"',
                            source,
                        )
                        self.assertEqual(count, 1)
                        (device_dir / "profile.toml").write_text(broken, encoding="utf-8")
                        errors, _ = profile.validate("a133", profile.load_lock())
                        self.assertIn(f"a133: [bootchain.{section}] must be a table", errors)

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
