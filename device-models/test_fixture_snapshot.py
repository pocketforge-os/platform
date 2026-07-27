#!/usr/bin/env python3
"""Regression tests for deterministic fixture dependency snapshots."""

from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import export_fixture_snapshot as snapshot
import test_fixture_contracts as contracts
import validate_fixture_contracts as fixture


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


class FixtureSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_temp = tempfile.TemporaryDirectory(
            prefix="pf-fixture-snapshot-source-"
        )
        self.output_temp = tempfile.TemporaryDirectory(
            prefix="pf-fixture-snapshot-output-"
        )
        self.addCleanup(self.source_temp.cleanup)
        self.addCleanup(self.output_temp.cleanup)
        self.root = Path(self.source_temp.name)
        self.output_root = Path(self.output_temp.name)
        self.base = contracts.raw_document(contracts.BASE_PATH)
        self.alias = contracts.raw_document(contracts.ALIAS_PATH)
        contracts.write_test_repository(
            self.root,
            self.base,
            self.alias,
        )
        git(self.root, "init", "--initial-branch=main")
        git(self.root, "config", "user.name", "Fixture Snapshot Test")
        git(self.root, "config", "user.email", "fixture@example.invalid")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "fixture contracts")
        self.initial_revision = git(self.root, "rev-parse", "HEAD")

    def commit(self, message: str) -> str:
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", message)
        return git(self.root, "rev-parse", "HEAD")

    def write_contracts(self, base: dict, alias: dict) -> None:
        contracts.write_test_repository(self.root, base, alias)

    def test_snapshot_is_canonical_deterministic_and_alias_deduplicated(
        self,
    ) -> None:
        first = snapshot.build_snapshot(self.root)
        second = snapshot.build_snapshot(self.root)
        first_bytes = snapshot._canonical_bytes(first)
        self.assertEqual(first_bytes, snapshot._canonical_bytes(second))
        self.assertEqual(self.initial_revision, first["source"]["revision"])
        self.assertEqual(
            ["trimui-smart-pro", "trimui-smart-pro-s"],
            [item["device_slug"] for item in first["contracts"]],
        )
        self.assertEqual(1, len(first["interfaces"]))
        self.assertEqual(
            {
                item["resolved_interface_sha256"]
                for item in first["contracts"]
            },
            {first["interfaces"][0]["sha256"]},
        )

        output = self.output_root / "snapshot.json"
        snapshot.write_snapshot(first, output, self.root)
        self.assertEqual(first_bytes, output.read_bytes())
        verified = snapshot.verify_snapshot(self.root, output)
        self.assertEqual(first, verified)

        output.write_bytes(b"old partial bytes")
        snapshot.write_snapshot(first, output, self.root)
        self.assertEqual(first_bytes, output.read_bytes())
        self.assertEqual(
            [],
            list(self.output_root.glob(".snapshot.json.*")),
        )

        output.write_bytes(b"known-good snapshot")
        with mock.patch.object(
            snapshot.os,
            "replace",
            side_effect=OSError("injected replacement failure"),
        ):
            with self.assertRaisesRegex(OSError, "injected replacement"):
                snapshot.write_snapshot(first, output, self.root)
        self.assertEqual(b"known-good snapshot", output.read_bytes())
        self.assertEqual(
            [],
            list(self.output_root.glob(".snapshot.json.*")),
        )

    def test_visual_only_commit_does_not_move_dependency_revision_or_bytes(
        self,
    ) -> None:
        before = snapshot._canonical_bytes(snapshot.build_snapshot(self.root))
        model = (
            self.root
            / "device-models/trimui-smart-pro/trimui-smart-pro.scad"
        )
        model.write_text("// visual-only change\n", encoding="utf-8")
        visual_revision = self.commit("visual model only")
        self.assertNotEqual(self.initial_revision, visual_revision)

        after = snapshot.build_snapshot(self.root)
        self.assertEqual(self.initial_revision, after["source"]["revision"])
        self.assertEqual(before, snapshot._canonical_bytes(after))

    def test_raw_contract_metadata_change_preserves_resolved_interface(
        self,
    ) -> None:
        before = snapshot.build_snapshot(self.root)
        changed = copy.deepcopy(self.base)
        changed["evidence"][0]["note"] = "Reworded fixture evidence."
        self.write_contracts(changed, self.alias)
        metadata_revision = self.commit("fixture evidence metadata")

        after = snapshot.build_snapshot(self.root)
        self.assertEqual(metadata_revision, after["source"]["revision"])
        self.assertEqual(before["interfaces"], after["interfaces"])
        self.assertNotEqual(
            before["contracts"][0]["raw_sha256"],
            after["contracts"][0]["raw_sha256"],
        )
        self.assertEqual(
            before["contracts"][0]["resolved_interface_sha256"],
            after["contracts"][0]["resolved_interface_sha256"],
        )

    def test_fit_change_moves_revision_and_shared_alias_interface(self) -> None:
        before = snapshot.build_snapshot(self.root)
        changed = copy.deepcopy(self.base)
        changed["interface_revision"] = 2
        changed["fixture_interface"]["contact_regions"][0]["shape"][
            "max_mm"
        ] += 0.01
        new_hash = contracts.update_full_hash(changed)
        contracts.make_unqualified(changed)
        alias = copy.deepcopy(self.alias)
        alias["expected_fixture_interface_sha256"] = new_hash
        contracts.make_unqualified(alias)
        self.write_contracts(changed, alias)
        fit_revision = self.commit("fit interface v2")

        after = snapshot.build_snapshot(self.root)
        self.assertEqual(fit_revision, after["source"]["revision"])
        self.assertNotEqual(
            before["interfaces"][0]["sha256"],
            after["interfaces"][0]["sha256"],
        )
        self.assertEqual(new_hash, after["interfaces"][0]["sha256"])
        self.assertEqual(2, after["interfaces"][0]["interface_revision"])
        self.assertEqual(
            {new_hash},
            {
                item["resolved_interface_sha256"]
                for item in after["contracts"]
            },
        )

    def test_dirty_source_and_repository_output_are_rejected(self) -> None:
        clean = snapshot.build_snapshot(self.root)
        with self.assertRaisesRegex(snapshot.SnapshotError, "outside"):
            snapshot.write_snapshot(
                clean,
                self.root / "generated-snapshot.json",
                self.root,
            )

        model = (
            self.root
            / "device-models/trimui-smart-pro/trimui-smart-pro.scad"
        )
        model.write_text("// uncommitted\n", encoding="utf-8")
        with self.assertRaisesRegex(snapshot.SnapshotError, "clean source"):
            snapshot.build_snapshot(self.root)

    def test_verifier_rejects_noncanonical_unknown_and_stale_snapshots(
        self,
    ) -> None:
        document = snapshot.build_snapshot(self.root)
        path = self.output_root / "snapshot.json"

        plain_document = json.loads(snapshot._canonical_bytes(document))
        path.write_text(
            json.dumps(plain_document, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(snapshot.SnapshotError, "not canonical"):
            snapshot.verify_snapshot(self.root, path)

        unknown = copy.deepcopy(document)
        unknown["surprise"] = True
        path.write_bytes(snapshot._canonical_bytes(unknown))
        with self.assertRaisesRegex(snapshot.SnapshotError, "unknown field"):
            snapshot.verify_snapshot(self.root, path)

        stale = copy.deepcopy(document)
        stale["contracts"][0]["raw_sha256"] = "0" * 64
        path.write_bytes(snapshot._canonical_bytes(stale))
        with self.assertRaisesRegex(
            snapshot.SnapshotError,
            "does not match source",
        ):
            snapshot.verify_snapshot(self.root, path)

    def test_duplicate_json_keys_and_unknown_interface_are_rejected(self) -> None:
        duplicate = self.output_root / "duplicate.json"
        duplicate.write_text(
            '{"schema":"one","schema":"two"}\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(fixture.ContractError, "duplicate"):
            fixture.load_json(duplicate)

        document = snapshot.build_snapshot(self.root)
        document["contracts"][0]["resolved_interface_sha256"] = "0" * 64
        with self.assertRaisesRegex(snapshot.SnapshotError, "unknown interface"):
            snapshot.validate_snapshot(document)

        malformed = snapshot.build_snapshot(self.root)
        malformed["interfaces"][0]["fixture_interface"]["surprise"] = True
        with self.assertRaisesRegex(snapshot.SnapshotError, "unknown field"):
            snapshot.validate_snapshot(malformed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
