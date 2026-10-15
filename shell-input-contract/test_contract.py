#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("shell_input_validate", ROOT / "validate.py")
validator = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(validator)

FROZEN_NAMES = ("trimui-smart-pro", "trimui-smart-pro-s", "fixture-buttonless", "binding-shapes", "safe-return-defaults")
V2_NAME_BY_DEVICE = {"a523": "trimui-smart-pro-s", "a133": "trimui-smart-pro", "fixture-buttonless": "fixture-buttonless"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


class ShellInputContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shipped = _load(ROOT / "fixtures/trimui-smart-pro.json")
        cls.shipped_s = _load(ROOT / "fixtures/trimui-smart-pro-s.json")
        cls.no_stick = _load(ROOT / "fixtures/fixture-no-stick.json")
        cls.minimal = _load(ROOT / "fixtures/fixture-minimal.json")
        cls.class_defaults = _load(ROOT / "fixtures/device-class-defaults.json")
        cls.shapes = _load(ROOT / "fixtures/binding-shapes.json")
        cls.defaults = _load(ROOT / "fixtures/safe-return-defaults.json")
        cls.v2 = {name: _load(ROOT / f"fixtures/frozen/v2/{name}.json") for name in FROZEN_NAMES}
        cls.v1 = {name: _load(ROOT / f"fixtures/frozen/v1/{name}.json") for name in FROZEN_NAMES}
        cls.class_fixtures = {
            "two_stick": [cls.shipped, cls.shipped_s],
            "no_stick": [cls.no_stick],
            "minimal": [cls.minimal],
        }

    def test_shipped_trimui_truth_and_defaults(self) -> None:
        validator.validate_contract(self.shipped)
        self.assertEqual(3, self.shipped["schema_version"])
        self.assertEqual("two_stick", self.shipped["device_class"])
        controls = {item["position"]: item for item in self.shipped["physical_controls"]}
        self.assertEqual("A", controls["east"]["printed_label"])
        self.assertEqual("B", controls["south"]["printed_label"])
        mapping = {(item["context"], item["action"]): item["binding"] for item in self.shipped["effective_map"]}
        self.assertEqual(["east"], mapping[("shell", "Activate")]["controls"])
        self.assertEqual(["south"], mapping[("shell", "Back")]["controls"])
        self.assertEqual({"shape": "single_press", "controls": ["guide"]}, mapping[("global", "SystemMenu")])
        self.assertEqual({"shape": "single_press", "controls": ["start"]}, mapping[("global", "Start")])
        self.assertEqual({"shape": "single_press", "controls": ["east"]}, mapping[("osk", "Type")])
        self.assertEqual({"shape": "hold", "controls": ["l2"], "min_duration_ms": 250}, mapping[("osk", "Shift")])
        self.assertEqual(
            {"shape": "stick_axis", "controls": ["rstick"], "axis": "horizontal"},
            mapping[("osk", "SuggestPick")],
        )
        self.assertEqual({"shape": "on_screen"}, mapping[("osk", "EditPad")])
        self.assertEqual({"shape": "single_press", "controls": ["start"]}, mapping[("osk.edit", "Done")])
        self.assertEqual({"shape": "single_press", "controls": ["east"]}, mapping[("pointer", "LeftClick")])
        self.assertEqual({"shape": "hold", "controls": ["l2"], "min_duration_ms": 250}, mapping[("pointer", "Slow")])

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
                target = instruction.get("target")
                if target == "defaults-registry":
                    changed = copy.deepcopy(self.defaults)
                    entry = changed["system_menu_defaults"][instruction["device_id"]]
                    if "replace_contract_fixture" in instruction:
                        entry["contract_fixture"] = instruction["replace_contract_fixture"]
                    else:
                        entry["shipped_default"] = instruction["replace_shipped_default"]
                    validate = validator.validate_defaults_registry
                elif target == "class-defaults":
                    changed = copy.deepcopy(self.class_defaults)
                    recipe = instruction["set_entry"]
                    changed["device_class_defaults"][recipe["class"]][recipe["context"]][recipe["action"]] = recipe["value"]
                    validate = validator.validate_class_defaults
                else:
                    changed = copy.deepcopy(self.shipped)
                    validate = validator.validate_contract
                    mappings = changed["effective_map"]
                    if "remove_action" in instruction:
                        changed["effective_map"] = [
                            item for item in mappings
                            if item["action"] != instruction["remove_action"]
                        ]
                    elif "remove_mapping" in instruction:
                        key = instruction["remove_mapping"]
                        changed["effective_map"] = [
                            item for item in mappings
                            if (item["context"], item["action"]) != (key["context"], key["action"])
                        ]
                    elif "duplicate_action" in instruction:
                        duplicate = next(
                            item for item in mappings
                            if item["action"] == instruction["duplicate_action"]
                        )
                        mappings.append(copy.deepcopy(duplicate))
                    elif "duplicate_context_action" in instruction:
                        key = instruction["duplicate_context_action"]
                        duplicate = next(
                            item for item in mappings
                            if (item["context"], item["action"]) == (key["context"], key["action"])
                        )
                        mappings.append(copy.deepcopy(duplicate))
                    elif "set_binding" in instruction:
                        key = instruction["set_binding"]
                        found = next(
                            item for item in mappings
                            if (item["context"], item["action"]) == (key["context"], key["action"])
                        )
                        found["binding"] = copy.deepcopy(key["binding"])
                    elif "add_mapping" in instruction:
                        added = instruction["add_mapping"]
                        mappings.append({
                            "context": added["context"],
                            "action": added["action"],
                            "binding": copy.deepcopy(added["binding"]),
                        })
                    elif "set_context" in instruction:
                        key = instruction["set_context"]
                        found = next(
                            item for item in mappings
                            if (item["context"], item["action"]) == (key["context"], key["action"])
                        )
                        found["context"] = key["new_context"]
                    elif "remove_physical_controls" in instruction:
                        removed = set(instruction["remove_physical_controls"])
                        changed["physical_controls"] = [
                            item for item in changed["physical_controls"]
                            if item["position"] not in removed
                        ]
                    elif "invalid_fallback_glyph_id" in instruction:
                        changed["physical_controls"][0]["fallback_glyph"]["id"] = instruction["invalid_fallback_glyph_id"]
                    else:
                        safe = next(item for item in mappings if item["action"] == "SystemMenu")
                        face = next(item for item in mappings if item["action"] == instruction["system_menu_copy_action"])
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
        self.assertEqual(3, self.shapes["schema_version"])
        encoded = json.dumps(self.shapes, sort_keys=True, separators=(",", ":"))
        decoded = json.loads(encoded)
        validator.validate_binding_set(decoded)
        self.assertEqual(self.shapes, decoded)
        self.assertEqual({"chord", "hold", "double_press"}, {item["binding"]["shape"] for item in decoded["system_menu_alternatives"]})
        default = next(item for item in self.shipped["effective_map"] if item["action"] == "SystemMenu")
        self.assertEqual("single_press", default["binding"]["shape"])

    def test_v3_binding_shapes(self) -> None:
        validator.binding({"shape": "stick_axis", "controls": ["rstick"], "axis": "horizontal"}, "b", 3)
        validator.binding({"shape": "stick_direction", "controls": ["lstick"], "direction": "up"}, "b", 3)
        validator.binding({"shape": "on_screen"}, "b", 3)
        for bad in (
            {"shape": "on_screen", "controls": ["east"]},
            {"shape": "stick_axis", "controls": ["rstick"]},
            {"shape": "stick_axis", "controls": ["dpad_up"], "axis": "horizontal"},
            {"shape": "stick_axis", "controls": ["rstick", "lstick"], "axis": "horizontal"},
            {"shape": "stick_axis", "controls": ["rstick"], "axis": "diagonal"},
            {"shape": "stick_direction", "controls": ["rstick"], "direction": "down", "axis": "horizontal"},
            {"shape": "single_press", "controls": []},
            {"shape": "single_press"},
        ):
            with self.subTest(bad=bad), self.assertRaises(validator.ContractError):
                validator.binding(bad, "b", 3)
        # the frozen generations never accept the v3 shapes or positions
        for version in (1, 2):
            with self.subTest(version=version):
                with self.assertRaises(validator.ContractError):
                    validator.binding({"shape": "on_screen"}, "b", version)
                with self.assertRaises(validator.ContractError):
                    validator.binding({"shape": "stick_axis", "controls": ["rstick"], "axis": "horizontal"}, "b", version)
                with self.assertRaises(validator.ContractError):
                    validator.binding({"shape": "single_press", "controls": ["dpad_up"]}, "b", version)

    def test_device_class_fixtures_resolve_every_spec_action(self) -> None:
        """AC: the two_stick, no_stick and minimal fixtures resolve every §4.1 and §4.3.1 action."""
        table = validator.flatten_class_defaults(validator.validate_class_defaults(self.class_defaults))
        for device_class, documents in self.class_fixtures.items():
            for document in documents:
                with self.subTest(device=document["device_id"]):
                    validator.validate_contract(document)
                    self.assertEqual(device_class, document["device_class"])
                    actual = {
                        (item["context"], item["action"]): item["binding"]
                        for item in document["effective_map"]
                        if item["context"] in validator.CLASS_CONTEXTS
                    }
                    expected = {key: value for key, value in table[device_class].items() if value is not None}
                    self.assertEqual(set(expected), set(actual))
                    for key in sorted(expected):
                        self.assertEqual(expected[key], actual[key], f"{key[0]}/{key[1]}")
                    controls = {item["position"] for item in document["physical_controls"]}
                    for key in sorted(validator.REQUIRED_PHYSICAL_KEYBOARD):
                        self.assertNotEqual("on_screen", actual[key]["shape"], f"{key[0]}/{key[1]} must stay physical (§4.2 P2)")
                        self.assertTrue(set(actual[key].get("controls", [])) <= controls)

    def test_per_device_shipped_defaults(self) -> None:
        validator.validate_defaults_registry(self.defaults)
        defaults = self.defaults["system_menu_defaults"]
        self.assertEqual({"a523", "a133", "fixture-no-stick", "fixture-minimal"}, set(defaults))
        self.assertEqual({"shape": "single_press", "controls": ["home"]}, defaults["a523"]["shipped_default"])
        self.assertEqual({"shape": "single_press", "controls": ["guide"]}, defaults["a133"]["shipped_default"])
        self.assertEqual({"shape": "chord", "controls": ["select", "start"]}, defaults["fixture-no-stick"]["shipped_default"])
        self.assertEqual({"shape": "chord", "controls": ["select", "start"]}, defaults["fixture-minimal"]["shipped_default"])

        a523 = _load(ROOT / defaults["a523"]["contract_fixture"])
        a133 = _load(ROOT / defaults["a133"]["contract_fixture"])
        a523_controls = {item["position"]: item for item in a523["physical_controls"]}
        a133_controls = {item["position"]: item for item in a133["physical_controls"]}
        self.assertEqual("KEY_HOMEPAGE", a523_controls["home"]["input_code"])
        self.assertEqual("Home", a523_controls["home"]["printed_label"])
        self.assertEqual("BTN_MODE", a133_controls["guide"]["input_code"])
        self.assertNotIn("printed_label", a133_controls["guide"])
        self.assertEqual("pf-guide", a133_controls["guide"]["fallback_glyph"]["id"])
        # adjudication #22: l3/r3 are contract positions from v3 on, present exactly where the device has stick clicks
        self.assertIn("l3", a523_controls)
        self.assertIn("r3", a523_controls)
        self.assertNotIn("l3", a133_controls)

    def test_re_resolution_proofs(self) -> None:
        validator.validate_defaults_registry(self.defaults)
        cases = {item["id"]: item for item in self.defaults["re_resolution_fixtures"]}
        self.assertEqual(["guide"], cases["a523-home-on-a133"]["expected_binding"]["controls"])
        self.assertEqual(["select", "start"], cases["guide-on-minimal"]["expected_binding"]["controls"])
        self.assertTrue(all(item["expected_notice"] for item in cases.values()))

    def test_registry_cross_checks_descriptor_profile_and_accept_default(self) -> None:
        """v3 registries tie the contract to the descriptor: the class picks the bindings, and
        accept_default is the shell's Activate position (X18)."""
        contract = self.shipped
        with open(ROOT.parent / "devices/a133/capabilities.toml", "rb") as handle:
            data = tomllib.load(handle)
        # positive control: the shipped descriptor agrees with the shipped contract
        validator.cross_check_descriptor("devices/a133/capabilities.toml", contract, "descriptor", data=data)
        validator.cross_check_descriptor("devices/a133/capabilities.toml", contract, "descriptor")

        tampered = copy.deepcopy(data)
        tampered["input_profile"]["device_class"] = "no_stick"
        with self.assertRaises(validator.ContractError) as raised:
            validator.cross_check_descriptor("devices/a133/capabilities.toml", contract, "descriptor", data=tampered)
        self.assertEqual("device-class-mismatch", raised.exception.reason)

        tampered = copy.deepcopy(data)
        del tampered["input_profile"]
        with self.assertRaises(validator.ContractError) as raised:
            validator.cross_check_descriptor("devices/a133/capabilities.toml", contract, "descriptor", data=tampered)
        self.assertEqual("device-class-mismatch", raised.exception.reason)

        tampered = copy.deepcopy(data)
        tampered["accept_default"] = "south"
        with self.assertRaises(validator.ContractError) as raised:
            validator.cross_check_descriptor("devices/a133/capabilities.toml", contract, "descriptor", data=tampered)
        self.assertEqual("accept-default-mismatch", raised.exception.reason)

    def test_reference_json_schema(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("optional jsonschema package unavailable")
        schemas = {
            version: json.loads((ROOT.parent / f"schemas/shell-input-contract-v{version}.schema.json").read_text())
            for version in (1, 2, 3)
        }
        for version in (2, 3):
            schema_bindings = [item["const"] for item in schemas[version]["$defs"]["systemMenuBinding"]["oneOf"]]
            self.assertEqual(list(validator.SYSTEM_MENU_BINDINGS), schema_bindings)
        checker = jsonschema.Draft202012Validator(schemas[3])
        for document in (self.shipped, self.shipped_s, self.no_stick, self.minimal,
                         self.class_defaults, self.shapes, self.defaults):
            checker.validate(document)
        jsonschema.Draft202012Validator(schemas[2]).validate(self.v2["trimui-smart-pro"])
        jsonschema.Draft202012Validator(schemas[1]).validate(self.v1["trimui-smart-pro"])

        missing = copy.deepcopy(self.shipped)
        missing["effective_map"] = [item for item in missing["effective_map"] if item["action"] != "SystemMenu"]
        duplicate = copy.deepcopy(self.shipped)
        duplicate["effective_map"].append(copy.deepcopy(duplicate["effective_map"][-1]))
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(missing)
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(duplicate)

        no_class = copy.deepcopy(self.shipped)
        del no_class["device_class"]
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(no_class)

        unknown_position = copy.deepcopy(self.shipped)
        unknown_position["physical_controls"].append({
            "position": "dpad",
            "fallback_glyph": {"source": "pocketforge", "id": "pf-dpad"},
        })
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(unknown_position)

        pointer_on_screen = copy.deepcopy(self.shipped)
        next(item for item in pointer_on_screen["effective_map"]
             if item["action"] == "LeftClick")["binding"] = {"shape": "on_screen"}
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(pointer_on_screen)

        stick_on_dpad = copy.deepcopy(self.shipped)
        next(item for item in stick_on_dpad["effective_map"]
             if item["action"] == "SuggestPick")["binding"] = {
            "shape": "stick_axis", "controls": ["dpad_up"], "axis": "horizontal",
        }
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(stick_on_dpad)

        unknown_context = copy.deepcopy(self.shipped)
        next(item for item in unknown_context["effective_map"]
             if (item["context"], item["action"]) == ("osk", "Type"))["context"] = "front-room"
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(unknown_context)

        menu_binding = next(item for item in self.shipped["effective_map"]
                            if item["action"] == "SystemMenu")["binding"]
        present = {item["action"] for item in self.shipped["effective_map"]}
        for action in sorted((validator.V3_ACTIONS - {"SystemMenu"}) & present):
            collision = copy.deepcopy(self.shipped)
            menu = next(item for item in collision["effective_map"] if item["action"] == "SystemMenu")
            other = next(item for item in collision["effective_map"] if item["action"] == action)
            menu["binding"] = copy.deepcopy(other["binding"])
            with self.subTest(schema_collision=action), self.assertRaises(jsonschema.ValidationError):
                checker.validate(collision)

        # an action the fixture legitimately omits (ScrollMode ships only when !two_sticks)
        # may not smuggle a ruled menu binding into the map either
        absent = copy.deepcopy(self.shipped)
        absent["effective_map"].append({
            "context": "pointer",
            "action": "ScrollMode",
            "binding": copy.deepcopy(menu_binding),
        })
        with self.assertRaises(jsonschema.ValidationError):
            checker.validate(absent)

    def test_runtime108_bootstrap_subset_includes_shown_and_is_additive(self) -> None:
        # The seven-frame fixture is the runtime#108 bootstrap compatibility subset
        # of provider protocol v1 (see test_provider_subset_is_bootstrap_compat_not_exhaustive_v1).
        fixture = json.loads((ROOT / "fixtures/system-menu-provider-v1.json").read_text())
        validator.validate_bootstrap_protocol_fixture(fixture)
        self.assertIn("shown", {message["type"] for message in fixture["messages"]})

        additive = copy.deepcopy(fixture)
        shown = next(message for message in additive["messages"] if message["type"] == "shown")
        shown["future_optional"] = {"app_id": "future-snapshot-example"}
        validator.validate_bootstrap_protocol_fixture(additive)

        missing_shown = copy.deepcopy(fixture)
        missing_shown["messages"] = [
            message for message in missing_shown["messages"] if message["type"] != "shown"
        ]
        with self.assertRaises(validator.ContractError):
            validator.validate_bootstrap_protocol_fixture(missing_shown)

        wrong_major = copy.deepcopy(fixture)
        next(message for message in wrong_major["messages"] if message["type"] == "shown")["version"] = 2
        with self.assertRaises(validator.ContractError):
            validator.validate_bootstrap_protocol_fixture(wrong_major)

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

    def test_provider_subset_is_bootstrap_compat_not_exhaustive_v1(self) -> None:
        # runtime#112 pairing, option (b): the seven-frame schema/fixture is the
        # runtime#108 bootstrap compatibility subset of provider protocol v1.  Its
        # exact-message-set check is exact WITHIN that fixture only; the full v1
        # vocabulary is normative in the runtime repo's docs/input-ipc.md section 3,
        # which additively defines closed, secure_entry and pong (provider -> router)
        # plus dismiss and ping (router -> provider) in the same major.
        fixture = _load(ROOT / "fixtures/system-menu-provider-v1.json")

        # The shown frame's wire shape never changes (runtime MenuToRouter::Shown).
        shown = next(message for message in fixture["messages"] if message["type"] == "shown")
        self.assertEqual({"version": 1, "type": "shown"}, shown)

        # Positive control: every additive runtime v1 frame is recognized vocabulary,
        # not an "unknown provider protocol message".  Field shapes stay normative in
        # runtime docs/input-ipc.md section 3 and machine-checked in the runtime repo
        # (section 11); this validator deliberately does not duplicate them.
        for frame in (
            {"version": 1, "type": "closed", "reason": "resume"},
            {"version": 1, "type": "secure_entry", "active": True},
            {"version": 1, "type": "pong", "seq": 7},
            {"version": 1, "type": "dismiss", "reason": "hold_return"},
            {"version": 1, "type": "ping", "seq": 7},
        ):
            with self.subTest(additive=frame["type"]):
                self.assertEqual(
                    frame["type"],
                    validator.validate_provider_message(frame, "additive")[0],
                )

        # Negative control: exactness is scoped to the bootstrap fixture — a fixture
        # carrying an additive runtime frame is not the bootstrap subset and is refused.
        inflated = copy.deepcopy(fixture)
        inflated["messages"].append({"version": 1, "type": "pong", "seq": 1})
        with self.assertRaises(validator.ContractError):
            validator.validate_bootstrap_protocol_fixture(inflated)

        # Negative control: a genuinely unknown type stays unknown.
        with self.assertRaises(validator.ContractError):
            validator.validate_provider_message({"version": 1, "type": "teleport"}, "unknown")

        # Doc check: the schema and README must label the subset, name the additive
        # frames, and cite the runtime contract normatively instead of claiming the
        # exhaustive v1 vocabulary or policies pending owner approval.
        schema = json.loads((ROOT.parent / "schemas/system-menu-provider-v1.schema.json").read_text())
        self.assertIn("bootstrap", schema["title"])
        self.assertIn("docs/input-ipc.md", schema["description"])
        readme = (ROOT / "README.md").read_text()
        section = readme.split("### Provider protocol v1", 1)[1].split("\n## ", 1)[0]
        self.assertIn("bootstrap compatibility subset", section)
        self.assertIn("docs/input-ipc.md", section)
        for additive in ("closed", "secure_entry", "pong", "dismiss", "ping"):
            self.assertIn(additive, section)
        for stale in (
            "pending owner approval",
            "owner-approved",
            "reserved vocabulary/policy only",
            "does not enforce a deadline",
        ):
            self.assertNotIn(stale, readme)

    def test_frozen_generations_validate_and_migrations(self) -> None:
        for name in ("trimui-smart-pro", "trimui-smart-pro-s", "fixture-buttonless"):
            validator.validate_contract(self.v1[name])
            validator.validate_contract(self.v2[name])
            self.assertEqual(self.v2[name], validator.migrate_v1(self.v1[name]))
        validator.validate_binding_set(self.v1["binding-shapes"])
        validator.validate_binding_set(self.v2["binding-shapes"])
        self.assertEqual(self.v2["binding-shapes"], validator.migrate_v1(self.v1["binding-shapes"]))
        validator.validate_defaults_registry(self.v1["safe-return-defaults"])
        validator.validate_defaults_registry(self.v2["safe-return-defaults"])
        with self.assertRaises(validator.ContractError) as raised:
            validator.migrate_v1(self.v1["safe-return-defaults"])
        self.assertEqual("migration-unsupported", raised.exception.reason)
        # v2 -> v3 is a coordinated fixture release, never an automatic migration
        with self.assertRaises(validator.ContractError) as raised:
            validator.migrate_v2_to_v3(self.v2["trimui-smart-pro"])
        self.assertEqual("migration-unsupported", raised.exception.reason)
        # a v2 document is not a v3 document, and a stale registry generation fails closed
        upgraded = copy.deepcopy(self.v2["trimui-smart-pro"])
        upgraded["schema_version"] = 3
        with self.assertRaises(validator.ContractError):
            validator.validate_contract(upgraded)
        stale = copy.deepcopy(self.v2["safe-return-defaults"])
        stale["system_menu_defaults"]["a133"]["contract_fixture"] = "fixtures/trimui-smart-pro.json"
        with self.assertRaises(validator.ContractError) as raised:
            validator.validate_defaults_registry(stale)
        self.assertEqual("contract-version-mismatch", raised.exception.reason)
        self.assertIn("schema version", raised.exception.detail)

    def test_noncanonical_v1_migrations_fail_closed(self) -> None:
        contract = copy.deepcopy(self.v2["trimui-smart-pro"])
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

        shapes = copy.deepcopy(self.v2["binding-shapes"])
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
            defaults = copy.deepcopy(self.v2["safe-return-defaults"])
            defaults["schema_version"] = 1
            defaults["safe_return_defaults"] = defaults.pop("system_menu_defaults")
            defaults["re_resolution_rule"]["invariant"] = "SafeReturn-never-unreachable"
            for device_id, entry in defaults["safe_return_defaults"].items():
                fixture = copy.deepcopy(self.v2[V2_NAME_BY_DEVICE[device_id]])
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

    def test_v3_validator_enforces_schema_only_menu_bindings_and_registry_generations(self) -> None:
        for document in (self.shipped, self.shipped_s, self.no_stick, self.minimal):
            validator.validate_contract(document)
        validator.validate_binding_set(self.shapes)
        validator.validate_defaults_registry(self.defaults)
        validator.validate_class_defaults(self.class_defaults)

        non_global = copy.deepcopy(self.shipped)
        next(item for item in non_global["effective_map"] if item["action"] == "SystemMenu")["context"] = "overlay"
        with self.assertRaises(validator.ContractError) as raised:
            validator.validate_contract(non_global)
        self.assertEqual("schema", raised.exception.reason)
        self.assertIn("global context", raised.exception.detail)

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

        stale_fixture = copy.deepcopy(self.defaults)
        stale_fixture["system_menu_defaults"]["a133"]["contract_fixture"] = "fixtures/frozen/v2/trimui-smart-pro.json"
        with self.assertRaises(validator.ContractError) as raised:
            validator.validate_defaults_registry(stale_fixture)
        self.assertEqual("contract-version-mismatch", raised.exception.reason)
        self.assertIn("schema version", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
