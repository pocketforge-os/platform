#!/usr/bin/env python3
"""Stdlib validator and v1-to-v2 migrator for PocketForge's shell input contract."""

from __future__ import annotations

import argparse
import copy
import json
import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POSITIONS = {"east", "south", "west", "north", "start", "select", "guide", "home", "l1", "r1", "l2", "r2"}
ACTIONS = {
    "Activate", "Back", "Move.up", "Move.down", "Move.left", "Move.right",
    "Quick", "Search.open", "Search.submit", "Search.cancel", "SystemMenu",
}
LEGACY_ACTIONS = (ACTIONS - {"SystemMenu"}) | {"SafeReturn"}
SYSTEM_MENU_BINDINGS = (
    {"shape": "single_press", "controls": ["guide"]},
    {"shape": "single_press", "controls": ["home"]},
    {"shape": "chord", "controls": ["select", "start"]},
    {"shape": "hold", "controls": ["guide"], "min_duration_ms": 1000},
    {"shape": "double_press", "controls": ["select", "start"], "max_interval_ms": 700},
    {"shape": "double_press", "controls": ["guide"], "max_interval_ms": 500},
    {"shape": "hold", "controls": ["select", "l1", "r1"], "min_duration_ms": 1000},
)
PROVIDER_MESSAGE_SIGNATURES = {
    ("register", None),
    ("registered", None),
    ("system_menu", None),
    ("ack", "system_menu"),
    ("shown", None),
    ("return", None),
    ("ack", "return"),
}


class ContractError(ValueError):
    def __init__(self, reason: str, path: str, detail: str):
        self.reason, self.path, self.detail = reason, path, detail
        super().__init__(f"{reason}: {path}: {detail}")


def fail(path: str, detail: str, reason: str = "schema") -> None:
    raise ContractError(reason, path, detail)


def obj(value: Any, path: str, required: set[str], optional: set[str] = set()) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(path, "must be an object")
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        fail(path, f"missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        fail(path, f"unknown field(s): {', '.join(sorted(unknown))}")
    return value


def binding(value: Any, path: str) -> dict[str, Any]:
    item = obj(value, path, {"shape", "controls"}, {"max_interval_ms", "min_duration_ms"})
    shape, controls = item["shape"], item["controls"]
    if shape not in {"single_press", "chord", "double_press", "hold"}:
        fail(f"{path}.shape", "must be single_press, chord, double_press, or hold")
    if not isinstance(controls, list) or not controls or any(c not in POSITIONS for c in controls):
        fail(f"{path}.controls", "must be a non-empty array of physical positions")
    if len(controls) != len(set(controls)):
        fail(f"{path}.controls", "must not contain duplicates")
    if shape == "single_press" and len(controls) != 1:
        fail(f"{path}.controls", "single_press requires exactly one control")
    if shape == "chord" and len(controls) < 2:
        fail(f"{path}.controls", "chord requires at least two controls")
    bounds = {"double_press": ("max_interval_ms", 100, 2000), "hold": ("min_duration_ms", 250, 5000)}
    allowed = {"shape", "controls"}
    if shape in bounds:
        field, low, high = bounds[shape]
        allowed.add(field)
        number = item.get(field)
        if not isinstance(number, int) or isinstance(number, bool) or not low <= number <= high:
            fail(f"{path}.{field}", f"must be an integer from {low} through {high}")
    extras = item.keys() - allowed
    if extras:
        fail(path, f"field(s) invalid for {shape}: {', '.join(sorted(extras))}")
    return item


def validate_provider_message(value: Any, path: str) -> tuple[str, str | None]:
    if not isinstance(value, dict):
        fail(path, "must be an object")
    if "version" not in value or "type" not in value:
        fail(path, "must contain version and type")
    if type(value["version"]) is not int or value["version"] != 1:
        fail(f"{path}.version", "must equal 1")
    message_type = value["type"]
    if not isinstance(message_type, str):
        fail(f"{path}.type", "must be a string")
    if message_type == "ack":
        action = value.get("action")
        if action not in {"system_menu", "return"}:
            fail(f"{path}.action", "ack must identify system_menu or return")
        return message_type, action
    if message_type not in {"register", "registered", "system_menu", "shown", "return"}:
        fail(f"{path}.type", "unknown provider protocol message")
    return message_type, None


def validate_provider_protocol_fixture(value: Any, source: str = "provider protocol") -> dict[str, Any]:
    fixture = obj(value, source, {"protocol_version", "messages"})
    if type(fixture["protocol_version"]) is not int or fixture["protocol_version"] != 1:
        fail(f"{source}.protocol_version", "must equal 1")
    messages = fixture["messages"]
    if not isinstance(messages, list):
        fail(f"{source}.messages", "must be an array")
    signatures = [
        validate_provider_message(message, f"{source}.messages[{index}]")
        for index, message in enumerate(messages)
    ]
    if len(signatures) != len(PROVIDER_MESSAGE_SIGNATURES) or set(signatures) != PROVIDER_MESSAGE_SIGNATURES:
        fail(f"{source}.messages", "must contain each v1 message signature exactly once")
    return fixture


def signature(value: dict[str, Any]) -> tuple[Any, ...]:
    return (value["shape"], tuple(sorted(value["controls"])), value.get("max_interval_ms"), value.get("min_duration_ms"))


def is_system_menu_binding(value: dict[str, Any]) -> bool:
    """Match the finite v2 binding set exactly as the reference schema does."""
    return value in SYSTEM_MENU_BINDINGS


def require_system_menu_binding(value: dict[str, Any], path: str) -> None:
    if not is_system_menu_binding(value):
        fail(path, "must be one of the ruled SystemMenu bindings")


def validate_contract(document: Any, source: str = "contract") -> dict[str, Any]:
    root = obj(document, source, {"schema_version", "device_id", "protected_actions", "physical_controls", "effective_map"})
    version = root["schema_version"]
    if version not in {1, 2}:
        fail(f"{source}.schema_version", "must equal 1 or 2")
    menu_action = "SafeReturn" if version == 1 else "SystemMenu"
    actions = LEGACY_ACTIONS if version == 1 else ACTIONS
    if not isinstance(root["device_id"], str) or not root["device_id"]:
        fail(f"{source}.device_id", "must be a non-empty string")
    if root["protected_actions"] != [menu_action]:
        fail(f"{source}.protected_actions", f"must equal ['{menu_action}']")

    controls = root["physical_controls"]
    if not isinstance(controls, list) or not controls:
        fail(f"{source}.physical_controls", "must be a non-empty array")
    seen: set[str] = set()
    for index, raw in enumerate(controls):
        path = f"{source}.physical_controls[{index}]"
        control = obj(raw, path, {"position", "fallback_glyph"}, {"printed_label", "input_code"})
        position = control["position"]
        if position not in POSITIONS or position in seen:
            fail(f"{path}.position", "must be a unique physical position")
        seen.add(position)
        if "printed_label" in control and (not isinstance(control["printed_label"], str) or not control["printed_label"]):
            fail(f"{path}.printed_label", "must be a non-empty string")
        if "input_code" in control and (not isinstance(control["input_code"], str) or re.fullmatch(r"(?:BTN|KEY)_[A-Z0-9_]+", control["input_code"]) is None):
            fail(f"{path}.input_code", "must be a BTN_* or KEY_* input code")
        glyph = obj(control["fallback_glyph"], f"{path}.fallback_glyph", {"source", "id"})
        if glyph["source"] != "pocketforge" or not isinstance(glyph["id"], str) or re.fullmatch(r"pf-[a-z0-9-]+", glyph["id"]) is None:
            fail(f"{path}.fallback_glyph", "must name a source-owned pf-* glyph")

    mappings = root["effective_map"]
    if not isinstance(mappings, list) or not mappings:
        fail(f"{source}.effective_map", "must be a non-empty array")
    parsed: list[dict[str, Any]] = []
    for index, raw in enumerate(mappings):
        path = f"{source}.effective_map[{index}]"
        item = obj(raw, path, {"context", "action", "binding"})
        if not isinstance(item["context"], str) or not item["context"]:
            fail(f"{path}.context", "must be a non-empty string")
        if item["action"] not in actions:
            fail(f"{path}.action", "unknown semantic action")
        parsed_binding = binding(item["binding"], f"{path}.binding")
        absent = set(parsed_binding["controls"]) - seen
        if absent:
            fail(
                f"{path}.binding.controls",
                f"control(s) absent from physical_controls: {', '.join(sorted(absent))}",
                "absent-physical-control",
            )
        parsed.append(item)
    required = {"Activate", "Back", menu_action}
    missing = required - {item["action"] for item in parsed}
    if missing:
        fail(f"{source}.effective_map", f"missing required action(s): {', '.join(sorted(missing))}", "missing-required-action")
    menus = [item for item in parsed if item["action"] == menu_action]
    if len(menus) != 1:
        reason = "safe-return-cardinality" if version == 1 else "system-menu-cardinality"
        fail(f"{source}.effective_map", f"must contain exactly one {menu_action} mapping", reason)
    menu = menus[0]
    for other in (
        item for item in parsed
        if item is not menu and (menu["context"] == "global" or item["context"] == menu["context"])
    ):
        if signature(menu["binding"]) == signature(other["binding"]):
            reason = "safe-return-collision" if version == 1 else "system-menu-collision"
            fail(
                f"{source}.effective_map",
                f"{menu_action} collides with {other['action']} in context {menu['context']}",
                reason,
            )
    if version == 2:
        for index, item in enumerate(parsed):
            path = f"{source}.effective_map[{index}]"
            if item["action"] == "SystemMenu":
                if item["context"] != "global":
                    fail(f"{path}.context", "SystemMenu must use the global context")
                require_system_menu_binding(item["binding"], f"{path}.binding")
            elif is_system_menu_binding(item["binding"]):
                fail(f"{path}.binding", "ruled SystemMenu bindings are reserved from application actions")
    return root


def validate_binding_set(document: Any, source: str = "binding fixtures") -> dict[str, Any]:
    if not isinstance(document, dict):
        fail(source, "must be an object")
    version = document.get("schema_version")
    if version not in {1, 2}:
        fail(f"{source}.schema_version", "must equal 1 or 2")
    key = "safe_return_alternatives" if version == 1 else "system_menu_alternatives"
    root = obj(document, source, {"schema_version", key})
    alternatives = root[key]
    if not isinstance(alternatives, list) or len(alternatives) != 5:
        fail(f"{source}.{key}", "must contain the five ruled alternatives")
    ids: set[str] = set()
    for index, raw in enumerate(alternatives):
        path = f"{source}.{key}[{index}]"
        item = obj(raw, path, {"id", "binding"})
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in ids:
            fail(f"{path}.id", "must be a unique non-empty string")
        ids.add(item["id"])
        parsed_binding = binding(item["binding"], f"{path}.binding")
        if version == 2:
            require_system_menu_binding(parsed_binding, f"{path}.binding")
    return root


def protected_binding(contract: dict[str, Any]) -> dict[str, Any]:
    menu_action = "SafeReturn" if contract["schema_version"] == 1 else "SystemMenu"
    matches = [item["binding"] for item in contract["effective_map"] if item["action"] == menu_action]
    if len(matches) != 1:
        fail("effective_map", f"must contain exactly one {menu_action} mapping")
    return matches[0]


def resolve_system_menu(
    stored_binding: dict[str, Any], current_controls: set[str], shipped_default: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Apply the normative device-portability rule; bool means notice is required."""
    binding(stored_binding, "stored_binding")
    if set(stored_binding["controls"]) <= current_controls:
        return stored_binding, False
    return shipped_default, True


def descriptor_controls(reference: str, contract: dict[str, Any], path: str) -> dict[str, str | None]:
    if reference == "synthetic:fixture-buttonless":
        return {item["position"]: item.get("input_code") for item in contract["physical_controls"]}
    descriptor = ROOT.parent / reference
    try:
        parsed = tomllib.loads(descriptor.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        fail(path, f"cannot read descriptor: {error}")
    inputs = parsed.get("inputs")
    if not isinstance(inputs, list):
        fail(path, "descriptor must contain inputs")
    return {
        item["id"]: item.get("code")
        for item in inputs
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def validate_defaults_registry(document: Any, source: str = "defaults registry") -> dict[str, Any]:
    if not isinstance(document, dict):
        fail(source, "must be an object")
    version = document.get("schema_version")
    if version not in {1, 2}:
        fail(f"{source}.schema_version", "must equal 1 or 2")
    defaults_key = "safe_return_defaults" if version == 1 else "system_menu_defaults"
    root = obj(
        document,
        source,
        {"schema_version", defaults_key, "re_resolution_rule", "re_resolution_fixtures"},
    )

    rule = obj(
        root["re_resolution_rule"],
        f"{source}.re_resolution_rule",
        {"identity_keyed", "absent_control_behavior", "notice", "invariant"},
    )
    invariant = "SafeReturn-never-unreachable" if version == 1 else "SystemMenu-and-Return-never-unreachable"
    expected_rule = {
        "identity_keyed": True,
        "absent_control_behavior": "use-current-device-shipped-default",
        "notice": "one-time-honest",
        "invariant": invariant,
    }
    if rule != expected_rule:
        fail(f"{source}.re_resolution_rule", "must encode the normative System Menu portability rule")

    defaults = root[defaults_key]
    if not isinstance(defaults, dict) or set(defaults) != {"a523", "a133", "fixture-buttonless"}:
        fail(f"{source}.{defaults_key}", "must be keyed by a523, a133, and fixture-buttonless")
    device_controls: dict[str, set[str]] = {}
    for device_id, raw in defaults.items():
        path = f"{source}.{defaults_key}.{device_id}"
        item = obj(raw, path, {"descriptor", "contract_fixture", "shipped_default"})
        if not isinstance(item["descriptor"], str) or not item["descriptor"]:
            fail(f"{path}.descriptor", "must be a non-empty descriptor reference")
        if not isinstance(item["contract_fixture"], str) or not item["contract_fixture"]:
            fail(f"{path}.contract_fixture", "must be a non-empty fixture reference")
        fixture = ROOT / item["contract_fixture"]
        contract = validate_contract(load(fixture), str(fixture))
        if contract["schema_version"] != version:
            fail(
                f"{path}.contract_fixture",
                f"contract schema version {contract['schema_version']} does not match registry version {version}",
                "contract-version-mismatch",
            )
        if contract["device_id"] != device_id:
            fail(f"{path}.contract_fixture", "device identity does not match registry key")
        default = binding(item["shipped_default"], f"{path}.shipped_default")
        if version == 2:
            require_system_menu_binding(default, f"{path}.shipped_default")
        descriptor = descriptor_controls(item["descriptor"], contract, f"{path}.descriptor")
        present = set(descriptor)
        absent = set(default["controls"]) - present
        if absent:
            fail(
                f"{path}.shipped_default.controls",
                f"control(s) absent from physical_controls: {', '.join(sorted(absent))}",
                "absent-physical-control",
            )
        contract_controls = {control["position"]: control for control in contract["physical_controls"]}
        for control_id in default["controls"]:
            declared = contract_controls.get(control_id)
            if declared is None:
                fail(f"{path}.contract_fixture", f"shipped control {control_id} is absent from contract fixture")
            if declared.get("input_code") != descriptor[control_id]:
                fail(f"{path}.contract_fixture", f"input code for {control_id} does not match descriptor")
        if signature(default) != signature(protected_binding(contract)):
            fail(f"{path}.shipped_default", "must match the contract fixture's protected mapping")
        device_controls[device_id] = present

    fixtures = root["re_resolution_fixtures"]
    if not isinstance(fixtures, list) or len(fixtures) != 2:
        fail(f"{source}.re_resolution_fixtures", "must contain the two portability proofs")
    fixture_ids: set[str] = set()
    for index, raw in enumerate(fixtures):
        path = f"{source}.re_resolution_fixtures[{index}]"
        item = obj(raw, path, {"id", "stored_device_id", "current_device_id", "stored_binding", "expected_binding", "expected_notice"})
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in fixture_ids:
            fail(f"{path}.id", "must be a unique non-empty string")
        fixture_ids.add(item["id"])
        if item["stored_device_id"] not in defaults or item["current_device_id"] not in defaults:
            fail(path, f"device ids must reference {defaults_key}")
        stored = binding(item["stored_binding"], f"{path}.stored_binding")
        expected = binding(item["expected_binding"], f"{path}.expected_binding")
        if version == 2:
            require_system_menu_binding(stored, f"{path}.stored_binding")
            require_system_menu_binding(expected, f"{path}.expected_binding")
        if signature(stored) != signature(defaults[item["stored_device_id"]]["shipped_default"]):
            fail(f"{path}.stored_binding", "must match the stated stored device's shipped default")
        current_id = item["current_device_id"]
        resolved, notice = resolve_system_menu(stored, device_controls[current_id], defaults[current_id]["shipped_default"])
        if signature(resolved) != signature(expected) or item["expected_notice"] is not True or notice is not True:
            fail(path, "must prove absent controls re-resolve to the current device default with notice")
    return root


def migrate_v1(document: Any) -> dict[str, Any]:
    """Return the deterministic v2 representation of one validated v1 document."""
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        fail("migration.schema_version", "must equal 1")
    migrated = copy.deepcopy(document)
    migrated["schema_version"] = 2

    def validate_result(validate: Any) -> None:
        try:
            validate(migrated, "migration result")
        except ContractError as error:
            fail(
                error.path,
                f"v1 document has no automatic v2 representation: {error.detail}",
                "migration-unsupported",
            )

    if "effective_map" in migrated:
        validate_contract(document, "migration source")
        migrated["protected_actions"] = ["SystemMenu"]
        for item in migrated["effective_map"]:
            if item["action"] == "SafeReturn":
                item["action"] = "SystemMenu"
        validate_result(validate_contract)
    elif "safe_return_alternatives" in migrated:
        validate_binding_set(document, "migration source")
        migrated["system_menu_alternatives"] = migrated.pop("safe_return_alternatives")
        validate_result(validate_binding_set)
    elif "safe_return_defaults" in migrated:
        validate_defaults_registry(document, "migration source")
        fail(
            "migration.safe_return_defaults",
            "defaults registries require coordinated migration of their referenced contract fixtures",
            "migration-unsupported",
        )
    else:
        fail("migration", "unknown v1 document shape")
    return migrated


def load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(str(path), str(error))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    paths = args.paths or sorted((ROOT / "fixtures").glob("*.json"))
    for path in paths:
        document = load(path)
        if "protocol_version" in document and "messages" in document:
            validate_provider_protocol_fixture(document, str(path))
        elif "system_menu_defaults" in document or "safe_return_defaults" in document:
            validate_defaults_registry(document, str(path))
        elif "effective_map" in document:
            validate_contract(document, str(path))
        else:
            validate_binding_set(document, str(path))
        print(f"PASS {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
