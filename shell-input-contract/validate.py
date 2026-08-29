#!/usr/bin/env python3
"""Stdlib validator for PocketForge's frozen shell input contract v1."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POSITIONS = {"east", "south", "west", "north", "start", "select", "guide", "l1", "r1", "l2", "r2"}
ACTIONS = {
    "Activate", "Back", "Move.up", "Move.down", "Move.left", "Move.right",
    "Quick", "Search.open", "Search.submit", "Search.cancel", "SafeReturn",
}
FACE_ACTIONS = {"Activate", "Back", "Quick", "Search.open", "Search.submit", "Search.cancel"}
REQUIRED = {"Activate", "Back", "SafeReturn"}


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


def signature(value: dict[str, Any]) -> tuple[Any, ...]:
    return (value["shape"], tuple(sorted(value["controls"])), value.get("max_interval_ms"), value.get("min_duration_ms"))


def validate_contract(document: Any, source: str = "contract") -> dict[str, Any]:
    root = obj(document, source, {"schema_version", "device_id", "protected_actions", "physical_controls", "effective_map"})
    if root["schema_version"] != 1:
        fail(f"{source}.schema_version", "must equal 1")
    if not isinstance(root["device_id"], str) or not root["device_id"]:
        fail(f"{source}.device_id", "must be a non-empty string")
    if root["protected_actions"] != ["SafeReturn"]:
        fail(f"{source}.protected_actions", "must equal ['SafeReturn']")

    controls = root["physical_controls"]
    if not isinstance(controls, list) or not controls:
        fail(f"{source}.physical_controls", "must be a non-empty array")
    seen: set[str] = set()
    for index, raw in enumerate(controls):
        path = f"{source}.physical_controls[{index}]"
        control = obj(raw, path, {"position", "fallback_glyph"}, {"printed_label"})
        position = control["position"]
        if position not in POSITIONS or position in seen:
            fail(f"{path}.position", "must be a unique physical position")
        seen.add(position)
        if "printed_label" in control and (not isinstance(control["printed_label"], str) or not control["printed_label"]):
            fail(f"{path}.printed_label", "must be a non-empty string")
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
        if item["action"] not in ACTIONS:
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
    missing = REQUIRED - {item["action"] for item in parsed}
    if missing:
        fail(f"{source}.effective_map", f"missing required action(s): {', '.join(sorted(missing))}", "missing-required-action")
    for safe in (item for item in parsed if item["action"] == "SafeReturn"):
        for face in (
            item for item in parsed
            if item["action"] in FACE_ACTIONS
            and (safe["context"] == "global" or item["context"] == safe["context"])
        ):
            if signature(safe["binding"]) == signature(face["binding"]):
                fail(f"{source}.effective_map", f"SafeReturn collides with {face['action']} in context {safe['context']}", "safe-return-collision")
    return root


def validate_binding_set(document: Any, source: str = "binding fixtures") -> dict[str, Any]:
    root = obj(document, source, {"schema_version", "safe_return_alternatives"})
    if root["schema_version"] != 1:
        fail(f"{source}.schema_version", "must equal 1")
    alternatives = root["safe_return_alternatives"]
    if not isinstance(alternatives, list) or len(alternatives) != 5:
        fail(f"{source}.safe_return_alternatives", "must contain the five ruled alternatives")
    ids: set[str] = set()
    for index, raw in enumerate(alternatives):
        path = f"{source}.safe_return_alternatives[{index}]"
        item = obj(raw, path, {"id", "binding"})
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in ids:
            fail(f"{path}.id", "must be a unique non-empty string")
        ids.add(item["id"])
        binding(item["binding"], f"{path}.binding")
    return root


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
        if "effective_map" in document:
            validate_contract(document, str(path))
        else:
            validate_binding_set(document, str(path))
        print(f"PASS {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
