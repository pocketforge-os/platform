#!/usr/bin/env python3
"""Stdlib-only semantic validator for menu-page.schema.json golden fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT.parent / "menu-page.schema.json"
FIXTURES = ROOT / "fixtures"

COMMON = {"id", "kind", "label", "subtitle", "icon", "enabled", "visible", "a11y"}
FIELDS = {
    "action": {"confirm", "stay_open"},
    "toggle": {"bind"},
    "choice": {"bind", "options", "present"},
    "stepper": {"bind", "min", "max", "step", "unit"},
    "info": {"value", "bind"},
    "slider": {"bind", "min", "max", "step"},
    "text": {"bind", "purpose", "max_chars", "secret"},
    "link": {"page"},
    "progress": {"bind", "indeterminate"},
    "binding": {"context", "action"},
    "date_time": {"bind", "fields"},
    "custom": {"renderer"},
}
REQUIRED = {
    "toggle": {"bind"}, "choice": {"bind", "options"},
    "stepper": {"bind", "min", "max"}, "slider": {"bind", "min", "max"},
    "text": {"bind", "max_chars"}, "link": {"page"}, "progress": {"bind"},
    "binding": {"context", "action"}, "date_time": {"bind"}, "custom": {"renderer"},
}
SCHEMA_NAMES = {kind: ("dateTime" if kind == "date_time" else kind) for kind in FIELDS}


class Invalid(ValueError):
    pass


def need(condition: bool, path: str, message: str) -> None:
    if not condition:
        raise Invalid(f"{path}: {message}")


def msg(value: Any, path: str) -> None:
    need(isinstance(value, dict), path, "message must be an object")
    need(set(value) in ({"text"}, {"id"}, {"id", "args"}), path, "message has invalid fields")
    key = "text" if "text" in value else "id"
    need(isinstance(value[key], str), f"{path}.{key}", "must be a string")
    if "args" in value:
        need(isinstance(value["args"], dict), f"{path}.args", "must be an object")
        need(all(isinstance(k, str) and isinstance(v, str) for k, v in value["args"].items()), f"{path}.args", "must map strings to strings")


def bind(value: Any, path: str) -> None:
    need(isinstance(value, dict) and len(value) == 1, path, "binding needs exactly one namespace")
    key, target = next(iter(value.items()))
    need(key in {"pref", "option", "host"}, path, "unknown binding namespace")
    need(isinstance(target, str) and target, path, "binding target must be a non-empty string")


def item(value: Any, path: str) -> None:
    need(isinstance(value, dict), path, "item must be an object")
    need({"id", "kind", "label"} <= set(value), path, "missing id, kind or label")
    kind = value["kind"]
    need(kind in FIELDS, f"{path}.kind", f"unknown kind {kind!r}")
    need(set(value) <= COMMON | FIELDS[kind], path, f"fields do not belong to {kind}")
    need(REQUIRED.get(kind, set()) <= set(value), path, f"missing fields for {kind}")
    need(isinstance(value["id"], str) and value["id"], f"{path}.id", "must be non-empty")
    msg(value["label"], f"{path}.label")
    for name in ("subtitle", "a11y", "value", "unit"):
        if name in value:
            msg(value[name], f"{path}.{name}")
    if "bind" in value:
        bind(value["bind"], f"{path}.bind")
    if kind == "choice":
        need(isinstance(value["options"], list) and 0 < len(value["options"]) <= 64, f"{path}.options", "needs 1..64 options")
        seen = set()
        for index, option in enumerate(value["options"]):
            opath = f"{path}.options[{index}]"
            need(isinstance(option, dict) and {"value", "label"} <= set(option) <= {"value", "label", "detail"}, opath, "invalid option")
            need(isinstance(option["value"], str) and option["value"] not in seen, opath, "value must be a unique string")
            seen.add(option["value"])
            msg(option["label"], f"{opath}.label")
            if "detail" in option:
                msg(option["detail"], f"{opath}.detail")
    if kind in {"stepper", "slider"}:
        need(all(isinstance(value[name], int) for name in ("min", "max")), path, "range bounds must be integers")
        need(value["min"] <= value["max"], path, "min exceeds max")
        need(isinstance(value.get("step", 1), int) and value.get("step", 1) > 0, path, "step must be positive")


def validate_schema_contract(schema: Any) -> None:
    """Prove the published schema and this dependency-free evaluator describe one surface."""
    path = str(SCHEMA)
    need(isinstance(schema, dict), path, "schema must be an object")
    need(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", path, "wrong JSON Schema draft")
    need(schema.get("additionalProperties") is False, path, "top level must be closed")
    need(set(schema.get("required", ())) == {"format", "id", "root", "pages"}, path, "top-level required fields drifted")
    defs = schema.get("$defs")
    need(isinstance(defs, dict), path, "missing $defs")
    common = defs.get("itemCommon", {})
    need(set(common.get("required", ())) == {"id", "kind", "label"}, f"{path}#/$defs/itemCommon", "required fields drifted")
    need(set(common.get("properties", {})) == COMMON, f"{path}#/$defs/itemCommon", "common fields drifted")

    refs = defs.get("item", {}).get("oneOf", [])
    actual_refs = {entry.get("$ref", "").removeprefix("#/$defs/") for entry in refs if isinstance(entry, dict)}
    need(actual_refs == set(SCHEMA_NAMES.values()), f"{path}#/$defs/item", "kind references drifted")
    for kind, schema_name in SCHEMA_NAMES.items():
        variant = defs.get(schema_name)
        vpath = f"{path}#/$defs/{schema_name}"
        need(isinstance(variant, dict) and variant.get("unevaluatedProperties") is False, vpath, "kind must be closed")
        all_of = variant.get("allOf")
        need(isinstance(all_of, list) and len(all_of) == 2, vpath, "kind must combine common and specific fields")
        need(all_of[0] == {"$ref": "#/$defs/itemCommon"}, vpath, "common item reference drifted")
        specific = all_of[1]
        properties = specific.get("properties", {})
        need(properties.get("kind", {}).get("const") == kind, vpath, "kind tag drifted")
        need(set(properties) == {"kind"} | FIELDS[kind], vpath, "kind fields drifted")
        need(set(specific.get("required", ())) == REQUIRED.get(kind, set()), vpath, "required fields drifted")


def validate(document: Any) -> None:
    need(isinstance(document, dict), "$", "document must be an object")
    need(set(document) == {"format", "id", "root", "pages"}, "$", "invalid top-level fields")
    need(document["format"] == "pocketforge.menu/1", "$.format", "unsupported format")
    need(isinstance(document["pages"], list) and document["pages"], "$.pages", "must be non-empty")
    page_ids, item_ids, links = set(), set(), []
    for pindex, page_value in enumerate(document["pages"]):
        path = f"$.pages[{pindex}]"
        need(isinstance(page_value, dict), path, "page must be an object")
        need({"id", "title", "sections"} <= set(page_value) <= {"id", "title", "sections", "tabs", "primary"}, path, "invalid page fields")
        need(page_value["id"] not in page_ids, f"{path}.id", "duplicate page id")
        page_ids.add(page_value["id"])
        msg(page_value["title"], f"{path}.title")
        need(isinstance(page_value["sections"], list), f"{path}.sections", "must be an array")
        local_ids = set()
        for sindex, section in enumerate(page_value["sections"]):
            spath = f"{path}.sections[{sindex}]"
            need(isinstance(section, dict) and "items" in section and set(section) <= {"header", "footer", "items"}, spath, "invalid section")
            for name in ("header", "footer"):
                if name in section:
                    msg(section[name], f"{spath}.{name}")
            need(isinstance(section["items"], list), f"{spath}.items", "must be an array")
            for iindex, row in enumerate(section["items"]):
                ipath = f"{spath}.items[{iindex}]"
                item(row, ipath)
                need(row["id"] not in item_ids, f"{ipath}.id", "duplicate item id")
                item_ids.add(row["id"])
                local_ids.add(row["id"])
                if row["kind"] == "link":
                    links.append((ipath, row["page"]))
        if "primary" in page_value:
            need(page_value["primary"] in local_ids, f"{path}.primary", "must name an item on this page")
    need(document["root"] in page_ids, "$.root", "does not name a page")
    for path, target in links:
        need(target in page_ids, f"{path}.page", "does not name a page")


def main() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validate_schema_contract(schema)
    files = sorted(FIXTURES.glob("*.json"))
    need(bool(files), str(FIXTURES), "no fixtures")
    for fixture in files:
        validate(json.loads(fixture.read_text(encoding="utf-8")))
        print(f"PASS {fixture.relative_to(ROOT.parent.parent)}")


if __name__ == "__main__":
    main()
