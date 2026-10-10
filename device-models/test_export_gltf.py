#!/usr/bin/env python3
"""Hermetic regression tests for the glTF export chain (tsp-h5ed.46.2).

Every failure path is exercised next to its positive control in the same test:
a fake repository root (one tiny .scad, one descriptor, one exported glb built
by the exporter's own stdlib writer) is checked clean first, then mutated.
No OpenSCAD is needed. The Khronos validator tests need the pinned binary
(``GLTF_VALIDATOR=<path>``); CI sets ``PF_REQUIRE_GLTF_VALIDATOR=1`` so a
missing binary fails there instead of skipping.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import export_gltf  # noqa: E402
import gltf_validate  # noqa: E402


def load_drift_module():
    spec = importlib.util.spec_from_file_location(
        "check_skin_drift", HERE / "check-skin-drift.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


drift = load_drift_module()


def temp_root(testcase: unittest.TestCase, prefix: str) -> Path:
    """A fresh temp dir removed bottom-up after the test (no recursive rm)."""
    root = Path(tempfile.mkdtemp(prefix=prefix))

    def remove() -> None:
        for directory, subdirs, files in os.walk(root, topdown=False):
            for name in files:
                os.unlink(os.path.join(directory, name))
            for name in subdirs:
                os.rmdir(os.path.join(directory, name))
        os.rmdir(root)

    testcase.addCleanup(remove)
    return root

FAKE_SCAD = """\
PART = "assembly";
CONTROL_IDS = [
    "btn_a",
    "btn_b"
];
shell_rear_color = [0.125, 0.135, 0.145, 1.0];
control_color = [0.055, 0.060, 0.068, 1.0];
glass_color = [0.012, 0.017, 0.027, 1.0];
"""

FAKE_DESCRIPTOR = """\
[identity]
id = "fake"

[[screens]]
role          = "primary"
present       = "portrait"
rotation      = "cw90"
render_canvas = { w = 1280, h = 720 }

[[inputs]]
id = "south"
kind = "button"
ev_type = "EV_KEY"
code = "BTN_A"
skin_part = "btn_a"

[[inputs]]
id = "east"
kind = "button"
ev_type = "EV_KEY"
code = "BTN_B"
skin_part = "btn_b"

[skin]
body = "skins/fake/body.png"

[skin.parts]
btn_a = { x = 1, y = 1, w = 10, h = 10 }
btn_b = { x = 20, y = 1, w = 10, h = 10 }
"""


def box(x0, y0, z0, x1, y1, z1):
    """Closed axis-aligned box as 12 outward-facing triangles (mm)."""
    p = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    quads = [
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (2, 3, 7, 6), (1, 2, 6, 5), (3, 0, 4, 7),
    ]
    tris = []
    for a, b, c, d in quads:
        tris.append((p[a], p[b], p[c]))
        tris.append((p[a], p[c], p[d]))
    return tris


def fake_parts(control_ids=("btn_a", "btn_b")):
    controls = {
        cid: box(5 + 12 * i, 5, 10, 13 + 12 * i, 13, 12)
        for i, cid in enumerate(control_ids)
    }
    return {
        "body": box(0, 0, 0, 60, 30, 10),
        "controls": controls,
        "screen_bbox": ((20.0, 10.0, 10.0), (50.0, 25.0, 10.5)),
    }


class FakeRepo:
    """A throwaway repository root holding one modelled device."""

    def __init__(self, testcase: unittest.TestCase, *, descriptor: bool = True):
        self.root = temp_root(testcase, "pf-gltf-test-")
        (self.root / "device-models" / "fake-dev").mkdir(parents=True)
        (self.root / "devices" / "fake").mkdir(parents=True)
        (self.root / "skins" / "fake").mkdir(parents=True)
        shutil.copyfile(
            HERE / "export_gltf.py", self.root / "device-models" / "export_gltf.py"
        )
        self.scad.write_text(FAKE_SCAD, encoding="utf-8")
        if descriptor:
            self.descriptor.write_text(FAKE_DESCRIPTOR, encoding="utf-8")
        self.model = export_gltf.Model(
            slug="fake-dev",
            skin="fake",
            descriptor="devices/fake/capabilities.toml" if descriptor else None,
            panel_rotation_deg=None if descriptor else 0,
        )

    @property
    def scad(self) -> Path:
        return self.root / "device-models" / "fake-dev" / "fake-dev.scad"

    @property
    def descriptor(self) -> Path:
        return self.root / "devices" / "fake" / "capabilities.toml"

    @property
    def glb(self) -> Path:
        return self.root / "skins" / "fake" / "model.glb"

    @property
    def meta(self) -> Path:
        return self.root / "skins" / "fake" / "model-glb.json"

    def export(self, parts=None) -> None:
        resolved = export_gltf.resolve_model(self.root, self.model)
        export_gltf.write_outputs(
            self.root, resolved, parts or fake_parts(), openscad_version="test"
        )

    def rewrite_glb(self, mutate) -> None:
        """Apply mutate(doc) to the committed glb and re-record its sha, so the
        failure under test is the mutation itself and not a stale hash."""
        doc, binary = export_gltf.read_glb(self.glb.read_bytes())
        mutate(doc)
        self.glb.write_bytes(export_gltf.pack_glb(doc, binary))
        meta = json.loads(self.meta.read_text(encoding="utf-8"))
        meta["glb_sha256"] = export_gltf.sha256_file(self.glb)
        meta["nodes"] = [node.get("name") for node in doc["nodes"]]
        self.meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def add_node(doc, name):
    doc["nodes"].append({"name": name, "mesh": doc["nodes"][1]["mesh"]})
    doc["nodes"][0].setdefault("children", []).append(len(doc["nodes"]) - 1)


def remove_node(doc, name):
    index = [n.get("name") for n in doc["nodes"]].index(name)
    for node in doc["nodes"]:
        children = [c for c in node.get("children", []) if c != index]
        node["children"] = [c - 1 if c > index else c for c in children]
        if not node["children"]:
            del node["children"]
    del doc["nodes"][index]
    doc["scenes"][0]["nodes"] = [0]


class DriftGateTests(unittest.TestCase):
    def failures(self, repo: FakeRepo) -> list[str]:
        return drift.check_glb(repo.meta, root=repo.root)

    def test_extra_node_fails_drift(self):
        repo = FakeRepo(self)
        repo.export()
        self.assertEqual(self.failures(repo), [], "positive control")
        repo.rewrite_glb(lambda doc: add_node(doc, "btn_hostile"))
        failures = self.failures(repo)
        self.assertTrue(
            any("btn_hostile" in f and "control" in f for f in failures), failures
        )

    def test_missing_node_fails_drift(self):
        repo = FakeRepo(self)
        repo.export()
        self.assertEqual(self.failures(repo), [], "positive control")
        repo.rewrite_glb(lambda doc: remove_node(doc, "btn_b"))
        failures = self.failures(repo)
        self.assertTrue(
            any("btn_b" in f and "control" in f for f in failures), failures
        )

    def test_descriptor_part_added_fails_drift(self):
        repo = FakeRepo(self)
        repo.export()
        self.assertEqual(self.failures(repo), [], "positive control")
        repo.descriptor.write_text(
            FAKE_DESCRIPTOR + 'btn_c = { x = 40, y = 1, w = 10, h = 10 }\n',
            encoding="utf-8",
        )
        failures = self.failures(repo)
        self.assertTrue(any("btn_c" in f for f in failures), failures)

    def test_scad_edit_without_reexport_fails_drift(self):
        repo = FakeRepo(self)
        repo.export()
        self.assertEqual(self.failures(repo), [], "positive control")
        repo.scad.write_text(FAKE_SCAD + "// edit\n", encoding="utf-8")
        failures = self.failures(repo)
        self.assertTrue(any("source_sha256" in f for f in failures), failures)

    def test_glb_byte_edit_fails_drift_and_check(self):
        repo = FakeRepo(self)
        repo.export()
        self.assertEqual(self.failures(repo), [], "positive control")
        self.assertEqual(export_gltf.check_all(repo.root)[0], [], "positive control")
        data = bytearray(repo.glb.read_bytes())
        data[-1] ^= 0x01
        repo.glb.write_bytes(bytes(data))
        self.assertTrue(any("glb_sha256" in f for f in self.failures(repo)))
        self.assertTrue(any("glb_sha256" in f for f in export_gltf.check_all(repo.root)[0]))

    def test_panel_rotation_drift(self):
        repo = FakeRepo(self)
        repo.export()
        self.assertEqual(self.failures(repo), [], "positive control")
        doc, _ = export_gltf.read_glb(repo.glb.read_bytes())
        screen = next(n for n in doc["nodes"] if n["name"] == "screen_main")
        self.assertEqual(screen["extras"]["panel_rotation_deg"], 90)

        def rotate(doc):
            node = next(n for n in doc["nodes"] if n["name"] == "screen_main")
            node["extras"]["panel_rotation_deg"] = 0

        repo.rewrite_glb(rotate)
        failures = self.failures(repo)
        self.assertTrue(any("panel_rotation_deg" in f for f in failures), failures)

    def test_screen_uv_required(self):
        repo = FakeRepo(self)
        repo.export()
        self.assertEqual(self.failures(repo), [], "positive control")

        def strip_uv(doc):
            node = next(n for n in doc["nodes"] if n["name"] == "screen_main")
            del doc["meshes"][node["mesh"]]["primitives"][0]["attributes"]["TEXCOORD_0"]

        repo.rewrite_glb(strip_uv)
        failures = self.failures(repo)
        self.assertTrue(any("TEXCOORD_0" in f for f in failures), failures)

    def test_rendered_skin_without_glb_fails_gate(self):
        repo = FakeRepo(self)
        repo.export()
        self.assertEqual(drift.glb_coverage_failures(repo.root), [], "positive control")
        (repo.root / "skins" / "other").mkdir()
        (repo.root / "skins" / "other" / "model-render.json").write_text("{}\n")
        failures = drift.glb_coverage_failures(repo.root)
        self.assertTrue(any("skins/other" in f for f in failures), failures)

    def test_model_only_device(self):
        repo = FakeRepo(self, descriptor=False)
        repo.export()
        self.assertEqual(self.failures(repo), [], "positive control")
        # A descriptor appearing later must be bound, not silently ignored.
        repo.descriptor.write_text(FAKE_DESCRIPTOR, encoding="utf-8")
        failures = self.failures(repo)
        self.assertTrue(any("descriptor" in f for f in failures), failures)


class ExporterTests(unittest.TestCase):
    def test_refuses_part_name_mismatch(self):
        repo = FakeRepo(self)
        export_gltf.resolve_model(repo.root, repo.model)  # positive control
        repo.scad.write_text(
            FAKE_SCAD.replace('"btn_b"', '"btn_b",\n    "btn_extra"'), encoding="utf-8"
        )
        with self.assertRaisesRegex(export_gltf.ExportError, "btn_extra"):
            export_gltf.resolve_model(repo.root, repo.model)
        repo.scad.write_text(FAKE_SCAD.replace(',\n    "btn_b"', ""), encoding="utf-8")
        with self.assertRaisesRegex(export_gltf.ExportError, "btn_b"):
            export_gltf.resolve_model(repo.root, repo.model)

    def test_refuses_parts_missing_a_control_mesh(self):
        repo = FakeRepo(self)
        resolved = export_gltf.resolve_model(repo.root, repo.model)
        export_gltf.build_document(resolved, fake_parts(), openscad_version="t")
        with self.assertRaisesRegex(export_gltf.ExportError, "btn_b"):
            export_gltf.build_document(
                resolved, fake_parts(("btn_a",)), openscad_version="t"
            )

    def test_triangle_budget(self):
        repo = FakeRepo(self)
        repo.export()
        failures, counts = export_gltf.check_all(repo.root)
        self.assertEqual(failures, [], "positive control")
        self.assertEqual(counts["fake"], 12 * 3 + 2)
        failures, _ = export_gltf.check_all(repo.root, budget=37)
        self.assertTrue(any("budget" in f for f in failures), failures)

    def test_deterministic_bytes(self):
        repo = FakeRepo(self)
        resolved = export_gltf.resolve_model(repo.root, repo.model)
        first = export_gltf.build_document(resolved, fake_parts(), openscad_version="t")
        second = export_gltf.build_document(resolved, fake_parts(), openscad_version="t")
        self.assertEqual(first, second)

    def test_normals_unit_and_degenerates_dropped(self):
        tris = box(0, 0, 0, 1, 1, 1) + [((0, 0, 0), (1, 0, 0), (2, 0, 0))]
        mesh = export_gltf.smooth_mesh(tris, origin=(0.0, 0.0, 0.0))
        self.assertEqual(len(mesh.indices), 12 * 3)
        for i in range(0, len(mesh.normals), 3):
            x, y, z = mesh.normals[i:i + 3]
            self.assertAlmostEqual(x * x + y * y + z * z, 1.0, places=5)
        # A cube's 90-degree edges exceed the crease angle: 24 split vertices.
        self.assertEqual(len(mesh.positions) // 3, 24)

    def test_screen_quad_uv_and_extras(self):
        repo = FakeRepo(self)
        repo.export()
        doc, binary = export_gltf.read_glb(repo.glb.read_bytes())
        summary = export_gltf.summarize(doc, binary)
        screen = summary.screens["screen_main"]
        self.assertEqual(screen["uv_min"], [0.0, 0.0])
        self.assertEqual(screen["uv_max"], [1.0, 1.0])
        self.assertEqual(screen["panel_rotation_deg"], 90)

    def test_read_glb_rejects_garbage(self):
        with self.assertRaises(export_gltf.GlbError):
            export_gltf.read_glb(b"not a glb at all")
        repo = FakeRepo(self)
        repo.export()
        export_gltf.read_glb(repo.glb.read_bytes())  # positive control


class ValidatorTests(unittest.TestCase):
    def validator(self) -> Path:
        path = os.environ.get("GLTF_VALIDATOR")
        if not path:
            if os.environ.get("PF_REQUIRE_GLTF_VALIDATOR") == "1":
                self.fail("PF_REQUIRE_GLTF_VALIDATOR=1 but GLTF_VALIDATOR is unset")
            self.skipTest("GLTF_VALIDATOR unset (CI requires it)")
        return Path(path)

    def test_valid_passes_invalid_fails(self):
        validator = self.validator()
        repo = FakeRepo(self)
        repo.export()
        ok, report = gltf_validate.validate(validator, repo.glb)
        self.assertTrue(ok, report)
        # A structurally invalid glb: an accessor reads past its buffer view.
        doc, binary = export_gltf.read_glb(repo.glb.read_bytes())
        broken = copy.deepcopy(doc)
        broken["accessors"][0]["count"] += 1000
        bad = repo.root / "bad.glb"
        bad.write_bytes(export_gltf.pack_glb(broken, binary))
        ok, report = gltf_validate.validate(validator, bad)
        self.assertFalse(ok, report)
        # Bytes that are not a glb at all.
        garbage = repo.root / "garbage.glb"
        garbage.write_bytes(b"glTF" + b"\x00" * 3)
        ok, report = gltf_validate.validate(validator, garbage)
        self.assertFalse(ok, report)

    def test_pinned_archive_checksum(self):
        archive = temp_root(self, "pf-gltf-fetch-") / "archive.tar.xz"
        archive.write_bytes(b"tampered")
        with self.assertRaisesRegex(gltf_validate.ValidatorError, "sha256"):
            gltf_validate.verify_archive(archive)


if __name__ == "__main__":
    unittest.main(verbosity=2)
