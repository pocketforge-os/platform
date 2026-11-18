"""tsp-mc9m.60.29.33.16 RED/GREEN gate: the image pin must include image#406
(807bb488: stages the Odyssey SDR50 opt-in DTB as dtb-sdr50.bin on FAT p4).
The old pin 9ba6c7a0 predates it, so a pf build would silently omit it."""
import pathlib
import re
import unittest

LOCK = pathlib.Path(__file__).resolve().parents[2] / "platform.lock"
WANT = "81aa178b2f420966e722c7ba1913ac25d6a4bb85"


class ImagePinHasSdr50Staging(unittest.TestCase):
    def test_image_pin_is_image_406_merge(self):
        text = LOCK.read_text()
        m = re.search(r'^name = "image"\n(?:.*\n)*?sha\s*=\s*"([0-9a-f]{40})"', text, re.M)
        self.assertIsNotNone(m, "image [[repos]] entry not found")
        self.assertEqual(m.group(1), WANT, "image pin does not carry image#406")


if __name__ == "__main__":
    unittest.main()
