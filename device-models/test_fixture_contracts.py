#!/usr/bin/env python3
"""Regression tests for the PocketForge fixture-contract boundary."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import validate_fixture_contracts as fixture


ROOT = Path(__file__).resolve().parent.parent
BASE_PATH = ROOT / "device-models/trimui-smart-pro/fixture-contract.json"
ALIAS_PATH = ROOT / "device-models/trimui-smart-pro-s/fixture-contract.json"
BRICK_PATH = ROOT / "device-models/trimui-brick/fixture-contract.json"
X55_PATH = ROOT / "device-models/powkiddy-x55/fixture-contract.json"
SCHEMA_PATH = ROOT / "schemas/device-fixture-contract.schema.json"


def raw_document(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def update_full_hash(document: dict) -> str:
    digest = fixture.interface_hash(document)
    document["fixture_interface_sha256"] = digest
    if document["qualification"]["status"] != "unqualified":
        document["qualification"]["qualified_fixture_interface_sha256"] = digest
    return digest


def make_unqualified(document: dict) -> None:
    qualification = document["qualification"]
    qualification["status"] = "unqualified"
    qualification["qualified_fixture_interface_sha256"] = None
    qualification["accepted_on"] = None
    qualification["acceptance_ref"] = None
    qualification["interface_refs"] = []
    qualification["holder_evidence"] = None


def write_test_repository(
    root: Path,
    base: dict,
    alias: dict,
) -> None:
    (root / "device-models/trimui-smart-pro").mkdir(parents=True, exist_ok=True)
    (root / "device-models/trimui-smart-pro-s").mkdir(parents=True, exist_ok=True)
    (root / "schemas").mkdir(parents=True, exist_ok=True)
    (root / "device-models/trimui-smart-pro/trimui-smart-pro.scad").write_text(
        "// test model\n", encoding="utf-8"
    )
    (root / "device-models/trimui-smart-pro-s/trimui-smart-pro-s.scad").write_text(
        "// test model\n", encoding="utf-8"
    )
    (root / "device-models/trimui-smart-pro/fixture-contract.json").write_text(
        json.dumps(base, indent=2) + "\n", encoding="utf-8"
    )
    (root / "device-models/trimui-smart-pro-s/fixture-contract.json").write_text(
        json.dumps(alias, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(SCHEMA_PATH, root / "schemas/device-fixture-contract.schema.json")


class FixtureContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = raw_document(BASE_PATH)
        self.alias = raw_document(ALIAS_PATH)
        self.brick = raw_document(BRICK_PATH)
        self.x55 = raw_document(X55_PATH)

    def test_x55_contract_records_provisional_local_depths(self) -> None:
        resolved = fixture.ContractRepository(ROOT).resolve(X55_PATH)
        interface = self.x55["fixture_interface"]
        self.assertEqual("unqualified", resolved.qualification["status"])
        self.assertEqual([210, 88.76], interface["envelope"]["xy_bounds_mm"]["max"])
        self.assertFalse(
            interface["envelope"]["overall_depth"]["manufacturing_ready"]
        )
        self.assertEqual(
            {
                "bottom_contact_depth": 14.4,
                "side_contact_depth": 14.6,
                "top_contact_depth": 13.8,
            },
            {row["id"]: row["nominal_mm"] for row in interface["local_depths"]},
        )
        self.assertTrue(
            all(not row["manufacturing_ready"] for row in interface["local_depths"])
        )
        self.assertEqual(
            {
                "bottom_left",
                "bottom_right",
                "left_datum",
                "right_datum",
                "top_left",
                "top_right",
            },
            {row["id"] for row in interface["contact_regions"]},
        )

    def test_brick_contract_is_distinct_and_stays_unqualified(self) -> None:
        resolved = fixture.ContractRepository(ROOT).resolve(BRICK_PATH)
        interface = self.brick["fixture_interface"]
        self.assertEqual("unqualified", resolved.qualification["status"])
        self.assertEqual(
            [72.8, 110.75],
            interface["envelope"]["xy_bounds_mm"]["max"],
        )
        self.assertEqual(
            {
                "thick_lower_shell": 20,
                "thin_upper_shell": 12,
            },
            {
                item["id"]: item["nominal_mm"]
                for item in interface["local_depths"]
            },
        )
        self.assertEqual(
            {
                "bottom_left_support",
                "bottom_right_support",
                "left_lower_datum",
                "right_lower_datum",
                "top_left_retainer",
            },
            {item["id"] for item in interface["contact_regions"]},
        )
        self.assertNotEqual(
            resolved.interface_hash,
            fixture.ContractRepository(ROOT).resolve(BASE_PATH).interface_hash,
        )

    def test_repository_contracts_validate_and_checker_is_read_only(self) -> None:
        paths = sorted(ROOT.glob("device-models/*/fixture-contract.json"))
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        }
        contracts = fixture.ContractRepository(ROOT).validate_all()
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        }
        self.assertEqual(4, len(contracts))
        self.assertEqual(before, after)
        by_slug = {
            contract.document["device"]["slug"]: contract
            for contract in contracts
        }
        self.assertEqual(
            by_slug["trimui-smart-pro"].interface_hash,
            by_slug["trimui-smart-pro-s"].interface_hash,
        )
        self.assertNotEqual(
            by_slug["trimui-brick"].interface_hash,
            by_slug["trimui-smart-pro"].interface_hash,
        )
        self.assertNotEqual(
            by_slug["powkiddy-x55"].interface_hash,
            by_slug["trimui-smart-pro"].interface_hash,
        )

    def test_hash_ignores_json_representation_and_semantic_list_order(self) -> None:
        changed = copy.deepcopy(self.base)
        changed["interface_revision"] = Decimal("1.000")
        changed["fixture_interface"]["envelope"]["xy_bounds_mm"]["min"][0] = Decimal("-0.000")
        changed["fixture_interface"]["envelope"]["xy_bounds_mm"]["max"][0] = Decimal("188.3500")
        interface = changed["fixture_interface"]
        for key in (
            "local_depths",
            "contact_regions",
            "keepouts",
            "access_regions",
            "datums",
            "clearance_requirements",
        ):
            interface[key].reverse()
        for depth in interface["local_depths"]:
            depth["region_refs"].reverse()
        for contact in interface["contact_regions"]:
            contact["contact_modes"].reverse()
        for clearance in interface["clearance_requirements"]:
            clearance["protects"].reverse()
        changed = dict(reversed(list(changed.items())))
        self.assertEqual(fixture.interface_hash(self.base), fixture.interface_hash(changed))

    def test_non_interface_metadata_does_not_change_hash(self) -> None:
        changed = copy.deepcopy(self.base)
        changed["device"]["product"] = "Cosmetic product-name edit"
        changed["visual_model"]["path"] = "different-visual-source.scad"
        changed["evidence"][0]["note"] = "Reworded provenance without moving geometry."
        changed["qualification"]["scope"] = "Reworded acceptance scope."
        changed["unresolved_measurements"][0]["needed"] = "Reworded measurement request."
        self.assertEqual(fixture.interface_hash(self.base), fixture.interface_hash(changed))

    def test_fit_coordinate_mutation_changes_hash_and_stale_record_fails(self) -> None:
        changed = copy.deepcopy(self.base)
        changed["fixture_interface"]["contact_regions"][0]["shape"]["max_mm"] += 0.001
        self.assertNotEqual(fixture.interface_hash(self.base), fixture.interface_hash(changed))
        repository = fixture.ContractRepository(ROOT)
        with self.assertRaisesRegex(fixture.ContractError, "stale interface hash"):
            repository._validate_full(BASE_PATH, changed)

    def test_unknown_missing_duplicate_and_bad_reference_are_rejected(self) -> None:
        repository = fixture.ContractRepository(ROOT)

        unknown = copy.deepcopy(self.base)
        unknown["surprise"] = True
        with self.assertRaisesRegex(fixture.ContractError, "unknown field"):
            repository._validate_full(BASE_PATH, unknown)

        missing = copy.deepcopy(self.base)
        del missing["coordinate_system"]
        with self.assertRaisesRegex(fixture.ContractError, "missing required field"):
            repository._validate_full(BASE_PATH, missing)

        duplicate = copy.deepcopy(self.base)
        duplicate["fixture_interface"]["contact_regions"][1]["id"] = "bottom_left"
        update_full_hash(duplicate)
        with self.assertRaisesRegex(fixture.ContractError, "duplicate interface id"):
            repository._validate_full(BASE_PATH, duplicate)

        bad_ref = copy.deepcopy(self.base)
        bad_ref["fixture_interface"]["contact_regions"][0]["local_depth_ref"] = "missing"
        update_full_hash(bad_ref)
        with self.assertRaisesRegex(fixture.ContractError, "unknown local depth"):
            repository._validate_full(BASE_PATH, bad_ref)

    def test_invalid_ranges_and_nonfinite_json_are_rejected(self) -> None:
        repository = fixture.ContractRepository(ROOT)
        changed = copy.deepcopy(self.base)
        shape = changed["fixture_interface"]["contact_regions"][0]["shape"]
        shape["max_mm"] = shape["min_mm"]
        update_full_hash(changed)
        with self.assertRaisesRegex(fixture.ContractError, "min_mm must be less"):
            repository._validate_full(BASE_PATH, changed)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"value": NaN}\n', encoding="utf-8")
            with self.assertRaisesRegex(fixture.ContractError, "non-finite"):
                fixture.load_json(path)

    def test_alias_hash_mismatch_and_fit_delta_are_rejected(self) -> None:
        repository = fixture.ContractRepository(ROOT)
        mismatch = copy.deepcopy(self.alias)
        mismatch["expected_fixture_interface_sha256"] = "f" * 64
        with self.assertRaisesRegex(fixture.ContractError, "does not match target"):
            repository._validate_alias(ALIAS_PATH, mismatch, (ALIAS_PATH.resolve(),))

        fit_delta = copy.deepcopy(self.alias)
        fit_delta["relationship"]["fit_relevant_deltas"] = ["different rear shell"]
        with self.assertRaisesRegex(fixture.ContractError, "cannot carry fit-relevant deltas"):
            repository._validate_alias(ALIAS_PATH, fit_delta, (ALIAS_PATH.resolve(),))

    def test_alias_cycle_and_resolved_path_escape_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_root = root / "device-models"
            for slug, target in (("alpha", "beta"), ("beta", "alpha")):
                package = model_root / slug
                package.mkdir(parents=True)
                (package / f"{slug}.scad").write_text("// test\n", encoding="utf-8")
                document = copy.deepcopy(self.alias)
                document["device"]["slug"] = slug
                document["device"]["platform_device_ids"] = [f"{slug}-soc"]
                document["device"]["product"] = slug
                document["device"]["model_number"] = slug.upper()
                document["device"]["hardware_revisions"] = [slug.upper()]
                document["visual_model"]["path"] = f"{slug}.scad"
                document["extends"] = f"../{target}/fixture-contract.json"
                (package / "fixture-contract.json").write_text(
                    json.dumps(document, indent=2) + "\n", encoding="utf-8"
                )
            with self.assertRaisesRegex(fixture.ContractError, "alias cycle"):
                fixture.ContractRepository(root).resolve(
                    model_root / "alpha/fixture-contract.json"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "device-models/alias"
            outside = root / "outside"
            package.mkdir(parents=True)
            outside.mkdir()
            (package / "alias.scad").write_text("// test\n", encoding="utf-8")
            os.symlink(outside, root / "device-models/escape")
            document = copy.deepcopy(self.alias)
            document["device"]["slug"] = "alias"
            document["device"]["platform_device_ids"] = ["alias-soc"]
            document["visual_model"]["path"] = "alias.scad"
            document["extends"] = "../escape/fixture-contract.json"
            path = package / "fixture-contract.json"
            path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(fixture.ContractError, "escapes device-models"):
                fixture.ContractRepository(root).resolve(path)

    def test_baseline_comparison_requires_revision_bump(self) -> None:
        with tempfile.TemporaryDirectory() as old_tmp, tempfile.TemporaryDirectory() as new_tmp:
            old_root = Path(old_tmp)
            new_root = Path(new_tmp)
            write_test_repository(old_root, self.base, self.alias)

            changed = copy.deepcopy(self.base)
            changed["fixture_interface"]["contact_regions"][0]["shape"]["max_mm"] += 0.01
            new_hash = update_full_hash(changed)
            alias = copy.deepcopy(self.alias)
            alias["expected_fixture_interface_sha256"] = new_hash
            alias["qualification"]["qualified_fixture_interface_sha256"] = new_hash
            write_test_repository(new_root, changed, alias)

            with self.assertRaisesRegex(fixture.ContractError, "without increasing revision"):
                fixture.compare_contract_roots(
                    fixture.ContractRepository(new_root),
                    fixture.ContractRepository(old_root),
                )

    def test_changed_qualified_interface_must_be_invalidated_or_reaccepted(self) -> None:
        with tempfile.TemporaryDirectory() as old_tmp, tempfile.TemporaryDirectory() as new_tmp:
            old_root = Path(old_tmp)
            new_root = Path(new_tmp)
            write_test_repository(old_root, self.base, self.alias)

            changed = copy.deepcopy(self.base)
            changed["interface_revision"] = 2
            changed["fixture_interface"]["contact_regions"][0]["shape"]["max_mm"] += 0.01
            new_hash = update_full_hash(changed)
            alias = copy.deepcopy(self.alias)
            alias["expected_fixture_interface_sha256"] = new_hash
            alias["qualification"]["qualified_fixture_interface_sha256"] = new_hash
            write_test_repository(new_root, changed, alias)

            with self.assertRaisesRegex(
                fixture.ContractError,
                "without invalidating qualification",
            ):
                fixture.compare_contract_roots(
                    fixture.ContractRepository(new_root),
                    fixture.ContractRepository(old_root),
                )

            changed["qualification"]["accepted_on"] = "2026-07-22"
            alias["qualification"]["accepted_on"] = "2026-07-22"
            write_test_repository(new_root, changed, alias)
            with self.assertRaisesRegex(
                fixture.ContractError,
                "without invalidating qualification",
            ):
                fixture.compare_contract_roots(
                    fixture.ContractRepository(new_root),
                    fixture.ContractRepository(old_root),
                )

            make_unqualified(changed)
            make_unqualified(alias)
            write_test_repository(new_root, changed, alias)
            messages = fixture.compare_contract_roots(
                fixture.ContractRepository(new_root),
                fixture.ContractRepository(old_root),
            )
            self.assertEqual(2, len(messages))

    def test_unchanged_hash_cannot_receive_meaningless_revision_bump(self) -> None:
        with tempfile.TemporaryDirectory() as old_tmp, tempfile.TemporaryDirectory() as new_tmp:
            old_root = Path(old_tmp)
            new_root = Path(new_tmp)
            write_test_repository(old_root, self.base, self.alias)
            changed = copy.deepcopy(self.base)
            changed["interface_revision"] = 2
            update_full_hash(changed)
            alias = copy.deepcopy(self.alias)
            alias["expected_fixture_interface_sha256"] = changed["fixture_interface_sha256"]
            alias["qualification"]["qualified_fixture_interface_sha256"] = changed[
                "fixture_interface_sha256"
            ]
            write_test_repository(new_root, changed, alias)
            with self.assertRaisesRegex(
                fixture.ContractError,
                "hash is unchanged but revision moved",
            ):
                fixture.compare_contract_roots(
                    fixture.ContractRepository(new_root),
                    fixture.ContractRepository(old_root),
                )

    def test_baseline_contract_cannot_silently_disappear(self) -> None:
        with tempfile.TemporaryDirectory() as old_tmp, tempfile.TemporaryDirectory() as new_tmp:
            old_root = Path(old_tmp)
            new_root = Path(new_tmp)
            write_test_repository(old_root, self.base, self.alias)
            write_test_repository(new_root, self.base, self.alias)
            (new_root / "device-models/trimui-smart-pro-s/fixture-contract.json").unlink()
            with self.assertRaisesRegex(fixture.ContractError, "contract.*disappeared"):
                fixture.compare_contract_roots(
                    fixture.ContractRepository(new_root),
                    fixture.ContractRepository(old_root),
                )

    def test_reference_json_schema_accepts_contracts_and_rejects_unknown_fields(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("optional jsonschema package is unavailable")
        schema = raw_document(SCHEMA_PATH)
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(self.base)
        validator.validate(self.alias)
        bad = copy.deepcopy(self.base)
        bad["surprise"] = True
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
