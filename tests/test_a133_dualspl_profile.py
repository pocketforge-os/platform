#!/usr/bin/env python3
"""tsp-mc9m.60.29.63.20.2: a133-open-7x-gpu-dualspl profile carries bootchain.spl_dual_8k."""
import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import profile  # noqa: E402

BASE, DUAL = "a133-open-7x-gpu", "a133-open-7x-gpu-dualspl"


def _env(dev):
    out = {}
    for ln in profile.env_lines(dev):
        k, _, v = ln.partition("=")
        out[k.replace("export ", "").strip()] = v.strip().strip("'\"")
    return out


class DualSplProfile(unittest.TestCase):
    def test_dual_profile_resolves_and_sets_flag(self):
        self.assertEqual(profile.resolve(DUAL)[0]["bootchain"].get("spl_dual_8k"), True)

    def test_base_profile_unflagged(self):
        self.assertFalse(profile.resolve(BASE)[0]["bootchain"].get("spl_dual_8k", False))

    def test_env_flag(self):
        self.assertEqual(_env(DUAL).get("PF_SPL_DUAL_8K"), "1")
        self.assertIn(_env(BASE).get("PF_SPL_DUAL_8K", ""), ("", "0"))

    def test_only_flag_differs_from_base(self):
        a, b = profile.resolve(BASE)[0], profile.resolve(DUAL)[0]
        for sect in ("kernel", "gpu", "display", "bootchain", "image"):
            x, y = dict(a.get(sect, {})), dict(b.get(sect, {}))
            y.pop("spl_dual_8k", None); x.pop("spl_dual_8k", None)
            if sect == "image":
                x.pop("image_name", None); y.pop("image_name", None)
            self.assertEqual(x, y, sect)

    def test_ci_matrix_registered(self):
        self.assertRegex((ROOT / "ci-matrix.toml").read_text(), r'(?m)^a133-open-7x-gpu-dualspl\s*=\s*"excluded"')


if __name__ == "__main__":
    unittest.main()
