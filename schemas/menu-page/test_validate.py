#!/usr/bin/env python3
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import Invalid, SCHEMA, validate, validate_schema_contract


class MenuPageValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).with_name("fixtures") / "system-menu.json"
        cls.valid = json.loads(fixture.read_text(encoding="utf-8"))

    def test_positive_control(self):
        validate(copy.deepcopy(self.valid))

    def test_unknown_item_field_is_rejected(self):
        invalid = copy.deepcopy(self.valid)
        invalid["pages"][0]["sections"][0]["items"][0]["bind"] = {"host": "wrong"}
        with self.assertRaises(Invalid):
            validate(invalid)

    def test_link_to_missing_page_is_rejected(self):
        invalid = copy.deepcopy(self.valid)
        invalid["pages"][0]["sections"][0]["items"][3]["page"] = "missing"
        with self.assertRaises(Invalid):
            validate(invalid)

    def test_schema_matches_the_semantic_validator(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validate_schema_contract(schema)

        invalid = copy.deepcopy(schema)
        invalid["$defs"]["toggle"]["allOf"][1]["required"] = []
        with self.assertRaises(Invalid):
            validate_schema_contract(invalid)

    def test_every_kind_and_recursive_condition_positive_control(self):
        items = [
            {"id": "action", "kind": "action", "label": {"text": "Action"}, "confirm": {"title": {"text": "Sure?"}, "confirm_label": {"text": "Yes"}, "destructive": True}, "stay_open": True},
            {"id": "toggle", "kind": "toggle", "label": {"text": "Toggle"}, "bind": {"host": "toggle"}, "visible": {"all": [{"when": "has_bt"}, {"unless": "app_running"}]}},
            {"id": "choice", "kind": "choice", "label": {"text": "Choice"}, "bind": {"option": "mode"}, "options": [{"value": "one", "label": {"text": "One"}, "detail": {"text": "First"}}], "present": "picker"},
            {"id": "stepper", "kind": "stepper", "label": {"text": "Stepper"}, "bind": {"host": "stepper"}, "min": 0, "max": 10, "step": 2, "unit": {"text": "%"}},
            {"id": "info", "kind": "info", "label": {"text": "Info"}, "value": {"text": "Value"}},
            {"id": "slider", "kind": "slider", "label": {"text": "Slider"}, "bind": {"pref": "brightness"}, "min": 0, "max": 100, "step": 5},
            {"id": "text", "kind": "text", "label": {"text": "Text"}, "bind": {"host": "text"}, "purpose": "search", "max_chars": 40, "secret": False},
            {"id": "link", "kind": "link", "label": {"text": "Link"}, "page": "child"},
            {"id": "progress", "kind": "progress", "label": {"text": "Progress"}, "bind": {"host": "progress"}, "indeterminate": True},
            {"id": "binding", "kind": "binding", "label": {"text": "Binding"}, "context": "shell", "action": "Move.Up"},
            {"id": "date", "kind": "date_time", "label": {"text": "Date"}, "bind": {"host": "date"}, "fields": "date_time"},
            {"id": "custom", "kind": "custom", "label": {"text": "Custom"}, "renderer": "system.renderer"},
        ]
        document = {
            "format": "pocketforge.menu/1",
            "id": "all-kinds",
            "root": "root",
            "pages": [
                {"id": "root", "title": {"id": "root-title", "args": {"name": "Root"}}, "tabs": ["root", "child"], "sections": [{"items": items}]},
                {"id": "child", "title": {"text": "Child"}, "tabs": ["root", "child"], "sections": []},
            ],
        }
        validate(document)

    def test_published_schema_omission_regressions_are_rejected(self):
        base = copy.deepcopy(self.valid)

        def replace_first(kind, **fields):
            document = copy.deepcopy(base)
            row = {"id": "row", "kind": kind, "label": {"text": "Row"}}
            row.update(fields)
            document["pages"][0]["sections"][0]["items"][0] = row
            document["pages"][0]["primary"] = "row"
            return document, row

        cases = []
        document = copy.deepcopy(base); document["id"] = "bad id"; cases.append(("document id", document))
        document = copy.deepcopy(base); document["pages"][0]["id"] = "bad id"; cases.append(("page id", document))
        document = copy.deepcopy(base); document["pages"][0]["title"] = {"id": "bad id"}; cases.append(("message id", document))
        document = copy.deepcopy(base); document["pages"][0]["tabs"] = ["system", "system"]; cases.append(("tabs unique", document))
        document = copy.deepcopy(base); document["pages"][0]["sections"][0]["items"][0]["icon"] = "bad icon"; cases.append(("icon id", document))
        document = copy.deepcopy(base); document["pages"][0]["sections"][0]["items"][0]["visible"] = {"all": "bad"}; cases.append(("recursive condition", document))
        document = copy.deepcopy(base); document["pages"][0]["sections"][0]["items"][0]["stay_open"] = "yes"; cases.append(("action boolean", document))
        document = copy.deepcopy(base); document["pages"][0]["sections"][0]["items"][0]["confirm"] = {"title": {"text": "Sure?"}}; cases.append(("confirm fields", document))
        document = copy.deepcopy(base); document["pages"][0]["sections"][0]["items"][2]["bind"] = {"host": "bad target"}; cases.append(("binding id", document))

        document, row = replace_first("choice", bind={"host": "choice"}, options=[{"value": "one", "label": {"text": "One"}}], present="grid"); cases.append(("choice present", document))
        document, row = replace_first("stepper", bind={"host": "step"}, min=0, max=10, step=True); cases.append(("stepper bool integer", document))
        document, row = replace_first("slider", bind={"host": "slide"}, min=False, max=10); cases.append(("slider bool integer", document))
        document, row = replace_first("text", bind={"host": "text"}, purpose="emoji", max_chars=10); cases.append(("text purpose", document))
        document, row = replace_first("text", bind={"host": "text"}, max_chars=True); cases.append(("text max chars", document))
        document, row = replace_first("progress", bind={"host": "progress"}, indeterminate="yes"); cases.append(("progress boolean", document))
        document, row = replace_first("binding", context="bad context", action="Move.Up"); cases.append(("binding context", document))
        document, row = replace_first("date_time", bind={"host": "date"}, fields="week"); cases.append(("date fields", document))
        document, row = replace_first("custom", renderer="bad renderer"); cases.append(("custom renderer", document))

        for name, document in cases:
            with self.subTest(name=name), self.assertRaises(Invalid):
                validate(document)


if __name__ == "__main__":
    unittest.main()
