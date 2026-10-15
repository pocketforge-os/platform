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
caps_spec = importlib.util.spec_from_file_location("pf_caps", ROOT / "core/caps.py")
caps = importlib.util.module_from_spec(caps_spec)
caps_spec.loader.exec_module(caps)

APP_RUNTIME = {
    "schema_version": 1,
    "runtime_family": "pocketforge/a133-powervr",
    "runtime_abi": "1",
    "platform_version": "20",
    "supported_capabilities": ["audio", "entropy", "input", "open_url", "settings"],
}
APP_BUILD_ARGS = {
    "PF_APP_RUNTIME_FAMILY": "pocketforge/a133-powervr",
    "PF_APP_RUNTIME_ABI": "1",
    "PF_APP_PLATFORM_VERSION": "20",
    "PF_APP_CAPABILITIES": "audio entropy input open_url settings",
}
A133_OPEN_PROFILES = {
    "a133-open",
    "a133-open-7x-gpu",
    "a133-open-7x-gpu-cts",
    "a133-open-7x-gpu-noradio",
    "a133-open-7x-gpu-spl-trace",
}


class ProfileTest(unittest.TestCase):
    def test_missing_platform_lock_keeps_buildargs_unseeded(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(profile, "LOCK", str(pathlib.Path(tmp) / "missing.lock")):
            for dev_id in profile.list_devices():
                for variant in ("dev", "release"):
                    with self.subTest(dev_id=dev_id, variant=variant):
                        merged, _family = profile.resolve(dev_id)
                        if merged.get("gamescope"):
                            # Preserve the pre-existing no-lock refusal for the
                            # governed-fork check; cursor defaults must not mask it
                            # with a KeyError first.
                            with self.assertRaisesRegex(
                                    profile.ProfileSchemaError,
                                    "source must be the governed PocketForge Gamescope fork"):
                                profile.build_args(dev_id, variant)
                            continue
                        args, state, _missing = profile.build_args(dev_id, variant)
                        self.assertEqual(state, "unseeded")
                        self.assertEqual(args["PF_CURSOR_THEME_SHA"], "")
                        self.assertEqual(args["PF_CURSOR_TOOLS_IMAGE"], "")
                        self.assertEqual(args["PF_CURSOR_TOOLS_RECIPE_SHA"], "")

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
        self.assertEqual(
            set(profile.list_devices()) - {
                "a133-open-7x",
                "a133-open-7x-gpu",
                "a133-open-7x-gpu-cts",
                "a133-open-7x-gpu-noradio",
                "a133-open-7x-gpu-spl-trace",
            },
            set(expected),
        )
        for dev_id, digest in expected.items():
            resolved, _ = profile.resolve(dev_id)
            # Removing the narrowly admitted metadata additions must reproduce
            # every historical profile's complete resolved shape exactly.
            without_display = copy.deepcopy(resolved)
            del without_display["display"]
            without_display["kernel"].pop("required_modules", None)
            without_display.pop("app_runtime", None)
            canonical = json.dumps(without_display, sort_keys=True, separators=(",", ":"))
            self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), digest, dev_id)

    def test_display_pipeline_is_pinned_for_every_profile(self):
        expected = {
            "a133": "fbdev",
            "a133-open": "fbdev",
            "a133-open-7x": "none",
            "a133-open-7x-gpu": "fbdev",
            "a133-open-7x-gpu-cts": "fbdev",
            "a133-open-7x-gpu-noradio": "fbdev",
            "a133-open-7x-gpu-spl-trace": "fbdev",
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

    def test_a133_open_complete_resolved_shape(self):
        resolved, _ = profile.resolve("a133-open")
        with open(ROOT / "regression/profile/a133-open-resolved.json", encoding="utf-8") as f:
            expected = json.load(f)
        self.assertEqual(resolved, expected)

    def test_a133_7x_gpu_complete_resolved_shape(self):
        resolved, _ = profile.resolve("a133-open-7x-gpu")
        with open(ROOT / "regression/profile/a133-open-7x-gpu-resolved.json",
                  encoding="utf-8") as f:
            expected = json.load(f)
        self.assertEqual(resolved, expected)

    def test_gamescope_source_tree_digest_is_required_lowercase_and_emitted(self):
        expected = "1582be24b260cf7633873fa54bc4e37bac944db086653eaa3c64edeba83af45d"
        resolved, _ = profile.resolve("a133-open-7x-gpu")
        self.assertEqual(resolved["gamescope"]["source_tree_sha256"], expected)
        args, _, missing = profile.build_args("a133-open-7x-gpu")
        self.assertEqual(missing, [])
        self.assertEqual(args["PF_GAMESCOPE_SOURCE_TREE_SHA256"], expected)

        for replacement in (None, expected.upper()):
            invalid = copy.deepcopy(resolved)
            if replacement is None:
                del invalid["gamescope"]["source_tree_sha256"]
            else:
                invalid["gamescope"]["source_tree_sha256"] = replacement
            with self.subTest(replacement=replacement), \
                    mock.patch.object(profile, "resolve", return_value=(invalid, {})):
                errors, _ = profile.validate(
                    "a133-open-7x-gpu", profile.load_lock())
                self.assertIn(
                    "a133-open-7x-gpu: [gamescope].source_tree_sha256 "
                    "must be a full SHA-256",
                    errors,
                )

    def test_gamescope_manifest_digest_matches_pinned_lock_declaration(self):
        lock = copy.deepcopy(profile.load_lock())
        lock["repos"]["gamescope"]["dependency_manifest_sha256"] = "0" * 64
        errors, _ = profile.validate("a133-open-7x-gpu", lock)
        self.assertIn(
            "a133-open-7x-gpu: [gamescope].dependency_manifest_sha256 must match "
            "the pinned repository declaration in platform.lock",
            errors,
        )

    def test_app_runtime_support_is_exactly_a133_open_for_both_variants(self):
        app_keys = set(APP_BUILD_ARGS)
        observed_open = set()
        for dev_id in profile.list_devices():
            resolved, _ = profile.resolve(dev_id)
            if "app_runtime" in resolved:
                observed_open.add(dev_id)
                self.assertEqual(resolved["app_runtime"], APP_RUNTIME, dev_id)
            for variant in ("dev", "release"):
                args, _, missing = profile.build_args(dev_id, variant)
                emitted = {key: args[key] for key in app_keys if key in args}
                if dev_id in A133_OPEN_PROFILES:
                    self.assertEqual(missing, [], (dev_id, variant))
                    self.assertEqual(emitted, APP_BUILD_ARGS, (dev_id, variant))
                else:
                    self.assertEqual(emitted, {}, (dev_id, variant))
        self.assertEqual(observed_open, A133_OPEN_PROFILES)

    def test_non_open_build_arg_goldens_are_byte_unchanged(self):
        # Generated from platform main c75b3304 before app-runtime support was added, then
        # regenerated for the default-apps step-6 lock move (tsp-mc9m.41.985; image re-pinned to
        # bba63941 for the image#140 harness disable), and again for tsp-mc9m.41.986 (image
        # 3aff434f: the PowerVR exp_hw_support customize-hook fix; the only payload change is
        # PF_IMAGE_SHA, verified by diffing the old and new payloads), and again for
        # tsp-f3fm.202.1.5 (runtime d75beedf + image f6e0ee14: the default-apps input broker; the
        # only payload changes are PF_RUNTIME_SHA and PF_IMAGE_SHA, verified the same way), and again for
        # tsp-mc9m.41.923.48 (kernel-sunxi-7.x 85fddb4b, CONFIG_FB_DEVICE=y: only the a133-open-7x rows
        # move, and their only payload change is PF_KERNEL_SHA, verified the same way), and again for
        # tsp-mc9m.41.923.42 (kernel-sunxi-7.x ee23555d, the PL8 usb1-vbus SD fix: again only the
        # a133-open-7x rows move, only PF_KERNEL_SHA, verified the same way), and again for
        # tsp-mc9m.41.923.53 (kernel 1b1da76f, image 27727a8f, poolsuite a89c2512: every row moves;
        # the only payload changes are PF_IMAGE_SHA on all rows, PF_POOLSUITE_SHA on dev rows and
        # PF_KERNEL_SHA on the a133-open-7x rows, verified the same way), and again for
        # tsp-3rd3.10 (image eeae9b40, then d53b4cab, + u-boot d34088eb: every row moves; the only payload changes are
        # PF_IMAGE_SHA on all rows and PF_UBOOT_SHA on the a133-owned rows, verified the same way),
        # and for its runtime 2ad0ca76 + launcher 96feb08c commit (only PF_RUNTIME_SHA, on every row;
        # PF_LAUNCHER_SHA moves only on open profiles, not in this table), and again for
        # tsp-3rd3.10 lock2 (image 2a3d2114, runtime 0955d8a8, u-boot c21fbfb8: PF_IMAGE_SHA and
        # PF_RUNTIME_SHA on every row, PF_UBOOT_SHA on the a133-owned rows, verified the same way),
        # and its kernel commit (2bfee8b5, rotation 90: only PF_KERNEL_SHA on the a133-open-7x rows);
        # and tsp-3rd3.10 lock3 (image ea5ed12e: only PF_IMAGE_SHA, every row; then kernel 44debb5a:
        # only PF_KERNEL_SHA on the a133-open-7x rows); and tsp-mc9m.41.924.16.12 (libsdl3-sunxifb
        # 576ae890: only PF_LIBSDL3_SHA, every row, verified the same way); and tsp-3rd3.14 (image
        # 40db72ec: only PF_IMAGE_SHA, every row; then libsdl3-sunxifb b91e26b3, tsp-f3fm.218: only
        # PF_LIBSDL3_SHA, every row; then kernel bea8779b: only PF_KERNEL_SHA on the a133-open-7x rows);
        # and tsp-f3fm.219 (runtime 7536aa1f: only PF_RUNTIME_SHA, every row, verified the same way;
        # then launcher 7a2b792d: no row moves, PF_LAUNCHER_SHA is open-only and not in this table;
        # then image 3c2ac542: only PF_IMAGE_SHA, every row); and tsp-mc9m.41.924.16.13 (libsdl3-sunxifb
        # 0141e53a: only PF_LIBSDL3_SHA, every row, verified the same way; gpu-um-tsp 035e397d moves
        # PF_GPU_UM_SHA, which is open-only and not in this table); and tsp-f3fm.220 (image 57e06ce8:
        # only PF_IMAGE_SHA, every row, verified the same way); and tsp-3rd3.16 (kernel 94ee6079: only
        # PF_KERNEL_SHA on the a133-open-7x rows, verified the same way); and tsp-3rd3.18 + .924.16.13.3
        # (image ed6b87dc, libsdl3-sunxifb 56194685, gpu-um-tsp 159df17d: PF_IMAGE_SHA and PF_LIBSDL3_SHA
        # on every row; PF_GPU_UM_SHA is open-only and not in this table; verified the same way); and
        # tsp-3rd3.17 + .924.16.13.3.1 (kernel 23cdf7bf, libsdl3-sunxifb cc71c00c: PF_LIBSDL3_SHA on every
        # row, PF_KERNEL_SHA on the a133-open-7x rows; old-vs-new payload diff shows no other field,
        # key, state or missing change); and gpu-14 lock tsp-mc9m.41.984.34.2 + tsp-f3fm.223 (image 87c94194:
        # only PF_IMAGE_SHA, every row; old-vs-new payload diff shows no other field, key, state or
        # missing change); and tsp-f3fm.224 (poolsuite aeb68670: PF_POOLSUITE_SHA only, verified the same way);
        # and tsp-f3fm.232 + tsp-f3fm.233.2 (poolsuite fe3c9abe: PF_POOLSUITE_SHA only on dev rows,
        # verified the same way);
        # and tsp-f3fm.233.1 (poolsuite c9d805f2: PF_POOLSUITE_SHA only on dev rows, verified the
        # same way);
        # and tsp-147u.14 logo lock (image f7714c02 + u-boot 24284b73: PF_IMAGE_SHA on every row and
        # PF_UBOOT_SHA on the a133-owned rows; old-vs-new payload diff shows no other field, key, state or
        # missing change, and each new payload equals the old one with exactly those substitutions);
        # and tsp-f3fm.227 (image 96e1eb13 + launcher ab9fb7fd: only PF_IMAGE_SHA, every row; PF_LAUNCHER_SHA
        # moves only on the open profiles, not in this table; verified the same way, open profiles included);
        # and tsp-op5a.439 (image#168 merge fed7823a + launcher 1ef9671a: only PF_IMAGE_SHA moves in every
        # row in this table; PF_LAUNCHER_SHA moves only on open profiles; verified with the same comparison);
        # and the tsp-147u.14 U-Boot revert (24284b73 -> c21fbfb8, device abort in initr_dm): only
        # PF_UBOOT_SHA on the a133-owned rows, verified the same way; and the tsp-147u.14 U-Boot probe
        # (c21fbfb8 -> 2a5610ed, u-boot#52 fix-forward, pending device proof): only PF_UBOOT_SHA on the
        # a133-owned rows, verified the same way; and the probe revert (2a5610ed -> c21fbfb8, bench B19
        # page-table abort on device): only PF_UBOOT_SHA on the a133-owned rows, verified the same way;
        # and the gpu-14 kernel batch lock (kernel 23cdf7bf -> 6955e721): only PF_KERNEL_SHA on the
        # a133-open-7x rows (PF_GPU_KM_SHA also moves on the open 7x-gpu profiles, not in this table;
        # the held no-radio kernel pin keeps those rows byte-identical), verified the same way;
        # and the gpu-14 lock k#67 + gpu-um#161 + sdl#27 (kernel 6955e721 -> a5418af4, gpu-um-tsp
        # a423c16e -> e5a0e008, libsdl3-sunxifb cc71c00c -> a2865266): PF_LIBSDL3_SHA on every row and
        # PF_KERNEL_SHA on the a133-open-7x rows (PF_GPU_KM_SHA and PF_GPU_UM_SHA move only on open
        # profiles, not in this table); on all 18 rows the new payload equals the old one with exactly
        # those substitutions, and no key, state or missing entry changes.
        # And the gpu-14 lock k#68 (kernel a5418af4 -> 3434d3fd: kernel-sunxi-7.x#68 tracefs+syscall
        # tracing, #43 sun4i-codec A133 analog output, #69 TSP USB1 disabled): only PF_KERNEL_SHA on
        # the a133-open-7x dev/release rows; the other 8 rows are byte-identical (diffed old vs new
        # payload: no other field, key, state or missing change). #69's TSP DTS edit does not touch
        # this table: the a133-open-7x-gpu/-noradio DTB rows are not members of this golden set, and
        # the no-radio kernel pin is NOT moved (see platform.lock), so it builds a frozen checkout.
        # The tsp-b4446e3ceb419c3f0d15.4 reboot-rail lock (kernel 3434d3fd -> 40ea8fd9) again
        # changes only PF_KERNEL_SHA on the a133-open-7x dev/release rows; the no-radio override
        # remains frozen and outside this table.
        # The tsp-60df20c562d859df6fc1 recovery/capability pin (kernel 40ea8fd9 -> a75bf257,
        # gpu-um-tsp eac0a8f4 -> c7d55c1a) again changes only PF_KERNEL_SHA on those two rows;
        # PF_GPU_UM_SHA and the kernel-coupled FFmpeg UAPI SHA move only on the full open profile.
        # The Stage A defaults + readback-fix lock (libsdl3-sunxifb a2865266 -> 7411a948,
        # gpu-um-tsp e5a0e008 -> e3569452) again changes PF_LIBSDL3_SHA on every row;
        # PF_GPU_UM_SHA changes only on open profiles, not in this table. The #163 readback
        # repair (gpu-um-tsp e3569452 -> 32a3fa91), #164 inverted-blit repair
        # (32a3fa91 -> ad28586e), #165 bounded CS dump (ad28586e -> 77f23ed2), and #167
        # odd-pitch staging readbacks (77f23ed2 -> eac0a8f4), then #168/#169/#171 capability
        # batch (eac0a8f4 -> c7d55c1a), likewise change only open profiles.
        # Against the
        # c75b3304-era digests the ONLY payload changes are the values of already-emitted
        # PF_IMAGE_SHA / PF_RUNTIME_SHA / PF_POOLSUITE_SHA (and PF_LAUNCHER_SHA on open profiles,
        # which are not in this table): no key added or removed, state and missing unchanged.
        # The tsp-mc9m.41.996.2 linked image pin (652b0b3a -> 4b92b6d6) again changes only the
        # already-emitted PF_IMAGE_SHA on these profiles; the new producer remains NOT-SHIPPED
        # because its mode argument is emitted only for the exact a133-open-7x-gpu profile.
        # The tsp-mc9m.41.924.29.1 source-lock refresh (4b92b6d6 -> 803f1f38) likewise changes
        # only the already-emitted PF_IMAGE_SHA; no profile or runtime selector changes. The
        # tsp-mc9m.41.924.29.3 native-fence/YUV batch (image 803f1f38 -> 623b33ea and gpu-um-tsp
        # c7d55c1a -> fd904962) again changes only PF_IMAGE_SHA in this non-open golden set;
        # PF_GPU_UM_SHA moves only on open profiles outside this table.
        # The tsp-e7ad6d3ba67d46e4c58b full GLES 3.0 lock (image 623b33ea -> 0ff637a9 and
        # gpu-um-tsp fd904962 -> 1d805654) likewise changes only PF_IMAGE_SHA here;
        # PF_GPU_UM_SHA remains open-only and outside this table.
        # The tsp-op5a.440.1.1 Gamescope packaging lock (image 0ff637a9 -> 6831e335)
        # again changes only the already-emitted PF_IMAGE_SHA on these profiles.
        # The tsp-mc9m.41.997.23.1.1 image#178 merge (6831e335 -> 12d8b9a1e8d1f986baa6673a15640d081c0b90fe)
        # likewise changes only PF_IMAGE_SHA on the A133 image-bearing profiles.
        # The tsp-35b9d6d1816b25822ebb.3 CMA lock moves image to 7a5bd0c5 and canonical
        # U-Boot to db70249c on top of tsp-mc9m.41.995.30.4's compatible image/runtime/
        # launcher generation. Image#181 then advances only PF_IMAGE_SHA to d81a1d7f while
        # retaining those co-pins. PF_IMAGE_SHA and PF_RUNTIME_SHA change on every image-bearing
        # row; PF_UBOOT_SHA changes only on canonical owned-U-Boot rows, while launcher is
        # open-only outside this table and diagnostic overrides stay held.
        # The tsp-35b9d6d1816b25822ebb.4 Cedrus publication moves PF_IMAGE_SHA on every
        # image-bearing row and PF_KERNEL_SHA on the a133-open-7x rows; the full GPU profile
        # also moves its in-tree KM and Steam Link UAPI source, while the no-radio override
        # remains frozen outside this table.
        # The tsp-mc9m.41.998 GPU demo-tool publication, unified-Zink attestation
        # correction, and runtime-loader attestation correction move only PF_IMAGE_SHA.
        # The combined image#190/#191 publication moves PF_IMAGE_SHA on every image-bearing
        # profile. The image#189/#192 provider publication moves it again; gpu-um-tsp#193
        # moves PF_GPU_UM_SHA only on open profiles outside this table. Image#193/#194 then
        # adds the profile-scoped CTS path and the 16550cc1 producer mirror, moving only
        # PF_IMAGE_SHA in this non-open table. Kernel and Steam Link UAPI remain unchanged.
        # Image#195 makes Xwayland a shared A133 open-GPU package input and again moves only
        # PF_IMAGE_SHA in every image-bearing row. Image#196 plus the kernel/UM batch moves
        # PF_IMAGE_SHA globally; canonical A133 rows also inherit the new kernel identity.
        # Image#197's byte-identical UAPI provenance mirror and image#198's exact gpu-um mirror
        # each move only PF_IMAGE_SHA in this non-open table; the gpu-um pin remains open-only.
        # Image#199 moves PF_IMAGE_SHA again for the byte-identical e9952056 UAPI provenance;
        # kernel#81 also moves PF_KERNEL_SHA only on the canonical open-7x rows. Image#200
        # advances PF_IMAGE_SHA globally; gpu-um 27219a2a remains open-profile-only.
        # Image#201/#202 move only PF_IMAGE_SHA again for the pipeline-cache producer and
        # corrected KMSRO device mapping; kernel and gpu-um remain pinned unchanged.
        # Image#204 corrects the KMSRO verification evidence and again moves only PF_IMAGE_SHA.
        # Stage-A first boot then moves PF_IMAGE_SHA, advances universal PF_WPA_SHA,
        # and adds universal PF_CLOUD_INIT_SHA. No profile selector or missing pin changes.
        # Image#205 advances PF_IMAGE_SHA globally and PF_GPU_UM_SHA on open profiles.
        # Image#206/#207/#208/#209 again move only the already-emitted PF_IMAGE_SHA.
        # Image#210 moves PF_IMAGE_SHA globally; its kernel#84 dependency additionally
        # moves PF_KERNEL_SHA for canonical open-7x profiles and the selected Steam Link
        # UAPI witness, while the no-radio kernel override remains frozen.
        # Build 5 includes image#211/#212 and kernel#85: PF_IMAGE_SHA moves globally;
        # canonical open-7x kernel/UAPI identities move while no-radio remains frozen.
        # Build 6 image#213 again moves PF_IMAGE_SHA globally; kernel#86 changes only
        # canonical open-7x kernel/UAPI identities and gpu-um#203/#205/#206 remain open-only.
        # The tsp-mc9m.41.1002.8.6 cloud-init completion pin moves only the universal
        # PF_CLOUD_INIT_SHA on every row; keys, lock state, and missing pins are unchanged.
        # Its c4377732 security correction again moves only PF_CLOUD_INIT_SHA.
        # Build 7 (tsp-mc9m.41.1017) moves PF_IMAGE_SHA and PF_CLOUD_INIT_SHA on every
        # row and PF_POOLSUITE_SHA on the dev rows that stage it; keys, lock state, and
        # missing pins are unchanged.
        # Build 8 (tsp-mc9m.41.996.13) advances PF_IMAGE_SHA and PF_CLOUD_INIT_SHA
        # globally. Runtime and launcher move only on profiles that stage those
        # open-GPU inputs.
        # The tsp-mc9m.41.1002.7.2 Build 8 finalizer repair advances only the
        # universal PF_CLOUD_INIT_SHA; image, runtime, and launcher stay pinned.
        # Image#235 then advances only the universal PF_IMAGE_SHA so platform
        # descriptor v3 reaches every image-build profile.
        # Image#236's GNU build-id producer merge likewise advances only PF_IMAGE_SHA.
        # Image#237's linear Gamescope cache rebind again advances only PF_IMAGE_SHA.
        # Image#238's hwprobe static-link repair again advances only PF_IMAGE_SHA.
        # Image#239's byte-identical GPU-UM toolchain mirror again advances only
        # PF_IMAGE_SHA here; GPU-UM #207/#208 remain open-profile-only.
        # Image#240's Wi-Fi lease-loss watchdog and image#241's Steam Link FFmpeg
        # GNU build IDs again advance only the universal PF_IMAGE_SHA.
        # Build 9 repair advances PF_IMAGE_SHA globally. The canonical open-GPU
        # profile also moves its byte-identical Steam Link UAPI witness to the
        # boot-kernel source identity; the no-radio override stays frozen.
        # Image#242's determinism repair again advances only universal PF_IMAGE_SHA.
        # Cursor packaging adds the universal PF_CURSOR_THEME_SHA and pinned
        # PF_CURSOR_TOOLS_* producer inputs; image#246 advances PF_IMAGE_SHA.
        # tsp-ihne1.1.1 corrects PF_CURSOR_TOOLS_RECIPE_SHA to the revision
        # proven by the pinned image's OCI metadata on every profile row.
        # The Build 10 Landlock set advances image/runtime/poolsuite globally;
        # launcher, gpu-um and Gamescope remain selected-profile-only inputs.
        # The Build 10 poolsuite pin cceaab08 advances PF_POOLSUITE_SHA on the dev
        # rows only; every release row stays byte-identical, verified by diffing the
        # old and new payloads key by key.
        # Build 11 advances PF_IMAGE_SHA on all ten rows and PF_KERNEL_SHA only on
        # the a133-open-7x dev/release rows. State, missing pins, and every other
        # build argument remain byte-identical in a base-vs-candidate payload diff.
        # The Gamescope rotation follow-up advances its paired image producer
        # witness globally; only PF_IMAGE_SHA moves on these non-GPU rows.
        # Build 12 advances PF_IMAGE_SHA and PF_RUNTIME_SHA on every row. Build 13
        # advances those fields again; launcher and gpu-um move only on open-GPU
        # profiles outside this non-open golden table.
        expected = {
            ("a133", "dev"): "bedd5db966a6e3770fa41c35177e29bd6f45582582ecbeff1b3109d2f38540c1",
            ("a133", "release"): "812bdf93c386799e1ec764324a47b7bfb4af56f6ed148d1d2cb673ef85ac788a",
            ("a133-open-7x", "dev"): "01d7a9db724275f8a27fdfed05676cb91bd67d230fb303146a2fef796df61a3a",
            ("a133-open-7x", "release"): "89fa799d3ad8435d0881b30be8ca722dc705c3f44b3c8437fc02000657be0774",
            ("a133-owned", "dev"): "d4336591c0e4812ba84931db44425d1b9ff3bfb9fb14cbd8e13856e46ad2fba9",
            ("a133-owned", "release"): "00722f5d96557a5f4061cc0ddcef81c2efd7b9c7d0749a279604a89d463e9c61",
            ("a523", "dev"): "b2098eecae816a38926cfb9ce98fa3286739e795472d415c49b22704fbe10ff9",
            ("a523", "release"): "7a20ef59f40009bbf3bd981e3e862bed059e83e787a83e90348f9d7856b6f315",
            ("sdm845", "dev"): "46e333d2e6fe99a74c2bcf2df219e4ec1104829a585e973f1aa5b01b0faac386",
            ("sdm845", "release"): "5b233394521f82d7c37199d72cda6c9a48cf73ec47ea44051e067db43bf54ef4",
        }
        for key, digest in expected.items():
            dev_id, variant = key
            args, state, missing = profile.build_args(dev_id, variant)
            payload = {"args": args, "state": state, "missing": missing}
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), digest, key)

    def test_app_runtime_declaration_is_validated_and_registry_derived(self):
        merged, _ = profile.resolve("a133")
        merged = copy.deepcopy(merged)
        merged["gpu"]["model"] = "open"
        source = pathlib.Path(profile.ABI_FAMILIES).read_text(encoding="utf-8")

        derived = source.replace(
            'id               = "pocketforge/a133-powervr"',
            'id               = "pocketforge/test-powervr"',
            1,
        ).replace('platform_version = "20"', 'platform_version = "21"', 1)
        with tempfile.TemporaryDirectory() as tmp:
            registry = pathlib.Path(tmp) / "families.toml"
            registry.write_text(derived, encoding="utf-8")
            with mock.patch.object(profile, "ABI_FAMILIES", str(registry)):
                support = profile._resolve_app_runtime_support(merged)
        self.assertEqual(support["runtime_family"], "pocketforge/test-powervr")
        self.assertEqual(support["platform_version"], "21")

        cases = {
            "unsorted": (
                '["audio", "entropy", "input", "open_url", "settings"]',
                '["settings", "audio"]',
                "must be sorted",
            ),
            "duplicate": (
                '["audio", "entropy", "input", "open_url", "settings"]',
                '["audio", "audio", "entropy"]',
                "must be unique",
            ),
            "runtime-unknown": (
                '["audio", "entropy", "input", "open_url", "settings"]',
                '["audio", "entropy", "input", "telepathy"]',
                "runtime-unknown values: telepathy",
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            registry = pathlib.Path(tmp) / "families.toml"
            for label, (old, new, message) in cases.items():
                with self.subTest(label=label):
                    registry.write_text(source.replace(old, new, 1), encoding="utf-8")
                    with mock.patch.object(profile, "ABI_FAMILIES", str(registry)):
                        with self.assertRaisesRegex(profile.ProfileSchemaError, message):
                            profile._resolve_app_runtime_support(merged)

    def test_open_url_capability_is_admitted_and_near_miss_word_refused(self):
        # tsp-mc9m.41.996.5.2: open_url joins the device-side vocabulary because
        # runtime#111 admits it in pf-app-manifest KNOWN_CAPABILITIES. The shipped
        # registry must back it for the a133 open-GPU launcher, and a near-miss
        # spelling must still be refused, so the same invocation carries both the
        # positive acceptance and the negative vocabulary control.
        merged, _ = profile.resolve("a133")
        merged = copy.deepcopy(merged)
        merged["gpu"]["model"] = "open"
        support = profile._resolve_app_runtime_support(merged)
        self.assertIn("open_url", support["supported_capabilities"])
        schema = json.loads(pathlib.Path(profile.PLATFORM_SUPPORT_SCHEMA).read_text())
        known = schema["properties"]["supported_capabilities"]["items"]["enum"]
        self.assertIn("open_url", known)

        source = pathlib.Path(profile.ABI_FAMILIES).read_text(encoding="utf-8")
        mutated = source.replace(
            '["audio", "entropy", "input", "open_url", "settings"]',
            '["audio", "entropy", "input", "open_url", "openurl", "settings"]',
            1,
        )
        self.assertNotEqual(mutated, source)
        with tempfile.TemporaryDirectory() as tmp:
            registry = pathlib.Path(tmp) / "families.toml"
            registry.write_text(mutated, encoding="utf-8")
            with mock.patch.object(profile, "ABI_FAMILIES", str(registry)):
                with self.assertRaisesRegex(
                        profile.ProfileSchemaError, "runtime-unknown values: openurl"):
                    profile._resolve_app_runtime_support(merged)

    def test_platform_support_schema_is_exact_and_runtime_known(self):
        schema = json.loads(pathlib.Path(profile.PLATFORM_SUPPORT_SCHEMA).read_text())
        self.assertFalse(schema["additionalProperties"])
        # tsp-fxlsw Task 2: the contract schema admits version 1 OR 2 (was const 1).
        self.assertEqual(schema["properties"]["schema_version"]["enum"], [1, 2])
        self.assertEqual(set(schema["required"]), set(APP_RUNTIME))
        known = schema["properties"]["supported_capabilities"]["items"]["enum"]
        self.assertEqual(known, sorted(set(known)))
        self.assertTrue(set(APP_RUNTIME["supported_capabilities"]).issubset(known))

    def test_platform_support_schema_2_facts_mirror_the_runtime_contract(self):
        # tsp-fxlsw Task 2: schema 2 adds six OPTIONAL facts, mirroring runtime@939ee0e6
        # crates/pf-app-manifest PlatformContract field for field (u32 domains, the
        # KNOWN_GLES_VERSIONS / KNOWN_VULKAN_VERSIONS / KNOWN_INPUTS vocabularies, and
        # DisplaySize {width, height}). The runtime parser owns the per-version discipline
        # (schema 1 must declare none of these; schema 2 requires the four non-graphics
        # facts), so the JSON schema keeps every one of them optional.
        schema = json.loads(pathlib.Path(profile.PLATFORM_SUPPORT_SCHEMA).read_text())
        props = schema["properties"]
        optional_v2 = ("physical_memory_mib", "app_memory_budget_mib",
                       "gles_max", "vulkan_max", "inputs", "display")
        for key in optional_v2:
            self.assertIn(key, props)
            self.assertNotIn(key, schema["required"])
        u32 = {"type": "integer", "minimum": 0, "maximum": 4294967295}
        self.assertEqual(props["physical_memory_mib"], u32)
        self.assertEqual(props["app_memory_budget_mib"], u32)
        self.assertEqual(props["gles_max"], {"type": "string", "enum": ["2.0", "3.0", "3.1", "3.2"]})
        self.assertEqual(props["vulkan_max"],
                         {"type": "string", "enum": ["1.0", "1.1", "1.2", "1.3", "1.4"]})
        self.assertEqual(props["inputs"], {
            "type": "array",
            "uniqueItems": True,
            "items": {
                "type": "string",
                "enum": ["buttons", "dpad", "stick", "two_sticks", "touch", "keyboard", "pointer"],
            },
        })
        self.assertEqual(props["display"], {
            "type": "object",
            "additionalProperties": False,
            "required": ["width", "height"],
            "properties": {"width": u32, "height": u32},
        })
        # The per-version discipline is expressed as conditional branches that mirror
        # parse_platform_contract: schema 1 forbids every v2 fact; schema 2 requires the
        # four non-graphics facts (gles_max/vulkan_max stay optional at both versions).
        v1_branch, v2_branch = schema["allOf"]
        self.assertEqual(v1_branch["if"], {"required": ["schema_version"],
                                           "properties": {"schema_version": {"const": 1}}})
        self.assertEqual(v1_branch["then"]["properties"], {k: False for k in optional_v2})
        self.assertEqual(v2_branch["if"], {"required": ["schema_version"],
                                           "properties": {"schema_version": {"const": 2}}})
        self.assertEqual(v2_branch["then"]["required"],
                         ["physical_memory_mib", "app_memory_budget_mib", "inputs", "display"])

    def test_platform_support_schema_branches_accept_exactly_the_runtime_contract(self):
        # tsp-fxlsw Task 2 (review round 1): the published schema must accept exactly the
        # documents runtime@939ee0e6 parse_platform_contract accepts. Positive and negative
        # controls are judged by the repo's own JSON-Schema engine in this single run.
        schema = json.loads(pathlib.Path(profile.PLATFORM_SUPPORT_SCHEMA).read_text())

        def errs(doc):
            return caps.schema_errors(doc, schema)

        v1 = dict(APP_RUNTIME)
        v2 = dict(APP_RUNTIME, schema_version=2, physical_memory_mib=970,
                  app_memory_budget_mib=600, gles_max="3.0",
                  inputs=["buttons", "dpad", "stick", "two_sticks"],
                  display={"width": 1280, "height": 720})
        # Positive controls: a v1 doc, a v2 doc, and v2 with both optional graphics facts.
        self.assertEqual(errs(v1), [])
        self.assertEqual(errs(v2), [])
        self.assertEqual(errs(dict(v2, vulkan_max="1.3")), [])
        # Negative controls: every v2-only fact is forbidden at schema 1, by name.
        forbidden_values = {"physical_memory_mib": 970, "app_memory_budget_mib": 600,
                            "gles_max": "3.0", "vulkan_max": "1.3", "inputs": ["buttons"],
                            "display": {"width": 640, "height": 480}}
        for field, value in forbidden_values.items():
            with self.subTest(forbidden_at_v1=field):
                got = errs(dict(v1, **{field: value}))
                self.assertTrue(got and any(field in e for e in got), got)
        # Negative controls: every fact required at schema 2 is enforced, by name.
        for field in ("physical_memory_mib", "app_memory_budget_mib", "inputs", "display"):
            with self.subTest(required_at_v2=field):
                doc = {k: val for k, val in v2.items() if k != field}
                got = errs(doc)
                self.assertTrue(got and any(field in e for e in got), got)
        # Negative controls: version and vocabulary discipline.
        self.assertTrue(any("schema_version" in e for e in errs(dict(v1, schema_version=3))))
        # JSON-Schema equality is type-aware: `true` is not 1 (Python's == disagrees), so a
        # boolean schema_version must not satisfy enum [1, 2] nor select the v1 const branch.
        self.assertTrue(any("schema_version" in e for e in errs(dict(v1, schema_version=True))))
        self.assertTrue(any("gles_max" in e for e in errs(dict(v2, gles_max="9.9"))))
        self.assertTrue(any("vulkan_max" in e for e in errs(dict(v2, vulkan_max="0.9"))))
        self.assertTrue(any("inputs" in e for e in errs(dict(v2, inputs=["buttons", "turbo"]))))
        self.assertTrue(any("inputs" in e for e in errs(dict(v2, inputs=["buttons", "buttons"]))))
        self.assertTrue(any("display" in e for e in errs(dict(v2, display={"width": 1280}))))
        self.assertTrue(any("bogus" in e for e in errs(dict(v1, bogus=1))))

    def test_dev_only_source_shas_are_empty_only_for_release(self):
        dev, _, dev_missing = profile.build_args("a133", "dev")
        release, _, release_missing = profile.build_args("a133", "release")
        self.assertEqual(dev_missing, [])
        self.assertEqual(release_missing, [])
        self.assertRegex(dev["PF_HWPROBE_SHA"], r"^[0-9a-f]{40}$")
        self.assertRegex(dev["PF_SIM_SHA"], r"^[0-9a-f]{40}$")
        self.assertEqual(dev["PF_POOLSUITE_SHA"], "cceaab085a270268efccc07930a732b41039dabf")
        self.assertEqual(release["PF_HWPROBE_SHA"], "")
        self.assertEqual(release["PF_SIM_SHA"], "")
        self.assertEqual(release["PF_POOLSUITE_SHA"], "")

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
        self.assertEqual(opened["PF_GPU_UM_SHA"], "1ae75772e7f42251062cf660fc13577b8fd60664")
        self.assertEqual(
            opened["PF_KERNEL_REQUIRED_MODULES"],
            "powervr videobuf2-dma-contig sun6i-csi xradio",
        )
        self.assertIn("pvr-fw-open-22.102.54.38", opened["PF_BLOB_GROUPS"])
        self.assertNotIn("pvr-ddk-22.102.54.38", opened["PF_BLOB_GROUPS"])
        # pf-shell launcher (tsp-mc9m.41.924.4 / top-coord RULING B): OPEN-ONLY. The launcher
        # SHA is emitted (and required) ONLY for the open path; it resolves EMPTY for the ddk
        # path so the Dockerfile launcher-ddk NOT-SHIPPED stub keeps the ddk images byte-identical.
        self.assertEqual(opened["PF_LAUNCHER_SHA"], "6de0ad32af207ea208ccb29a42b3f3ae4e8d2777")
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
        for dev_id in ("a133", "a133-open", "a133-open-7x",
                       "a133-open-7x-gpu", "a133-open-7x-gpu-noradio",
                       "a133-owned"):
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
        self.assertEqual(args["PF_KERNEL_SHA"], "07bb60764cbc64b5a5d760c34709f07f8259e985")
        self.assertEqual(args["PF_KERNEL_DTB"], "sun50i-a133-pocketforge-tsp.dtb")
        self.assertEqual(args["PF_GPU_MODEL"], "none")
        self.assertEqual(args["PF_GPU_REPO"], "")
        self.assertEqual(args["PF_GPU_KM_REPO"], "")
        self.assertEqual(args["PF_GPU_UM_REPO"], "")
        self.assertEqual(args["PF_GPU_MODULES"], "")
        self.assertEqual(args["PF_LAUNCHER_SHA"], "")
        self.assertEqual(args["PF_RECOVERY_SHA"], "")
        self.assertNotIn("pvr-fw-open-22.102.54.38", args["PF_BLOB_GROUPS"])

    def test_a133_7x_gpu_selects_full_open_contract(self):
        args, _, missing = profile.build_args("a133-open-7x-gpu")
        self.assertEqual(missing, [])
        self.assertEqual(args["PF_DEVICE_ID"], "a133-open-7x-gpu")
        self.assertEqual(args["PF_KERNEL_REPO"], "kernel-sunxi-7.x")
        self.assertEqual(args["PF_KERNEL_REF"], "device/a133")
        self.assertEqual(args["PF_KERNEL_SHA"], "07bb60764cbc64b5a5d760c34709f07f8259e985")
        self.assertEqual(args["PF_KERNEL_DTB"], "sun50i-a133-pocketforge-odyssey.dtb")
        self.assertEqual(args["PF_GPU_MODEL"], "open")
        self.assertEqual(args["PF_GPU_KM_MODEL"], "in-tree-7.x")
        self.assertEqual(args["PF_GPU_KM_REPO"], "kernel-sunxi-7.x")
        self.assertEqual(args["PF_GPU_KM_REF"], "device/a133")
        self.assertEqual(args["PF_GPU_KM_SHA"], args["PF_KERNEL_SHA"])
        self.assertEqual(args["PF_GPU_UM_REPO"], "gpu-um-tsp")
        self.assertEqual(
            {
                "PF_GPU_UM_SHA": args["PF_GPU_UM_SHA"],
                "PF_IMAGE_SHA": args["PF_IMAGE_SHA"],
            },
            {
                "PF_GPU_UM_SHA": "1ae75772e7f42251062cf660fc13577b8fd60664",
                "PF_IMAGE_SHA": "85e1a5f1877b1e3c2bd3f0f4beea1e0be19476e3",
            },
        )
        self.assertEqual(args["PF_LIBSDL3_SHA"], "7411a94803c95b2f93a898f3773ffe95dfec4263")
        self.assertEqual(args["PF_GPU_MODULES"], "powervr.ko")
        self.assertEqual(args["PF_KERNEL_REQUIRED_MODULES"], "powervr")
        self.assertEqual(args["PF_DISPLAY_PIPELINE"], "fbdev")
        self.assertEqual(args["PF_LAUNCHER_SHA"], "6de0ad32af207ea208ccb29a42b3f3ae4e8d2777")
        self.assertEqual(args["PF_RECOVERY_SHA"], "443a84e47c96d83de967948844d8e5eaa41d7413")
        self.assertEqual(args["PF_BLOBS_SHA"], "02ad8b7158ae39797f2693607ea9f2e6975f9ffd")
        self.assertEqual(
            args["PF_VENDOR_MANIFEST_SHA"],
            "3c8c5c537028e6f749f7888b05e85aa95aa88db4",
        )
        self.assertIn("pvr-fw-open-22.102.54.38", args["PF_BLOB_GROUPS"])

    def test_open_profile_module_contract_fails_closed(self):
        original = profile.resolve
        resolved, family = original("a133-open-7x-gpu")
        cases = {
            "missing": None,
            "empty": [],
            "missing-powervr": ["sun6i-csi"],
            "invalid": ["powervr.ko"],
            "duplicate": ["powervr", "powervr"],
        }
        for label, required_modules in cases.items():
            with self.subTest(label=label):
                broken = copy.deepcopy(resolved)
                if required_modules is None:
                    del broken["kernel"]["required_modules"]
                else:
                    broken["kernel"]["required_modules"] = required_modules
                profile.resolve = lambda _dev, candidate=broken: (candidate, family)
                try:
                    errors, _ = profile.validate("a133-open-7x-gpu", profile.load_lock())
                finally:
                    profile.resolve = original
                self.assertTrue(
                    any("required_modules" in error for error in errors),
                    (label, errors),
                )

    def test_open_profile_missing_locked_kernel_sha_is_reported(self):
        lock = copy.deepcopy(profile.load_lock())
        lock["repos"]["kernel-sunxi-7.x"]["sha"] = ""
        with mock.patch.object(profile, "load_lock", return_value=lock):
            args, _, missing = profile.build_args("a133-open-7x-gpu")
        self.assertEqual(args["PF_KERNEL_SHA"], "")
        self.assertEqual(args["PF_GPU_KM_SHA"], "")
        self.assertIn("PF_KERNEL_SHA", missing)
        self.assertIn("PF_GPU_KM_SHA", missing)

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
