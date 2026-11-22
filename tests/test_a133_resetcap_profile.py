#!/usr/bin/env python3
"""tsp-mc9m.60.29.63.20.4: a133-open-7x-gpu-resetcap-off profile carries tfa.reset_capability."""
import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import profile  # noqa: E402

BASE, OFF = "a133-open-7x-gpu", "a133-open-7x-gpu-resetcap-off"


def _env(dev):
    out = {}
    for ln in profile.env_lines(dev):
        k, _, v = ln.partition("=")
        out[k.replace("export ", "").strip()] = v.strip().strip("'\"")
    return out


def _build_args(dev):
    args, _, _ = profile.build_args(dev)
    return args


class ResetCapProfile(unittest.TestCase):
    def test_off_profile_resolves_and_sets_capability(self):
        merged, _ = profile.resolve(OFF)
        self.assertEqual(merged["bootchain"].get("tfa", {}).get("reset_capability"), "watchdog")

    def test_base_profile_default_capability(self):
        merged, _ = profile.resolve(BASE)
        cap = merged["bootchain"].get("tfa", {}).get("reset_capability", "axp717")
        self.assertEqual(cap, "axp717")

    def test_env_flag(self):
        self.assertEqual(_env(OFF).get("PF_TFA_RESET_CAPABILITY"), "watchdog")
        self.assertEqual(_env(BASE).get("PF_TFA_RESET_CAPABILITY", "axp717"), "axp717")

    def test_build_args_flag(self):
        self.assertEqual(_build_args(OFF).get("PF_TFA_RESET_CAPABILITY"), "watchdog")
        self.assertEqual(_build_args(BASE).get("PF_TFA_RESET_CAPABILITY", "axp717"), "axp717")

    def test_only_capability_differs_from_base(self):
        """Control/candidate are semantically identical apart from reset_capability + identity."""
        a, b = profile.resolve(BASE)[0], profile.resolve(OFF)[0]
        # Compare all sections with documented deltas
        for sect in ("kernel", "gpu", "display", "bootchain", "image", "device"):
            x, y = dict(a.get(sect, {})), dict(b.get(sect, {}))
            if sect == "bootchain":
                # Pop tfa sub-dict and remove reset_capability from it
                tfa_x = dict(x.pop("tfa", {}))
                tfa_y = dict(y.pop("tfa", {}))
                tfa_x.pop("reset_capability", None)
                tfa_y.pop("reset_capability", None)
                x["tfa"] = tfa_x
                y["tfa"] = tfa_y
            if sect == "image":
                # Only image_name differs (identity)
                x.pop("image_name", None); y.pop("image_name", None)
            if sect == "device":
                # Only id and name differ (identity)
                x.pop("id", None); y.pop("id", None)
                x.pop("name", None); y.pop("name", None)
            self.assertEqual(x, y, f"section {sect} differs beyond documented identity deltas")

    def test_ci_matrix_registered(self):
        self.assertRegex((ROOT / "ci-matrix.toml").read_text(),
                         r'(?m)^a133-open-7x-gpu-resetcap-off\s*=\s*"excluded"')

    def test_source_pins_equality(self):
        """Control and candidate share locked TF-A/U-Boot/kernel SHAs."""
        a_args = _build_args(BASE)
        b_args = _build_args(OFF)
        for key in ("PF_TFA_SHA", "PF_UBOOT_SHA", "PF_KERNEL_SHA"):
            self.assertEqual(a_args.get(key), b_args.get(key), f"{key} must be identical")

    def test_tfa_locked_to_merged_main_linear_sha(self):
        """Platform.lock pins tfa-tsp-a133 to exact main-linear merge 18473be6."""
        EXPECTED_TFA_SHA = "18473be659d2549046723ffc5ec940c918fdd823"
        a_args = _build_args(BASE)
        b_args = _build_args(OFF)
        self.assertEqual(a_args.get("PF_TFA_SHA"), EXPECTED_TFA_SHA,
                         f"base profile PF_TFA_SHA must be merged main-linear {EXPECTED_TFA_SHA}")
        self.assertEqual(b_args.get("PF_TFA_SHA"), EXPECTED_TFA_SHA,
                         f"off profile PF_TFA_SHA must be merged main-linear {EXPECTED_TFA_SHA}")

    def test_identity_deltas_only(self):
        """Prove device.id, device.name are the only identity deltas."""
        a, b = profile.resolve(BASE)[0], profile.resolve(OFF)[0]
        # device section
        self.assertEqual(a["device"]["id"], "a133-open-7x-gpu")
        self.assertEqual(b["device"]["id"], "a133-open-7x-gpu-resetcap-off")
        self.assertNotEqual(a["device"]["name"], b["device"]["name"])

    def test_build_args_differ_only_in_reset_capability(self):
        """Prove build args differ only in PF_TFA_RESET_CAPABILITY and identity fields."""
        a_args = _build_args(BASE)
        b_args = _build_args(OFF)
        # Remove the one legitimate difference
        a_cmp = dict(a_args)
        b_cmp = dict(b_args)
        a_cap = a_cmp.pop("PF_TFA_RESET_CAPABILITY", None)
        b_cap = b_cmp.pop("PF_TFA_RESET_CAPABILITY", None)
        self.assertEqual(a_cap, "axp717")
        self.assertEqual(b_cap, "watchdog")
        # Remove identity fields
        for key in ("PF_DEVICE_ID", "PF_DEVICE_NAME", "PF_IMAGE_NAME"):
            a_cmp.pop(key, None)
            b_cmp.pop(key, None)
        self.assertEqual(a_cmp, b_cmp, "build args differ beyond reset_capability + identity")


if __name__ == "__main__":
    unittest.main()
