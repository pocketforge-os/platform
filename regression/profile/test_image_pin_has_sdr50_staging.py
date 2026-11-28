"""RED/GREEN gate: the image pin must carry image#406 (807bb488: stages the
Odyssey SDR50 opt-in DTB as dtb-sdr50.bin on FAT p4).

tsp-hqm1p.182.948.3: the pin is read from platform.lock, never copied here. "Carries"
is proved offline from the lock's own lineage records: the seed line above the image
`sha` names 807bb488 as its parent, and pf-pin appends
`# <bead>: <new8> = <old8> + ...` above the `sha` on every later advance. The chain
from the current pin back must reach the image#406 floor."""
import pathlib
import re
import unittest

LOCK = pathlib.Path(__file__).resolve().parents[2] / "platform.lock"
FLOOR = "807bb488"  # image#406 merge; a history prefix, not the current pin
LINEAGE = re.compile(r"^#[^\n]*?:\s*([0-9a-f]{8})\s*=\s*([0-9a-f]{8})\s*\+", re.M)


def image_pin(text: str) -> tuple[str, str]:
    m = re.search(r'^name = "image"[^\n]*\n((?:.*\n)*?)sha\s*=\s*"([0-9a-f]{40})"', text, re.M)
    if m is None:
        raise AssertionError("image [[repos]] entry not found")
    return m.group(2), m.group(1)


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


class ImagePinHasSdr50Staging(unittest.TestCase):
    def test_image_pin_carries_image_406(self):
        pin, block = image_pin(LOCK.read_text())
        self.assertTrue(carries(pin, block, FLOOR), "image pin does not carry image#406")

    def test_lineage_walk(self):
        block = "# a: 33333333 = 22222222 + k#3\n# b: 22222222 = 11111111 + k#2\n"
        self.assertTrue(carries("3" * 40, block, "11111111"))
        self.assertTrue(carries("1" * 40, block, "11111111"))
        self.assertFalse(carries("3" * 40, block, "44444444"))
        self.assertFalse(carries("5" * 40, block, "11111111"))

    def test_floor_absent_does_not_carry(self):
        block = "# a: 33333333 = 22222222 + k#3\n"
        self.assertFalse(carries("3" * 40, block, FLOOR))
        self.assertFalse(carries("8" * 40, "", FLOOR))


if __name__ == "__main__":
    unittest.main()