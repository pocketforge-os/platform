#!/usr/bin/env python3
"""Stdlib validator and v1-to-v2 migrator for PocketForge's shell input contract.

Generations: v1 (SafeReturn, frozen), v2 (SystemMenu, frozen), v3 (device classes,
osk/osk.edit/pointer contexts, stick and on-screen binding shapes). v2->v3 has no
automatic migration: the class defaults ship as coordinated fixture data.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
BUTTON_POSITIONS = {"east", "south", "west", "north", "start", "select", "guide", "home", "l1", "r1", "l2", "r2"}
STICK_POSITIONS = {"lstick", "rstick"}
POSITIONS = BUTTON_POSITIONS | {"l3", "r3", "dpad_up", "dpad_down", "dpad_left", "dpad_right"} | STICK_POSITIONS
AXES = {"horizontal", "vertical"}
DIRECTIONS = {"up", "down", "left", "right"}
ACTIONS = {
    "Activate", "Back", "Move.up", "Move.down", "Move.left", "Move.right",
    "Quick", "Search.open", "Search.submit", "Search.cancel", "SystemMenu",
}
OSK_ACTIONS = {
    "Type", "Close", "Backspace", "Space", "Shift", "Symbols",
    "CursorLeft", "CursorRight", "Commit", "NextLayout", "EditPad",
    "SuggestPick", "SuggestList",
}
OSK_EDIT_ACTIONS = {
    "WordLeft", "WordRight", "Select", "SelectAll", "Copy", "Cut", "Paste", "Back", "Done",
}
POINTER_ACTIONS = {
    "LeftClick", "RightClick", "MiddleClick", "Escape", "Back", "Forward",
    "Slow", "ScrollMode", "Enter", "Tab",
}
V3_ACTIONS = ACTIONS | {"Start"} | OSK_ACTIONS | OSK_EDIT_ACTIONS | POINTER_ACTIONS
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
DEVICE_CLASSES = ("two_stick", "no_stick", "minimal")
MAPPING_CONTEXTS = {"shell", "search", "global", "osk", "osk.edit", "pointer"}
INHERITED_CONTEXTS = {"osk.num"}
KEYBOARD_CONTEXTS = ("osk", "osk.edit")
CLASS_CONTEXTS = ("osk", "osk.edit", "pointer")
# every-menu-spec §4.1/§4.3.1: these keyboard actions keep a physical binding on every
# device class (rule P2 of §4.2), and SuggestPick only ever rides a stick or the D-pad.
REQUIRED_PHYSICAL_KEYBOARD = {
    ("osk", "Type"), ("osk", "Close"), ("osk", "Backspace"), ("osk", "Space"), ("osk", "SuggestPick"),
}
# §4.1: the full suggestion list is a two-stick affordance; it is the one keyboard
# action a class may ship without (the keyboard itself stays usable).
NULLABLE_KEYBOARD = {("osk", "SuggestList")}
ACTION_CONTEXTS: dict[str, set[str]] = {
    action: {"shell"}
    for action in ("Activate", "Move.up", "Move.down", "Move.left", "Move.right", "Quick")
}
ACTION_CONTEXTS["Back"] = {"shell", "osk.edit", "pointer"}
for _action in ("Search.open", "Search.submit", "Search.cancel"):
    ACTION_CONTEXTS[_action] = {"search"}
ACTION_CONTEXTS["SystemMenu"] = {"global"}
ACTION_CONTEXTS["Start"] = {"global"}
for _action in OSK_ACTIONS:
    ACTION_CONTEXTS[_action] = {"osk"}
for _action in OSK_EDIT_ACTIONS:
    ACTION_CONTEXTS.setdefault(_action, set()).add("osk.edit")
for _action in POINTER_ACTIONS:
    ACTION_CONTEXTS.setdefault(_action, set()).add("pointer")
CLASS_DEFAULTS_PATH = "fixtures/device-class-defaults.json"


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


def binding(value: Any, path: str, version: int = 2) -> dict[str, Any]:
    if version >= 3:
        item = obj(value, path, {"shape"}, {"controls", "max_interval_ms", "min_duration_ms", "axis", "direction"})
    else:
        item = obj(value, path, {"shape", "controls"}, {"max_interval_ms", "min_duration_ms"})
    shape = item["shape"]
    shapes = {"single_press", "chord", "double_press", "hold"}
    if version >= 3:
        shapes |= {"stick_axis", "stick_direction", "on_screen"}
    if shape not in shapes:
        fail(f"{path}.shape", "must be a ruled binding shape: " + ", ".join(sorted(shapes)))
    if shape == "on_screen":
        if "controls" in item:
            fail(f"{path}.controls", "on_screen bindings name no controls")
        extras = item.keys() - {"shape"}
        if extras:
            fail(path, f"field(s) invalid for on_screen: {', '.join(sorted(extras))}")
        return item
    controls = item.get("controls")
    positions = POSITIONS if version >= 3 else BUTTON_POSITIONS
    if not isinstance(controls, list) or not controls or any(c not in positions for c in controls):
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
    if version >= 3 and shape in {"stick_axis", "stick_direction"}:
        field, values = ("axis", AXES) if shape == "stick_axis" else ("direction", DIRECTIONS)
        if len(controls) != 1 or controls[0] not in STICK_POSITIONS:
            fail(f"{path}.controls", f"{shape} requires exactly one stick control (lstick or rstick)")
        if item.get(field) not in values:
            fail(f"{path}.{field}", f"must be one of {', '.join(sorted(values))}")
        allowed.add(field)
    extras = item.keys() - allowed
    if extras:
        fail(path, f"field(s) invalid for {shape}: {', '.join(sorted(extras))}")
    return item


def signature(value: dict[str, Any]) -> tuple[Any, ...]:
    return (
        value["shape"],
        tuple(sorted(value.get("controls", []))),
        value.get("max_interval_ms"),
        value.get("min_duration_ms"),
        value.get("axis"),
        value.get("direction"),
    )


def is_system_menu_binding(value: dict[str, Any]) -> bool:
    """Match the finite v2+ binding set exactly as the reference schema does."""
    return value in SYSTEM_MENU_BINDINGS


def require_system_menu_binding(value: dict[str, Any], path: str) -> None:
    if not is_system_menu_binding(value):
        fail(path, "must be one of the ruled SystemMenu bindings")


def class_defaults_table() -> dict[str, dict[tuple[str, str], Any]]:
    """Load, validate and flatten the shipped device-class defaults ({class: {(context, action): binding|None}})."""
    return flatten_class_defaults(validate_class_defaults(load(ROOT / CLASS_DEFAULTS_PATH)))


def flatten_class_defaults(root: dict[str, Any]) -> dict[str, dict[tuple[str, str], Any]]:
    table: dict[str, dict[tuple[str, str], Any]] = {}
    for device_class, contexts in root["device_class_defaults"].items():
        flat: dict[tuple[str, str], Any] = {}
        for context, actions in contexts.items():
            for action, value in actions.items():
                flat[(context, action)] = value
        table[device_class] = flat
    return table


def validate_class_defaults(document: Any, source: str = "class defaults") -> dict[str, Any]:
    if not isinstance(document, dict):
        fail(source, "must be an object")
    if document.get("schema_version") != 3:
        fail(f"{source}.schema_version", "must equal 3")
    root = obj(document, source, {"schema_version", "device_class_defaults"})
    classes = root["device_class_defaults"]
    if not isinstance(classes, dict) or set(classes) != set(DEVICE_CLASSES):
        fail(f"{source}.device_class_defaults", f"must be keyed by exactly {', '.join(DEVICE_CLASSES)}")
    action_sets = {"osk": OSK_ACTIONS, "osk.edit": OSK_EDIT_ACTIONS, "pointer": POINTER_ACTIONS}
    for device_class in DEVICE_CLASSES:
        contexts = obj(classes[device_class], f"{source}.device_class_defaults.{device_class}", set(CLASS_CONTEXTS))
        for context in CLASS_CONTEXTS:
            names = action_sets[context]
            table = obj(contexts[context], f"{source}.device_class_defaults.{device_class}.{context}", names)
            for action in sorted(names):
                path = f"{source}.device_class_defaults.{device_class}.{context}.{action}"
                value = table[action]
                if value is None:
                    if context in KEYBOARD_CONTEXTS and (context, action) not in NULLABLE_KEYBOARD:
                        fail(
                            path,
                            "a keyboard action must resolve to a physical binding or an on-screen key "
                            "on every device class",
                            "unreachable-keyboard-action",
                        )
                    continue
                parsed = binding(value, path, version=3)
                if parsed["shape"] == "on_screen":
                    if context not in KEYBOARD_CONTEXTS:
                        fail(path, "on_screen bindings exist only for on-screen keyboard actions", "on-screen-outside-keyboard")
                    if (context, action) in REQUIRED_PHYSICAL_KEYBOARD:
                        fail(path, f"{context}/{action} must keep a physical binding on every device class", "keyboard-action-requires-physical")
    return root


def v3_contract_checks(root: dict[str, Any], parsed: list[dict[str, Any]], source: str) -> None:
    device_class = root["device_class"]
    for index, item in enumerate(parsed):
        path = f"{source}.effective_map[{index}]"
        context = item["context"]
        if context in INHERITED_CONTEXTS:
            fail(
                f"{path}.context",
                f"{context} inherits its bindings from osk and ships no mappings of its own",
                "inherited-context-mapping",
            )
        if context not in MAPPING_CONTEXTS:
            fail(f"{path}.context", f"unknown context (ruled: {', '.join(sorted(MAPPING_CONTEXTS))})", "unknown-context")
        allowed = ACTION_CONTEXTS.get(item["action"], set())
        if context not in allowed:
            fail(
                path,
                f"{item['action']} does not live in context {context} "
                f"(ruled: {', '.join(sorted(allowed)) or 'nowhere'})",
                "action-context-mismatch",
            )
    seen: set[tuple[str, str]] = set()
    for item in parsed:
        key = (item["context"], item["action"])
        if key in seen:
            fail(f"{source}.effective_map", f"duplicate mapping for {key[0]}/{key[1]}", "duplicate-mapping")
        seen.add(key)
    menu = next(item for item in parsed if item["action"] == "SystemMenu")
    reserved = set(menu["binding"]["controls"]) if menu["binding"]["shape"] == "single_press" else set()
    if reserved:
        for index, item in enumerate(parsed):
            if item is menu:
                continue
            used = reserved & set(item["binding"].get("controls", []))
            if used:
                fail(
                    f"{source}.effective_map[{index}].binding",
                    f"control(s) {', '.join(sorted(used))} are the Menu control(s) reserved for SystemMenu; "
                    "no other action may use them",
                    "menu-reserved-control",
                )
    for index, item in enumerate(parsed):
        path = f"{source}.effective_map[{index}]"
        key = (item["context"], item["action"])
        if item["binding"]["shape"] != "on_screen":
            continue
        if item["context"] not in KEYBOARD_CONTEXTS:
            fail(f"{path}.binding", "on_screen bindings exist only for on-screen keyboard actions", "on-screen-outside-keyboard")
        if key in REQUIRED_PHYSICAL_KEYBOARD:
            fail(
                f"{path}.binding",
                f"{key[0]}/{key[1]} must keep a physical binding on every device class",
                "keyboard-action-requires-physical",
            )
    table = class_defaults_table()[device_class]
    actual = {(item["context"], item["action"]): item for item in parsed if item["context"] in CLASS_CONTEXTS}
    for key in sorted(actual):
        item = actual[key]
        path = f"{source}.effective_map[{parsed.index(item)}]"
        if key not in table:
            fail(path, f"{key[0]}/{key[1]} is not a {device_class} device-class action", "unexpected-class-action")
        expected = table[key]
        if expected is None:
            fail(path, f"{key[0]}/{key[1]} ships absent (null) for device class {device_class}", "unexpected-class-action")
        if expected != item["binding"]:
            fail(
                f"{path}.binding",
                f"shipped binding must equal the {device_class} class default "
                f"{json.dumps(expected, sort_keys=True)}",
                "class-default-mismatch",
            )
    for key in sorted(table):
        if table[key] is None or key in actual:
            continue
        if key[0] in KEYBOARD_CONTEXTS:
            fail(
                f"{source}.effective_map",
                f"{key[0]}/{key[1]} has no mapping: a keyboard action must stay reachable on every device",
                "unreachable-keyboard-action",
            )
        fail(
            f"{source}.effective_map",
            f"{key[0]}/{key[1]} is missing from the shipped {device_class} map",
            "class-default-mismatch",
        )


def validate_contract(document: Any, source: str = "contract") -> dict[str, Any]:
    version_probe = document.get("schema_version") if isinstance(document, dict) else None
    required = {"schema_version", "device_id", "protected_actions", "physical_controls", "effective_map"}
    if version_probe == 3:
        required.add("device_class")
    root = obj(document, source, required)
    version = root["schema_version"]
    if version not in {1, 2, 3}:
        fail(f"{source}.schema_version", "must equal 1, 2, or 3")
    menu_action = "SafeReturn" if version == 1 else "SystemMenu"
    actions = LEGACY_ACTIONS if version == 1 else (V3_ACTIONS if version == 3 else ACTIONS)
    if not isinstance(root["device_id"], str) or not root["device_id"]:
        fail(f"{source}.device_id", "must be a non-empty string")
    if root["protected_actions"] != [menu_action]:
        fail(f"{source}.protected_actions", f"must equal ['{menu_action}']")
    if version == 3 and root["device_class"] not in DEVICE_CLASSES:
        fail(f"{source}.device_class", f"must be one of {', '.join(DEVICE_CLASSES)}", "unknown-device-class")

    controls = root["physical_controls"]
    if not isinstance(controls, list) or not controls:
        fail(f"{source}.physical_controls", "must be a non-empty array")
    positions = POSITIONS if version == 3 else BUTTON_POSITIONS
    seen: set[str] = set()
    for index, raw in enumerate(controls):
        path = f"{source}.physical_controls[{index}]"
        control = obj(raw, path, {"position", "fallback_glyph"}, {"printed_label", "input_code"})
        position = control["position"]
        if position not in positions or position in seen:
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
        parsed_binding = binding(item["binding"], f"{path}.binding", version)
        absent = set(parsed_binding.get("controls", [])) - seen
        if absent:
            fail(
                f"{path}.binding.controls",
                f"control(s) absent from physical_controls: {', '.join(sorted(absent))}",
                "absent-physical-control",
            )
        parsed.append(item)
    required_actions = {"Activate", "Back", menu_action}
    if version == 3:
        required_actions.add("Start")
    missing = required_actions - {item["action"] for item in parsed}
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
    if version >= 2:
        for index, item in enumerate(parsed):
            path = f"{source}.effective_map[{index}]"
            if item["action"] == "SystemMenu":
                if item["context"] != "global":
                    fail(f"{path}.context", "SystemMenu must use the global context")
                require_system_menu_binding(item["binding"], f"{path}.binding")
            elif is_system_menu_binding(item["binding"]):
                fail(f"{path}.binding", "ruled SystemMenu bindings are reserved from application actions")
    if version == 3:
        v3_contract_checks(root, parsed, source)
    return root


def validate_binding_set(document: Any, source: str = "binding fixtures") -> dict[str, Any]:
    if not isinstance(document, dict):
        fail(source, "must be an object")
    version = document.get("schema_version")
    if version not in {1, 2, 3}:
        fail(f"{source}.schema_version", "must equal 1, 2, or 3")
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
        parsed_binding = binding(item["binding"], f"{path}.binding", version)
        if version >= 2:
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


def descriptor_document(reference: str, path: str) -> dict[str, Any]:
    descriptor = ROOT.parent / reference
    try:
        return tomllib.loads(descriptor.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        fail(path, f"cannot read descriptor: {error}")


def descriptor_controls(reference: str, contract: dict[str, Any], path: str) -> dict[str, str | None]:
    if reference.startswith("synthetic:"):
        return {item["position"]: item.get("input_code") for item in contract["physical_controls"]}
    parsed = descriptor_document(reference, path)
    inputs = parsed.get("inputs")
    if not isinstance(inputs, list):
        fail(path, "descriptor must contain inputs")
    return {
        item["id"]: item.get("code")
        for item in inputs
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def cross_check_descriptor(
    reference: str, contract: dict[str, Any], path: str, data: dict[str, Any] | None = None
) -> None:
    """v3: the device descriptor and the contract must agree on the device class (the
    class picks the bindings) and on the confirm hint (X18: accept_default names the
    printed Accept button, which is the shell's Activate position)."""
    if data is None:
        data = descriptor_document(reference, path)
    profile = data.get("input_profile")
    declared_class = profile.get("device_class") if isinstance(profile, dict) else None
    if declared_class != contract.get("device_class"):
        fail(
            path,
            f"descriptor input_profile.device_class {declared_class!r} does not match contract "
            f"device_class {contract.get('device_class')!r} (a descriptor without [input_profile] "
            "cannot pick device-class bindings)",
            "device-class-mismatch",
        )
    accept = data.get("accept_default")
    activate = next(
        (item for item in contract["effective_map"] if item["context"] == "shell" and item["action"] == "Activate"),
        None,
    )
    confirm = activate["binding"]["controls"][0] if activate and activate["binding"].get("controls") else None
    if accept != confirm:
        fail(
            path,
            f"descriptor accept_default {accept!r} does not match the shell Activate control "
            f"{confirm!r} (X18: the confirm hint names the printed Accept button)",
            "accept-default-mismatch",
        )


def validate_defaults_registry(document: Any, source: str = "defaults registry") -> dict[str, Any]:
    if not isinstance(document, dict):
        fail(source, "must be an object")
    version = document.get("schema_version")
    if version not in {1, 2, 3}:
        fail(f"{source}.schema_version", "must equal 1, 2, or 3")
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
    expected_devices = (
        {"a523", "a133", "fixture-buttonless"} if version < 3 else {"a523", "a133", "fixture-no-stick", "fixture-minimal"}
    )
    if not isinstance(defaults, dict) or set(defaults) != expected_devices:
        fail(f"{source}.{defaults_key}", f"must be keyed by {', '.join(sorted(expected_devices))}")
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
        default = binding(item["shipped_default"], f"{path}.shipped_default", version)
        if version >= 2:
            require_system_menu_binding(default, f"{path}.shipped_default")
        descriptor = descriptor_controls(item["descriptor"], contract, f"{path}.descriptor")
        if version == 3 and not item["descriptor"].startswith("synthetic:"):
            cross_check_descriptor(item["descriptor"], contract, f"{path}.descriptor")
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
        stored = binding(item["stored_binding"], f"{path}.stored_binding", version)
        expected = binding(item["expected_binding"], f"{path}.expected_binding", version)
        if version >= 2:
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


def migrate_v2_to_v3(document: Any) -> None:
    """v2 documents have no automatic v3 representation (fail closed, like v1 registries)."""
    if not isinstance(document, dict) or document.get("schema_version") != 2:
        fail("migration.schema_version", "must equal 2")
    if "effective_map" in document:
        validate_contract(document, "migration source")
    fail(
        "migration",
        "v2 documents have no automatic v3 representation: device_class, the device-class "
        "defaults and the osk/pointer maps ship as coordinated fixture data",
        "migration-unsupported",
    )


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
        if "system_menu_defaults" in document or "safe_return_defaults" in document:
            validate_defaults_registry(document, str(path))
        elif "device_class_defaults" in document:
            validate_class_defaults(document, str(path))
        elif "effective_map" in document:
            validate_contract(document, str(path))
        else:
            validate_binding_set(document, str(path))
        print(f"PASS {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
