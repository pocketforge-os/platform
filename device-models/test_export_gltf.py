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
import render_glb_views  # noqa: E402  (numpy/Pillow only needed to render)


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


def write_fake_views(repo: FakeRepo, tag: str = "v1") -> None:
    """Stand-in view PNGs (the rasteriser needs numpy) recorded by the real
    render_glb_views.record_views, so the gate sees exactly what a render writes."""
    renderer = repo.root / "device-models" / "render_glb_views.py"
    if not renderer.is_file():
        shutil.copyfile(HERE / "render_glb_views.py", renderer)
    views = repo.root / "skins" / "fake" / "views"
    views.mkdir(exist_ok=True)
    for name in drift.VIEW_NAMES:
        (views / f"{name}.png").write_bytes(f"{tag}:{name}".encode())
    render_glb_views.record_views(repo.glb)


class ViewsLockstepTests(unittest.TestCase):
    """skins/<id>/views/*.png move in lockstep with the glb they were rendered from."""

    def failures(self, repo: FakeRepo) -> list[str]:
        return drift.check_views(repo.meta, root=repo.root)

    def fresh(self) -> FakeRepo:
        repo = FakeRepo(self)
        repo.export()
        write_fake_views(repo)
        self.assertEqual(self.failures(repo), [], "positive control")
        self.assertEqual(drift.check_glb(repo.meta, root=repo.root), [], "positive control")
        return repo

    def assert_regenerate(self, failures: list[str], needle: str) -> None:
        self.assertTrue(
            any(needle in f and "regenerate with render_glb_views.py" in f for f in failures),
            failures,
        )

    def test_reexported_glb_without_new_views_fails(self):
        repo = self.fresh()
        stale_views = json.loads(repo.meta.read_text(encoding="utf-8"))["views"]
        parts = fake_parts()
        parts["body"] = box(0, 0, 0, 61, 30, 10)
        repo.export(parts)  # a new glb; the exporter rewrites model-glb.json
        self.assertEqual(drift.check_glb(repo.meta, root=repo.root), [], "glb itself is fine")
        self.assert_regenerate(self.failures(repo), "no views block")
        # Views block carried over by hand: still older than the glb.
        meta = json.loads(repo.meta.read_text(encoding="utf-8"))
        meta["views"] = stale_views
        repo.meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        self.assert_regenerate(self.failures(repo), "older than the glb")
        write_fake_views(repo, "v2")
        self.assertEqual(self.failures(repo), [], "positive control after regen")

    def test_renderer_edit_without_rerender_fails(self):
        repo = self.fresh()
        renderer = repo.root / "device-models" / "render_glb_views.py"
        renderer.write_text(renderer.read_text(encoding="utf-8") + "# new camera\n",
                            encoding="utf-8")
        self.assert_regenerate(self.failures(repo), "renderer_sha256")
        write_fake_views(repo, "v2")
        self.assertEqual(self.failures(repo), [], "positive control after regen")
        meta = json.loads(repo.meta.read_text(encoding="utf-8"))
        del meta["views"]["renderer"]
        repo.meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        self.assert_regenerate(self.failures(repo), "renderer")

    def test_hand_edited_png_fails(self):
        repo = self.fresh()
        front = repo.root / "skins" / "fake" / "views" / "front.png"
        front.write_bytes(front.read_bytes() + b"\x00")
        self.assert_regenerate(self.failures(repo), "views/front.png")

    def test_missing_and_unrecorded_png_fail(self):
        repo = self.fresh()
        views = repo.root / "skins" / "fake" / "views"
        (views / "iso.png").write_bytes(b"extra")
        self.assert_regenerate(self.failures(repo), "iso")
        (views / "iso.png").unlink()
        self.assertEqual(self.failures(repo), [], "positive control")
        (views / "top.png").unlink()
        self.assert_regenerate(self.failures(repo), "views/top.png")

    def test_recorded_view_set_must_be_the_six(self):
        repo = self.fresh()
        meta = json.loads(repo.meta.read_text(encoding="utf-8"))
        del meta["views"]["files"]["bottom"]
        repo.meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        self.assert_regenerate(self.failures(repo), "bottom")

    def test_main_views_only_runs_the_lockstep(self):
        repo = self.fresh()
        self.assertEqual(drift.views_main(repo.root), 0, "positive control")
        (repo.root / "skins" / "fake" / "views" / "left.png").write_bytes(b"stale")
        self.assertEqual(drift.views_main(repo.root), 1)

    def test_committed_views_are_recorded(self):
        """The repository itself: every exported glb has gated views."""
        metas = sorted((HERE.parent / "skins").glob(f"*/{export_gltf.METADATA_NAME}"))
        self.assertTrue(metas)
        for meta in metas:
            self.assertEqual(drift.check_views(meta), [], meta)


class RegenScriptTests(unittest.TestCase):
    """device-models/regen.sh refuses before touching anything."""

    def run_regen(self, openscad: str, *args: str):
        import subprocess

        env = dict(os.environ, OPENSCAD=openscad)
        return subprocess.run(
            ["bash", str(HERE / "regen.sh"), *args],
            capture_output=True, text=True, env=env, check=False,
        )

    def test_refuses_without_openscad_and_unknown_slug(self):
        missing = self.run_regen("/nonexistent/openscad", "trimui-smart-pro")
        self.assertEqual(missing.returncode, 2, missing.stderr)
        self.assertIn("openscad not found", missing.stderr)
        stub_dir = temp_root(self, "pf-regen-stub-")
        stub = stub_dir / "openscad"
        stub.write_text("#!/bin/sh\necho 'OpenSCAD version 2021.01'\n")
        stub.chmod(0o755)
        # Positive control: with an openscad present the openscad refusal does
        # not fire; the next guard (slug) does.
        unknown = self.run_regen(str(stub), "no-such-model")
        self.assertEqual(unknown.returncode, 2, unknown.stderr)
        self.assertNotIn("openscad not found", unknown.stderr)
        self.assertIn("unknown model slug", unknown.stderr)
        self.assertIn("trimui-smart-pro", unknown.stderr)
        usage = self.run_regen(str(stub))
        self.assertEqual(usage.returncode, 2, usage.stderr)
        self.assertIn("usage", usage.stderr)


def load_render_module(slug: str):
    """A device render.py for its pure rect helpers. Pillow is only needed to
    render, so stub it where it is absent (the CI drift leg) rather than skip."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        import types

        pil = types.ModuleType("PIL")
        for name in ("Image", "ImageChops", "ImageDraw", "ImageOps"):
            setattr(pil, name, types.ModuleType(f"PIL.{name}"))
            sys.modules[f"PIL.{name}"] = getattr(pil, name)
        sys.modules["PIL"] = pil
    spec = importlib.util.spec_from_file_location(
        f"render_{slug.replace('-', '_')}", HERE / slug / "render.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def system_key_failures(descriptor: dict, doc: dict) -> list[str]:
    """Every class=system input is bound to a glb control node carrying it."""
    nodes = {n.get("name"): n for n in doc.get("nodes", [])}
    parts = descriptor.get("skin", {}).get("parts", {})
    failures = []
    for row in descriptor.get("inputs", []):
        if row.get("class") != "system":
            continue
        part = row.get("skin_part")
        if not part:
            failures.append(f"{row['id']}: no skin_part")
        elif part not in parts:
            failures.append(f"{row['id']}: skin_part {part} not in [skin.parts]")
        elif part not in nodes:
            failures.append(f"{row['id']}: skin_part {part} is not a glb node")
        elif row["id"] not in [i["id"] for i in nodes[part]["extras"]["inputs"]]:
            failures.append(f"{row['id']}: glb node {part} does not carry it")
    if "btn_power" not in nodes:
        failures.append("no btn_power glb node")
    return failures


class SystemKeyNodeTests(unittest.TestCase):
    """tsp-h5ed.46.21: VOL+/VOL- and POWER are clickable glb nodes (repository)."""

    def test_system_inputs_bind_glb_nodes(self):
        import tomllib

        for device in ("a133", "a523"):
            with (HERE.parent / "devices" / device / "capabilities.toml").open("rb") as f:
                descriptor = tomllib.load(f)
            doc, _ = export_gltf.read_glb(
                (HERE.parent / "skins" / device / "model.glb").read_bytes()
            )
            self.assertEqual(system_key_failures(descriptor, doc), [], device)
            # Negative controls: an unbound row and a dropped node both fail.
            unbound = copy.deepcopy(descriptor)
            for row in unbound["inputs"]:
                if row["id"] == "vol_up":
                    row.pop("skin_part", None)
            self.assertIn("vol_up: no skin_part",
                          system_key_failures(unbound, doc), device)
            dropped = copy.deepcopy(doc)
            dropped["nodes"] = [n for n in dropped["nodes"]
                                if n.get("name") not in ("btn_vol_down", "btn_power")]
            failures = system_key_failures(descriptor, dropped)
            self.assertIn("no btn_power glb node", failures, device)
            self.assertTrue(any(f.startswith("vol_down:") for f in failures), failures)

    def test_rocker_halves_get_disjoint_rects(self):
        for slug in ("trimui-smart-pro", "trimui-smart-pro-s"):
            render = load_render_module(slug)
            # Two one-at-a-time diffs that share the seam column (+1 px padding).
            rects = {
                "btn_vol_down": {"x": 930, "y": 20, "w": 62, "h": 12},
                "btn_vol_up": {"x": 988, "y": 21, "w": 61, "h": 11},
                "btn_power": {"x": 400, "y": 20, "w": 40, "h": 12},
            }
            render.split_rocker_overlap(rects)
            self.assertEqual(render.rectangle_overlaps(rects), [], slug)
            down, up = rects["btn_vol_down"], rects["btn_vol_up"]
            self.assertEqual((down["x"], down["x"] + down["w"]), (930, 990), slug)
            self.assertEqual((up["x"], up["x"] + up["w"]), (990, 1049), slug)
            self.assertEqual(rects["btn_power"],
                             {"x": 400, "y": 20, "w": 40, "h": 12}, slug)
            # Positive control: already-disjoint halves are left alone, and a
            # view without the rocker is a no-op instead of an error.
            apart = {
                "btn_vol_down": {"x": 930, "y": 20, "w": 50, "h": 12},
                "btn_vol_up": {"x": 990, "y": 20, "w": 50, "h": 12},
            }
            before = copy.deepcopy(apart)
            render.split_rocker_overlap(apart)
            self.assertEqual(apart, before, slug)
            render.split_rocker_overlap({"btn_l1": {"x": 0, "y": 0, "w": 9, "h": 9}})
            self.assertIn("btn_vol_up", render.CONTROL_IDS, slug)
            self.assertIn("btn_vol_up", render.SKIN_VIEWS["top"]["controls"], slug)


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

    def test_canonical_triangle_order(self):
        """OpenSCAD 2021.01 emits the same triangles in a different order on every
        run; the canonical order makes the exported bytes independent of it."""
        tris = box(0, 0, 0, 1, 2, 3)
        shuffled = [t[1:] + t[:1] if i % 2 else t for i, t in enumerate(reversed(tris))]
        self.assertNotEqual(shuffled, tris)
        canonical = export_gltf.canonical_triangles(tris)
        self.assertEqual(export_gltf.canonical_triangles(shuffled), canonical)
        # Rotation keeps the winding: a flipped triangle stays distinct.
        flipped = [(tris[0][0], tris[0][2], tris[0][1])] + tris[1:]
        self.assertNotEqual(export_gltf.canonical_triangles(flipped), canonical)
        self.assertEqual(sorted(tuple(sorted(t)) for t in canonical),
                         sorted(tuple(sorted(t)) for t in tris))

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
