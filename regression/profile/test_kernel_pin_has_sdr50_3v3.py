"""tsp-mc9m.60.29.33.17 RED/GREEN gate: both a133-open-7x-gpu kernel pins must carry
kernel#183 (d84c5066: SDR50 opt-in DT restores PF 3.3 V mode on the default mmc0 state).

tsp-hqm1p.182.339: the pin is read from platform.lock, never copied here. "Carries" is
proved offline from the lock's own lineage record: each advance appends
`# <bead>: <new8> = <old8> + ...` above the kernel-sunxi-7.x `sha`, and the chain from
the current pin back must reach the kernel#183 floor."""
import pathlib
import re
import unittest

LOCK = pathlib.Path(__file__).resolve().parents[2] / "platform.lock"
FLOOR = "d84c5066"  # kernel#183 merge; a history prefix, not the current pin
LINEAGE = re.compile(r"^#[^\n]*?:\s*([0-9a-f]{8})\s*=\s*([0-9a-f]{8})\s*\+", re.M)


def kernel_pins(text: str) -> tuple[set[str], str, str]:
    shas = set(re.findall(r'^kernel\s*=\s*"([0-9a-f]{40})"', text, re.M))
    m = re.search(
        r'^name = "kernel-sunxi-7\.x"[^\n]*\n((?:.*\n)*?)sha\s*=\s*"([0-9a-f]{40})"', text, re.M
    )
    if m is None:
        raise AssertionError("kernel-sunxi-7.x [[repos]] entry not found")
    return shas, m.group(2), m.group(1)


def carries(current: str, block: str, floor: str) -> bool:
    parent = {new: old for new, old in LINEAGE.findall(block)}
    node, seen = current[:8], set()
    while node not in seen:
        if node == floor:
            return True
        seen.add(node)
        if node not in parent:
            return False
        node = parent[node]
    return False


class KernelPinHasSdr50Fix(unittest.TestCase):
    def test_kernel_pins_are_equal_and_carry_183(self):
        profile_pins, repo_pin, block = kernel_pins(LOCK.read_text())
        self.assertEqual(profile_pins | {repo_pin}, {repo_pin}, "kernel pins diverge")
        self.assertTrue(carries(repo_pin, block, FLOOR), "kernel pin does not carry kernel#183")

    def test_lineage_walk(self):
        block = "# a: 33333333 = 22222222 + k#3\n# b: 22222222 = 11111111 + k#2\n"
        self.assertTrue(carries("3" * 40, block, "11111111"))
        self.assertTrue(carries("1" * 40, block, "11111111"))
        self.assertFalse(carries("3" * 40, block, "44444444"))
        self.assertFalse(carries("5" * 40, block, "11111111"))


if __name__ == "__main__":
    unittest.main()
