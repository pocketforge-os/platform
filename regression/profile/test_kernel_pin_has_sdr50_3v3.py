"""tsp-mc9m.60.29.33.17 RED/GREEN gate: both a133-open-7x-gpu kernel pins must carry
kernel#183 (d84c5066: SDR50 opt-in DT restores PF 3.3 V mode on the default mmc0 state)."""
import pathlib
import re
import unittest

LOCK = pathlib.Path(__file__).resolve().parents[2] / "platform.lock"
WANT = "d84c506667f1b67645a95af871d194ac694477fb"


class KernelPinHasSdr50Fix(unittest.TestCase):
    def test_kernel_pins_are_183_merge(self):
        text = LOCK.read_text()
        shas = set(re.findall(r'^kernel\s*=\s*"([0-9a-f]{40})"', text, re.M))
        m = re.search(r'^name = "kernel-sunxi-7\.x"[^\n]*\n(?:.*\n)*?sha\s*=\s*"([0-9a-f]{40})"', text, re.M)
        self.assertIsNotNone(m, "kernel-sunxi-7.x [[repos]] entry not found")
        shas.add(m.group(1))
        self.assertEqual(shas, {WANT}, "kernel pins do not all carry kernel#183")


if __name__ == "__main__":
    unittest.main()
