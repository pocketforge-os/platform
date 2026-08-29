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
        cls.defaults = json.loads((ROOT / "fixtures/safe-return-defaults.json").read_text())

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
                if instruction.get("target") == "defaults-registry":
                    changed = copy.deepcopy(self.defaults)
                    entry = changed["safe_return_defaults"][instruction["device_id"]]
                    entry["shipped_default"] = instruction["replace_shipped_default"]
                    validate = validator.validate_defaults_registry
                else:
                    changed = copy.deepcopy(self.shipped)
                    validate = validator.validate_contract
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
                elif instruction.get("target") != "defaults-registry":
                    safe = next(item for item in changed["effective_map"] if item["action"] == "SafeReturn")
                    face = next(item for item in changed["effective_map"] if item["action"] == instruction["safe_return_copy_action"])
                    if not instruction.get("preserve_safe_return_context", False):
                        safe["context"] = face["context"]
                    safe["binding"] = copy.deepcopy(face["binding"])
                with self.assertRaises(validator.ContractError) as raised:
                    validate(changed, path.name)
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

    def test_per_device_shipped_defaults(self) -> None:
        validator.validate_defaults_registry(self.defaults)
        defaults = self.defaults["safe_return_defaults"]
        self.assertEqual({"shape": "single_press", "controls": ["home"]}, defaults["a523"]["shipped_default"])
        self.assertEqual({"shape": "single_press", "controls": ["guide"]}, defaults["a133"]["shipped_default"])
        self.assertEqual({"shape": "chord", "controls": ["select", "start"]}, defaults["fixture-buttonless"]["shipped_default"])

        a523 = json.loads((ROOT / defaults["a523"]["contract_fixture"]).read_text())
        a133 = json.loads((ROOT / defaults["a133"]["contract_fixture"]).read_text())
        a523_controls = {item["position"]: item for item in a523["physical_controls"]}
        a133_controls = {item["position"]: item for item in a133["physical_controls"]}
        self.assertEqual("KEY_HOMEPAGE", a523_controls["home"]["input_code"])
        self.assertEqual("Home", a523_controls["home"]["printed_label"])
        self.assertEqual("BTN_MODE", a133_controls["guide"]["input_code"])
        self.assertNotIn("printed_label", a133_controls["guide"])
        self.assertEqual("pf-guide", a133_controls["guide"]["fallback_glyph"]["id"])

    def test_re_resolution_proofs(self) -> None:
        validator.validate_defaults_registry(self.defaults)
        cases = {item["id"]: item for item in self.defaults["re_resolution_fixtures"]}
        self.assertEqual(["guide"], cases["a523-home-on-a133"]["expected_binding"]["controls"])
        self.assertEqual(["select", "start"], cases["guide-on-buttonless"]["expected_binding"]["controls"])
        self.assertTrue(all(item["expected_notice"] for item in cases.values()))

    def test_reference_json_schema(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("optional jsonschema package unavailable")
        schema = json.loads((ROOT.parent / "schemas/shell-input-contract-v1.schema.json").read_text())
        checker = jsonschema.Draft202012Validator(schema)
        checker.validate(self.shipped)
        checker.validate(self.shapes)
        checker.validate(self.defaults)
        for name in ("trimui-smart-pro-s.json", "fixture-buttonless.json"):
            checker.validate(json.loads((ROOT / "fixtures" / name).read_text()))


if __name__ == "__main__":
    unittest.main()
