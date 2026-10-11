#!/usr/bin/env python3
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import Invalid, validate


class MenuPageValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).with_name("fixtures") / "system-menu.json"
        cls.valid = json.loads(fixture.read_text(encoding="utf-8"))

    def test_positive_control(self):
        validate(copy.deepcopy(self.valid))

    def test_unknown_item_field_is_rejected(self):
        invalid = copy.deepcopy(self.valid)
        invalid["pages"][0]["sections"][0]["items"][0]["bind"] = {"host": "wrong"}
        with self.assertRaises(Invalid):
            validate(invalid)

    def test_link_to_missing_page_is_rejected(self):
        invalid = copy.deepcopy(self.valid)
        invalid["pages"][0]["sections"][0]["items"][3]["page"] = "missing"
        with self.assertRaises(Invalid):
            validate(invalid)


if __name__ == "__main__":
    unittest.main()
