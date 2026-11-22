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
        a, b = profile.resolve(BASE)[0], profile.resolve(OFF)[0]
        for sect in ("kernel", "gpu", "display", "bootchain", "image"):
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
                x.pop("image_name", None); y.pop("image_name", None)
            if sect == "device":
                x.pop("id", None); y.pop("id", None)
                x.pop("name", None); y.pop("name", None)
            self.assertEqual(x, y, sect)

    def test_ci_matrix_registered(self):
        self.assertRegex((ROOT / "ci-matrix.toml").read_text(),
                         r'(?m)^a133-open-7x-gpu-resetcap-off\s*=\s*"excluded"')

    def test_source_pins_equality(self):
        """Control and candidate share locked TF-A/U-Boot/kernel SHAs."""
        a_args = _build_args(BASE)
        b_args = _build_args(OFF)
        for key in ("PF_TFA_SHA", "PF_UBOOT_SHA"):
            self.assertEqual(a_args.get(key), b_args.get(key), key)


if __name__ == "__main__":
    unittest.main()
