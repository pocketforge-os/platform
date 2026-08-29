#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("shell_input_validate", ROOT / "validate.py")
validator = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(validator)


class ShellInputContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shipped = json.loads((ROOT / "fixtures/trimui-smart-pro.json").read_text())
        cls.shapes = json.loads((ROOT / "fixtures/binding-shapes.json").read_text())

    def test_shipped_trimui_truth_and_defaults(self) -> None:
        validator.validate_contract(self.shipped)
        controls = {item["position"]: item for item in self.shipped["physical_controls"]}
        self.assertEqual("A", controls["east"]["printed_label"])
        self.assertEqual("B", controls["south"]["printed_label"])
        mapping = {item["action"]: item["binding"] for item in self.shipped["effective_map"]}
        self.assertEqual(["east"], mapping["Activate"]["controls"])
        self.assertEqual(["south"], mapping["Back"]["controls"])
        self.assertEqual({"shape": "single_press", "controls": ["guide"]}, mapping["SafeReturn"])

    def test_unlabeled_controls_have_source_owned_fallbacks(self) -> None:
        controls = {item["position"]: item for item in self.shipped["physical_controls"]}
        self.assertNotIn("printed_label", controls["guide"])
        self.assertEqual({"source": "pocketforge", "id": "pf-guide"}, controls["guide"]["fallback_glyph"])
        for item in controls.values():
            if "printed_label" not in item:
                self.assertEqual("pocketforge", item["fallback_glyph"]["source"])
                self.assertTrue(item["fallback_glyph"]["id"].startswith("pf-"))

    def test_invalid_fixtures_are_rejected_with_typed_reasons(self) -> None:
        for path in sorted((ROOT / "fixtures/invalid").glob("*.json")):
            with self.subTest(fixture=path.name):
                instruction = json.loads(path.read_text())
                changed = copy.deepcopy(self.shipped)
                if "remove_action" in instruction:
                    changed["effective_map"] = [
                        item for item in changed["effective_map"]
                        if item["action"] != instruction["remove_action"]
                    ]
                elif "remove_physical_controls" in instruction:
                    removed = set(instruction["remove_physical_controls"])
                    changed["physical_controls"] = [
                        item for item in changed["physical_controls"]
                        if item["position"] not in removed
                    ]
                elif "invalid_fallback_glyph_id" in instruction:
                    changed["physical_controls"][0]["fallback_glyph"]["id"] = instruction["invalid_fallback_glyph_id"]
                else:
                    safe = next(item for item in changed["effective_map"] if item["action"] == "SafeReturn")
                    face = next(item for item in changed["effective_map"] if item["action"] == instruction["safe_return_copy_action"])
                    if not instruction.get("preserve_safe_return_context", False):
                        safe["context"] = face["context"]
                    safe["binding"] = copy.deepcopy(face["binding"])
                with self.assertRaises(validator.ContractError) as raised:
                    validator.validate_contract(changed, path.name)
                self.assertEqual(instruction["expected_reason"], raised.exception.reason)
                if "expected_detail" in instruction:
                    self.assertIn(instruction["expected_detail"], raised.exception.detail)

    def test_all_ruled_binding_shapes_round_trip(self) -> None:
        validator.validate_binding_set(self.shapes)
        encoded = json.dumps(self.shapes, sort_keys=True, separators=(",", ":"))
        decoded = json.loads(encoded)
        validator.validate_binding_set(decoded)
        self.assertEqual(self.shapes, decoded)
        self.assertEqual({"chord", "hold", "double_press"}, {item["binding"]["shape"] for item in decoded["safe_return_alternatives"]})
        default = next(item for item in self.shipped["effective_map"] if item["action"] == "SafeReturn")
        self.assertEqual("single_press", default["binding"]["shape"])

    def test_reference_json_schema(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("optional jsonschema package unavailable")
        schema = json.loads((ROOT.parent / "schemas/shell-input-contract-v1.schema.json").read_text())
        checker = jsonschema.Draft202012Validator(schema)
        checker.validate(self.shipped)
        checker.validate(self.shapes)


if __name__ == "__main__":
    unittest.main()
