#!/usr/bin/env python3
"""Regression coverage for the a133 rumble actuator row."""

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
A133 = ROOT / "devices" / "a133" / "capabilities.toml"


class A133RumbleActuatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = A133.read_text(encoding="utf-8")
        cls.descriptor = tomllib.loads(cls.text)
        cls.actuators = {row["id"]: row for row in cls.descriptor["actuators"]}

    def test_rumble_row_present(self) -> None:
        self.assertEqual(
            self.actuators.get("rumble"),
            {
                "id": "rumble",
                "kind": "rumble",
                "ev_type": "EV_FF",
                "code": "FF_RUMBLE",
                "source": "gpio-vibrator",
            },
        )

    def test_leds_row_unchanged(self) -> None:
        self.assertEqual(self.actuators["leds"]["kind"], "led_array")

    def test_stale_no_rumble_statement_removed(self) -> None:
        self.assertNotIn("NO rumble on the base unit", self.text)


if __name__ == "__main__":
    unittest.main()
