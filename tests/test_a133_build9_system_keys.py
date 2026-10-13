#!/usr/bin/env python3
"""Regression coverage for a133 Build 9 system-key evidence."""

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
A133 = ROOT / "devices" / "a133" / "capabilities.toml"


class A133Build9SystemKeysTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = A133.read_text(encoding="utf-8")
        cls.descriptor = tomllib.loads(cls.text)
        cls.inputs = {row["id"]: row for row in cls.descriptor["inputs"]}

    def test_power_row_matches_build9_receipt(self) -> None:
        self.assertEqual(
            self.inputs["power"],
            {
                "id": "power",
                "kind": "button",
                "ev_type": "EV_KEY",
                "code": "KEY_POWER",
                "class": "system",
                "source": "axp20x-pek",
                "skin_part": "btn_power",
            },
        )

    def test_volume_rows_keep_stock_os_source(self) -> None:
        self.assertEqual(self.inputs["vol_up"]["source"], "sunxi-keyboard")
        self.assertEqual(self.inputs["vol_down"]["source"], "sunxi-keyboard")

    def test_build9_provenance_is_recorded(self) -> None:
        required_evidence = (
            "9179d1446ad98af5c5387ab25435f0fe",
            "406aba39e725f3c65a396ac2f8a0a1b0e96f9cacd9b245bc5d5bb543994b1255",
            "35945342b75c7002b5b5c39f4b5b38d0696691a8563034ce53feb06579d122a5",
            "platform-7081400.i2c-platform-axp20x-pek-event",
            "0000/0000/0000",
            "AXP717",
            "pmic@34",
            "lradc@5070800",
            "status=disabled",
            "gpio-keys-hall",
            "SW_LID",
            "0019/0001/0001",
            "sunxi-ir",
            "H616 Audio Codec Headphone Jack",
        )
        for evidence in required_evidence:
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, self.text)


if __name__ == "__main__":
    unittest.main()
