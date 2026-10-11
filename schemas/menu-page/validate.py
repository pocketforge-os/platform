#!/usr/bin/env python3
"""Stdlib-only semantic validator for menu-page.schema.json golden fixtures."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT.parent / "menu-page.schema.json"
FIXTURES = ROOT / "fixtures"
SCHEMA_DIGEST = "f868d860038bef99b7ad58d796b06bab7dd80f93f3188ca714d3e0d5a54dbd3f"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

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


def identifier(value: Any, path: str) -> None:
    need(isinstance(value, str), path, "must be a string")
    need(1 <= len(value) <= 128 and ID_RE.fullmatch(value) is not None, path, "must match the id contract")


def boolean(value: Any, path: str) -> None:
    need(type(value) is bool, path, "must be a boolean")


def integer(value: Any, path: str) -> None:
    need(type(value) is int, path, "must be an integer")


def msg(value: Any, path: str) -> None:
    need(isinstance(value, dict), path, "message must be an object")
    need(set(value) in ({"text"}, {"id"}, {"id", "args"}), path, "message has invalid fields")
    key = "text" if "text" in value else "id"
    need(isinstance(value[key], str), f"{path}.{key}", "must be a string")
    if key == "id":
        identifier(value[key], f"{path}.id")
    if "args" in value:
        need(isinstance(value["args"], dict), f"{path}.args", "must be an object")
        need(all(isinstance(k, str) and isinstance(v, str) for k, v in value["args"].items()), f"{path}.args", "must map strings to strings")


def cond(value: Any, path: str) -> None:
    if isinstance(value, str):
        need(value in {"always", "never"}, path, "unknown condition word")
        return
    need(isinstance(value, dict) and len(value) == 1, path, "condition needs exactly one rule")
    name, payload = next(iter(value.items()))
    need(name in {"when", "unless", "all", "any"}, path, "unknown condition rule")
    if name in {"when", "unless"}:
        identifier(payload, f"{path}.{name}")
    else:
        need(isinstance(payload, list), f"{path}.{name}", "must be an array")
        for index, child in enumerate(payload):
            cond(child, f"{path}.{name}[{index}]")


def bind(value: Any, path: str) -> None:
    need(isinstance(value, dict) and len(value) == 1, path, "binding needs exactly one namespace")
    key, target = next(iter(value.items()))
    need(key in {"pref", "option", "host"}, path, "unknown binding namespace")
    identifier(target, f"{path}.{key}")


def confirm(value: Any, path: str) -> None:
    need(isinstance(value, dict), path, "confirm must be an object")
    need({"title", "confirm_label"} <= set(value) <= {"title", "body", "confirm_label", "destructive"}, path, "invalid confirm fields")
    msg(value["title"], f"{path}.title")
    msg(value["confirm_label"], f"{path}.confirm_label")
    if "body" in value:
        msg(value["body"], f"{path}.body")
    if "destructive" in value:
        boolean(value["destructive"], f"{path}.destructive")


def item(value: Any, path: str) -> None:
    need(isinstance(value, dict), path, "item must be an object")
    need({"id", "kind", "label"} <= set(value), path, "missing id, kind or label")
    kind = value["kind"]
    need(kind in FIELDS, f"{path}.kind", f"unknown kind {kind!r}")
    need(set(value) <= COMMON | FIELDS[kind], path, f"fields do not belong to {kind}")
    need(REQUIRED.get(kind, set()) <= set(value), path, f"missing fields for {kind}")
    identifier(value["id"], f"{path}.id")
    msg(value["label"], f"{path}.label")
    for name in ("subtitle", "a11y", "value", "unit"):
        if name in value:
            msg(value[name], f"{path}.{name}")
    if "bind" in value:
        bind(value["bind"], f"{path}.bind")
    if "icon" in value:
        identifier(value["icon"], f"{path}.icon")
    for name in ("enabled", "visible"):
        if name in value:
            cond(value[name], f"{path}.{name}")
    if kind == "action":
        if "confirm" in value:
            confirm(value["confirm"], f"{path}.confirm")
        if "stay_open" in value:
            boolean(value["stay_open"], f"{path}.stay_open")
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
        if "present" in value:
            need(value["present"] in {"inline", "picker"}, f"{path}.present", "unknown presentation")
    if kind in {"stepper", "slider"}:
        integer(value["min"], f"{path}.min")
        integer(value["max"], f"{path}.max")
        need(value["min"] <= value["max"], path, "min exceeds max")
        if "step" in value:
            integer(value["step"], f"{path}.step")
            need(value["step"] > 0, f"{path}.step", "must be positive")
    if kind == "text":
        if "purpose" in value:
            need(value["purpose"] in {"normal", "name", "number", "pin", "email", "url", "search"}, f"{path}.purpose", "unknown purpose")
        integer(value["max_chars"], f"{path}.max_chars")
        need(value["max_chars"] >= 1, f"{path}.max_chars", "must be positive")
        if "secret" in value:
            boolean(value["secret"], f"{path}.secret")
    if kind == "link":
        identifier(value["page"], f"{path}.page")
    if kind == "progress" and "indeterminate" in value:
        boolean(value["indeterminate"], f"{path}.indeterminate")
    if kind == "binding":
        identifier(value["context"], f"{path}.context")
        identifier(value["action"], f"{path}.action")
    if kind == "date_time" and "fields" in value:
        need(value["fields"] in {"date", "time", "date_time"}, f"{path}.fields", "unknown field set")
    if kind == "custom":
        identifier(value["renderer"], f"{path}.renderer")


def validate_schema_contract(schema: Any) -> None:
    """Prove the published schema and this dependency-free evaluator describe one surface."""
    path = str(SCHEMA)
    need(isinstance(schema, dict), path, "schema must be an object")
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    need(hashlib.sha256(canonical).hexdigest() == SCHEMA_DIGEST, path, "schema content drifted; update validator and negative controls together")
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
    identifier(document["id"], "$.id")
    identifier(document["root"], "$.root")
    need(isinstance(document["pages"], list) and document["pages"], "$.pages", "must be non-empty")
    page_ids, item_ids, links = set(), set(), []
    for pindex, page_value in enumerate(document["pages"]):
        path = f"$.pages[{pindex}]"
        need(isinstance(page_value, dict), path, "page must be an object")
        need({"id", "title", "sections"} <= set(page_value) <= {"id", "title", "sections", "tabs", "primary"}, path, "invalid page fields")
        identifier(page_value["id"], f"{path}.id")
        need(page_value["id"] not in page_ids, f"{path}.id", "duplicate page id")
        page_ids.add(page_value["id"])
        msg(page_value["title"], f"{path}.title")
        if "tabs" in page_value:
            tabs = page_value["tabs"]
            need(isinstance(tabs, list), f"{path}.tabs", "must be an array")
            for index, tab in enumerate(tabs):
                identifier(tab, f"{path}.tabs[{index}]")
            need(len(tabs) == len(set(tabs)), f"{path}.tabs", "must be unique")
        if "primary" in page_value:
            identifier(page_value["primary"], f"{path}.primary")
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
