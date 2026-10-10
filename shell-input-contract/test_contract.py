#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        self.assertEqual(2, self.shipped["schema_version"])
        controls = {item["position"]: item for item in self.shipped["physical_controls"]}
        self.assertEqual("A", controls["east"]["printed_label"])
        self.assertEqual("B", controls["south"]["printed_label"])
        mapping = {item["action"]: item["binding"] for item in self.shipped["effective_map"]}
        self.assertEqual(["east"], mapping["Activate"]["controls"])
        self.assertEqual(["south"], mapping["Back"]["controls"])
        self.assertEqual({"shape": "single_press", "controls": ["guide"]}, mapping["SystemMenu"])

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
                if "system_menu_copy_actions" in instruction:
                    for action in instruction["system_menu_copy_actions"]:
                        with self.subTest(action=action):
                            changed = copy.deepcopy(self.shipped)
                            menu = next(item for item in changed["effective_map"] if item["action"] == "SystemMenu")
                            other = next(item for item in changed["effective_map"] if item["action"] == action)
                            menu["binding"] = copy.deepcopy(other["binding"])
                            with self.assertRaises(validator.ContractError) as raised:
                                validator.validate_contract(changed, path.name)
                            self.assertEqual(instruction["expected_reason"], raised.exception.reason)
                    continue
                if instruction.get("target") == "defaults-registry":
                    changed = copy.deepcopy(self.defaults)
                    entry = changed["system_menu_defaults"][instruction["device_id"]]
                    if "replace_contract_fixture" in instruction:
                        entry["contract_fixture"] = instruction["replace_contract_fixture"]
                    else:
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
                elif "duplicate_action" in instruction:
                    duplicate = next(
                        item for item in changed["effective_map"]
                        if item["action"] == instruction["duplicate_action"]
                    )
                    changed["effective_map"].append(copy.deepcopy(duplicate))
                elif "remove_physical_controls" in instruction:
                    removed = set(instruction["remove_physical_controls"])
                    changed["physical_controls"] = [
                        item for item in changed["physical_controls"]
                        if item["position"] not in removed
                    ]
                elif "invalid_fallback_glyph_id" in instruction:
                    changed["physical_controls"][0]["fallback_glyph"]["id"] = instruction["invalid_fallback_glyph_id"]
                elif instruction.get("target") != "defaults-registry":
                    safe = next(item for item in changed["effective_map"] if item["action"] == "SystemMenu")
                    face = next(item for item in changed["effective_map"] if item["action"] == instruction["system_menu_copy_action"])
                    if not instruction.get("preserve_system_menu_context", False):
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
        self.assertEqual({"chord", "hold", "double_press"}, {item["binding"]["shape"] for item in decoded["system_menu_alternatives"]})
        default = next(item for item in self.shipped["effective_map"] if item["action"] == "SystemMenu")
        self.assertEqual("single_press", default["binding"]["shape"])

    def test_per_device_shipped_defaults(self) -> None:
        validator.validate_defaults_registry(self.defaults)
        defaults = self.defaults["system_menu_defaults"]
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
        schema = json.loads((ROOT.parent / "schemas/shell-input-contract-v2.schema.json").read_text())
        schema_bindings = [item["const"] for item in schema["$defs"]["systemMenuBinding"]["oneOf"]]
        self.assertEqual(list(validator.SYSTEM_MENU_BINDINGS), schema_bindings)
        checker = jsonschema.Draft202012Validator(schema)
        checker.validate(self.shipped)
        checker.validate(self.shapes)
        checker.validate(self.defaults)
        for name in ("trimui-smart-pro-s.json", "fixture-buttonless.json"):
            checker.validate(json.loads((ROOT / "fixtures" / name).read_text()))

        missing = copy.deepcopy(self.shipped)
        missing["effective_map"] = [item for item in missing["effective_map"] if item["action"] != "SystemMenu"]
        duplicate = copy.deepcopy(self.shipped)
        duplicate["effective_map"].append(copy.deepcopy(duplicate["effective_map"][-1]))
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(missing)
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(duplicate)
        for action in validator.ACTIONS - {"SystemMenu"}:
            collision = copy.deepcopy(self.shipped)
            menu = next(item for item in collision["effective_map"] if item["action"] == "SystemMenu")
            other = next(item for item in collision["effective_map"] if item["action"] == action)
            menu["binding"] = copy.deepcopy(other["binding"])
            with self.subTest(schema_collision=action), self.assertRaises(jsonschema.ValidationError):
                checker.validate(collision)

    def test_system_menu_provider_v1_includes_shown_and_is_additive(self) -> None:
        fixture = json.loads((ROOT / "fixtures/system-menu-provider-v1.json").read_text())
        validator.validate_provider_protocol_fixture(fixture)
        self.assertIn("shown", {message["type"] for message in fixture["messages"]})

        additive = copy.deepcopy(fixture)
        shown = next(message for message in additive["messages"] if message["type"] == "shown")
        shown["future_optional"] = {"app_id": "reserved-but-not-implemented"}
        validator.validate_provider_protocol_fixture(additive)

        missing_shown = copy.deepcopy(fixture)
        missing_shown["messages"] = [
            message for message in missing_shown["messages"] if message["type"] != "shown"
        ]
        with self.assertRaises(validator.ContractError):
            validator.validate_provider_protocol_fixture(missing_shown)

        wrong_major = copy.deepcopy(fixture)
        next(message for message in wrong_major["messages"] if message["type"] == "shown")["version"] = 2
        with self.assertRaises(validator.ContractError):
            validator.validate_provider_protocol_fixture(wrong_major)

        try:
            import jsonschema
        except ImportError:
            self.skipTest("optional jsonschema package unavailable")
        schema = json.loads((ROOT.parent / "schemas/system-menu-provider-v1.schema.json").read_text())
        checker = jsonschema.Draft202012Validator(schema)
        checker.validate(additive)
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(missing_shown)
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(wrong_major)

    def test_frozen_v1_documents_and_supported_migrations(self) -> None:
        contract = copy.deepcopy(self.shipped)
        contract["schema_version"] = 1
        contract["protected_actions"] = ["SafeReturn"]
        next(item for item in contract["effective_map"] if item["action"] == "SystemMenu")["action"] = "SafeReturn"

        shapes = copy.deepcopy(self.shapes)
        shapes["schema_version"] = 1
        shapes["safe_return_alternatives"] = shapes.pop("system_menu_alternatives")

        defaults = copy.deepcopy(self.defaults)
        defaults["schema_version"] = 1
        defaults["safe_return_defaults"] = defaults.pop("system_menu_defaults")
        defaults["re_resolution_rule"]["invariant"] = "SafeReturn-never-unreachable"

        v1_schema = json.loads((ROOT.parent / "schemas/shell-input-contract-v1.schema.json").read_text())
        try:
            import jsonschema
        except ImportError:
            jsonschema = None
        if jsonschema is not None:
            checker = jsonschema.Draft202012Validator(v1_schema)
            for document in (contract, shapes, defaults):
                checker.validate(document)

        validator.validate_contract(contract)
        validator.validate_binding_set(shapes)
        migrated_contract = validator.migrate_v1(contract)
        migrated_shapes = validator.migrate_v1(shapes)
        self.assertEqual(self.shipped, migrated_contract)
        self.assertEqual(self.shapes, migrated_shapes)
        if jsonschema is not None:
            v2_schema = json.loads((ROOT.parent / "schemas/shell-input-contract-v2.schema.json").read_text())
            checker = jsonschema.Draft202012Validator(v2_schema)
            checker.validate(migrated_contract)
            checker.validate(migrated_shapes)
        with self.assertRaises(validator.ContractError) as raised:
            validator.validate_defaults_registry(defaults)
        self.assertEqual("contract-version-mismatch", raised.exception.reason)

    def test_noncanonical_v1_migrations_fail_closed(self) -> None:
        contract = copy.deepcopy(self.shipped)
        contract["schema_version"] = 1
        contract["protected_actions"] = ["SafeReturn"]
        protected = next(item for item in contract["effective_map"] if item["action"] == "SystemMenu")
        protected.update(
            action="SafeReturn",
            context="overlay",
            binding={"shape": "single_press", "controls": ["l1"]},
        )
        validator.validate_contract(contract)
        with self.assertRaises(validator.ContractError) as raised:
            validator.migrate_v1(contract)
        self.assertEqual("migration-unsupported", raised.exception.reason)

        shapes = copy.deepcopy(self.shapes)
        shapes["schema_version"] = 1
        shapes["safe_return_alternatives"] = shapes.pop("system_menu_alternatives")
        shapes["safe_return_alternatives"][0]["binding"] = {
            "shape": "single_press",
            "controls": ["l1"],
        }
        validator.validate_binding_set(shapes)
        with self.assertRaises(validator.ContractError) as raised:
            validator.migrate_v1(shapes)
        self.assertEqual("migration-unsupported", raised.exception.reason)

        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = Path(temporary)
            defaults = copy.deepcopy(self.defaults)
            defaults["schema_version"] = 1
            defaults["safe_return_defaults"] = defaults.pop("system_menu_defaults")
            defaults["re_resolution_rule"]["invariant"] = "SafeReturn-never-unreachable"
            for device_id, entry in defaults["safe_return_defaults"].items():
                source = ROOT / entry["contract_fixture"]
                fixture = json.loads(source.read_text())
                fixture["schema_version"] = 1
                fixture["protected_actions"] = ["SafeReturn"]
                mapping = next(item for item in fixture["effective_map"] if item["action"] == "SystemMenu")
                mapping["action"] = "SafeReturn"
                if device_id == "a133":
                    mapping["binding"] = {"shape": "single_press", "controls": ["l1"]}
                    entry["shipped_default"] = copy.deepcopy(mapping["binding"])
                entry["descriptor"] = "synthetic:fixture-buttonless"
                entry["contract_fixture"] = f"{device_id}.json"
                (fixture_root / entry["contract_fixture"]).write_text(json.dumps(fixture))
            defaults["re_resolution_fixtures"][0]["expected_binding"] = {
                "shape": "single_press",
                "controls": ["l1"],
            }
            defaults["re_resolution_fixtures"][1]["stored_binding"] = {
                "shape": "single_press",
                "controls": ["l1"],
            }
            with mock.patch.object(validator, "ROOT", fixture_root):
                validator.validate_defaults_registry(defaults)
                with self.assertRaises(validator.ContractError) as raised:
                    validator.migrate_v1(defaults)
            self.assertEqual("migration-unsupported", raised.exception.reason)

    def test_v2_validator_enforces_schema_only_menu_bindings_and_fixture_versions(self) -> None:
        validator.validate_contract(self.shipped)
        validator.validate_binding_set(self.shapes)
        validator.validate_defaults_registry(self.defaults)

        non_global = copy.deepcopy(self.shipped)
        next(item for item in non_global["effective_map"] if item["action"] == "SystemMenu")["context"] = "overlay"
        with self.assertRaises(validator.ContractError):
            validator.validate_contract(non_global)

        unruled_menu = copy.deepcopy(self.shipped)
        next(item for item in unruled_menu["effective_map"] if item["action"] == "SystemMenu")["binding"] = {
            "shape": "single_press",
            "controls": ["l1"],
        }
        with self.assertRaises(validator.ContractError):
            validator.validate_contract(unruled_menu)

        for ruled_binding in validator.SYSTEM_MENU_BINDINGS:
            reserved_for_app = copy.deepcopy(self.shipped)
            application = next(
                item for item in reserved_for_app["effective_map"]
                if item["action"] == "Activate"
            )
            application["binding"] = copy.deepcopy(ruled_binding)
            with self.subTest(reserved_for_app=ruled_binding), self.assertRaises(validator.ContractError):
                validator.validate_contract(reserved_for_app)

        unruled_alternative = copy.deepcopy(self.shapes)
        unruled_alternative["system_menu_alternatives"][0]["binding"] = {
            "shape": "single_press",
            "controls": ["l1"],
        }
        with self.assertRaises(validator.ContractError):
            validator.validate_binding_set(unruled_alternative)

        unruled_default = copy.deepcopy(self.defaults)
        unruled_default["system_menu_defaults"]["a133"]["shipped_default"] = {
            "shape": "single_press",
            "controls": ["l1"],
        }
        with self.assertRaises(validator.ContractError):
            validator.validate_defaults_registry(unruled_default)

        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = Path(temporary)
            defaults = copy.deepcopy(self.defaults)
            for device_id, entry in defaults["system_menu_defaults"].items():
                fixture = json.loads((ROOT / entry["contract_fixture"]).read_text())
                fixture["schema_version"] = 1
                fixture["protected_actions"] = ["SafeReturn"]
                protected = next(
                    item for item in fixture["effective_map"]
                    if item["action"] == "SystemMenu"
                )
                protected["action"] = "SafeReturn"
                entry["descriptor"] = "synthetic:fixture-buttonless"
                entry["contract_fixture"] = f"{device_id}.json"
                (fixture_root / entry["contract_fixture"]).write_text(json.dumps(fixture))
            with mock.patch.object(validator, "ROOT", fixture_root):
                with self.assertRaises(validator.ContractError) as raised:
                    validator.validate_defaults_registry(defaults)
            self.assertIn("schema version", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
