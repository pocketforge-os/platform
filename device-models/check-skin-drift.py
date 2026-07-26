#!/usr/bin/env python3
"""Platform CI drift gate for the .scad -> skin -> [skin.parts] chain (infra-113 D9).

Deterministic, render-free consistency check over the committed
model -> rendered-skin -> device-descriptor chain for every modelled device. It
proves the chain cannot silently diverge WITHOUT running OpenSCAD, so it is cheap
and byte-stable enough to run on every relevant PR (no GL backend, no fonts, no
rendering non-determinism to fight).

DATA-DRIVEN BY AUTO-DISCOVERY. Every device whose skin has been rendered from a
model carries a ``skins/<id>/model-render.json`` (written by that model's
``render.py --write``). This check discovers those files and needs NO per-device
code: each ``model-render.json`` already records its own OpenSCAD ``source`` and
``renderer`` paths, the device id, the asset hashes, the derived control rects, and
the projected ``display_rect``. So adding a modelled device = committing its
rendered skin (its ``model-render.json``); this gate picks it up automatically. A
device with a descriptor but no model-rendered skin (only legacy bezel art, no
``model-render.json``) simply is not discovered and is not gated here.

For each discovered device it asserts:

* the OpenSCAD source and renderer recorded in ``model-render.json`` still hash to
  the committed ``.scad`` / ``render.py`` (edit the model, forget to regenerate the
  skin -> caught);
* the committed ``body.png`` / ``body_lit.png`` still hash to what
  ``model-render.json`` recorded (edit an asset, forget to regenerate -> caught);
* ``model-render.json`` control rects equal the device descriptor ``[skin.parts]``
  rects (edit one side, forget the other -> caught) -- these are what the sim GUI
  and ``check-skin`` consume, so a divergence is exactly the silent break D9 exists
  to stop;
* the projected screen ``display_rect`` matches on both sides.

COVERAGE / HONESTY (infra-113 D9). Every guarantee here is a strict SUBSET of
``render.py --check``: that command recomputes the recorded hashes and rects from a
fresh OpenSCAD render and compares them to the committed metadata, so a repo that
passes ``render.py --check`` necessarily passes this check. This is the fast,
byte-stable floor; ``render.py --check`` is the heavier OpenSCAD-dependent
companion. The ONE drift class this render-free gate cannot catch is a *consistent*
hand-edit of a rect in BOTH ``model-render.json`` AND ``capabilities.toml`` without
re-rendering -- the two files still agree and the ``.scad``/PNG hashes are
untouched, so the rect silently points where the rendered atlas no longer
highlights. That narrow, semi-adversarial case is closed by running
``render.py --check`` locally when touching a model (see device-models/README.md).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tomllib

# device-models/check-skin-drift.py -> repo root is one level up.
ROOT = Path(__file__).resolve().parents[1]
SKINS = ROOT / "skins"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm_rect(rect: dict) -> dict[str, int]:
    return {key: int(value) for key, value in rect.items()}


def check_skin(metadata_path: Path) -> list[str]:
    """Return a list of human-readable drift failures for one rendered skin."""
    skin_dir = metadata_path.parent
    device = skin_dir.name
    rel_meta = metadata_path.relative_to(ROOT)
    failures: list[str] = []

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("device") and metadata["device"] != device:
        failures.append(
            f"{device}: model-render.json.device={metadata['device']!r} does not "
            f"match its skin directory skins/{device}/"
        )

    # 1. Recorded source/renderer/asset hashes still match the committed files.
    #    The source and renderer paths are recorded (repo-relative) in the metadata
    #    itself, so the check stays model-agnostic.
    hash_targets = [
        ("source_sha256", metadata.get("source"), "source"),
        ("renderer_sha256", metadata.get("renderer"), "renderer"),
        ("body_sha256", f"skins/{device}/body.png", "body"),
        ("body_lit_sha256", f"skins/{device}/body_lit.png", "body_lit"),
    ]
    for field, rel, label in hash_targets:
        if not rel:
            failures.append(f"{device}: {rel_meta} is missing the {label} path")
            continue
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"{device}: missing committed {label} file {rel}")
            continue
        recorded = metadata.get(field)
        actual = sha256(path)
        if recorded != actual:
            failures.append(
                f"{device}: {field} drift for {rel}: "
                f"metadata={recorded} committed={actual} "
                f"(regenerate with render.py --write)"
            )

    # 2/3. Descriptor rects equal the model-derived rects.
    descriptor_path = ROOT / "devices" / device / "capabilities.toml"
    if not descriptor_path.is_file():
        failures.append(
            f"{device}: missing descriptor devices/{device}/capabilities.toml"
        )
        return failures
    with descriptor_path.open("rb") as stream:
        descriptor = tomllib.load(stream)

    declared = {
        name: norm_rect(rect)
        for name, rect in descriptor.get("skin", {}).get("parts", {}).items()
    }
    derived = {
        name: norm_rect(rect)
        for name, rect in metadata.get("controls", {}).items()
    }
    if set(declared) != set(derived):
        failures.append(
            f"{device}: control id sets differ: "
            f"descriptor[skin.parts]={sorted(declared)} "
            f"model-render.json.controls={sorted(derived)}"
        )
    for control_id in sorted(set(declared) & set(derived)):
        if declared[control_id] != derived[control_id]:
            failures.append(
                f"{device}: {control_id} rect drift: "
                f"descriptor={declared[control_id]} "
                f"model-render.json={derived[control_id]}"
            )

    # 4. Projected display_rect matches (mirrors render.py's own single-screen
    #    contract: exactly one screen carrying a display_rect).
    if "display_rect" in metadata:
        screens = [s for s in descriptor.get("screens", []) if "display_rect" in s]
        if len(screens) != 1:
            failures.append(
                f"{device}: expected exactly one descriptor screen with a "
                f"display_rect, found {len(screens)}"
            )
        else:
            declared_display = norm_rect(screens[0]["display_rect"])
            derived_display = norm_rect(metadata["display_rect"])
            if declared_display != derived_display:
                failures.append(
                    f"{device}: display_rect drift: "
                    f"descriptor={declared_display} "
                    f"model-render.json={derived_display}"
                )

    # 5. Additional CLICKABLE VIEWS (tsp-65jc.27). model-render.json may carry a
    #    "views" block ({name: {body, body_lit, body_sha256, body_lit_sha256,
    #    controls}}) for extra rendered atlases (e.g. the top-edge view the sim GUI
    #    rotates to). Each view is gated exactly like the front: its committed
    #    body/body_lit PNGs must hash to what the metadata recorded, and its control
    #    rects must EQUAL the descriptor's [skin.views.<name>.parts]. A view present
    #    on one side but not the other is drift. Shared source/renderer hashes are
    #    already covered by section 1 (same .scad/render.py). A device with no views
    #    block simply skips this — no per-device code, same auto-discovery property.
    metadata_views = metadata.get("views", {})
    descriptor_views = descriptor.get("skin", {}).get("views", {})
    if set(metadata_views) != set(descriptor_views):
        failures.append(
            f"{device}: view sets differ: "
            f"model-render.json.views={sorted(metadata_views)} "
            f"descriptor[skin.views]={sorted(descriptor_views)}"
        )
    for view_name in sorted(set(metadata_views) & set(descriptor_views)):
        view_meta = metadata_views[view_name]
        for field, label in (("body_sha256", "body"), ("body_lit_sha256", "body_lit")):
            rel = view_meta.get(label)
            if not rel:
                failures.append(
                    f"{device}/{view_name}: metadata missing the {label} path"
                )
                continue
            path = ROOT / rel
            if not path.is_file():
                failures.append(
                    f"{device}/{view_name}: missing committed {label} file {rel}"
                )
                continue
            recorded = view_meta.get(field)
            actual = sha256(path)
            if recorded != actual:
                failures.append(
                    f"{device}/{view_name}: {field} drift for {rel}: "
                    f"metadata={recorded} committed={actual} "
                    f"(regenerate with render.py --write-views)"
                )
        view_declared = {
            name: norm_rect(rect)
            for name, rect in descriptor_views[view_name].get("parts", {}).items()
        }
        view_derived = {
            name: norm_rect(rect)
            for name, rect in view_meta.get("controls", {}).items()
        }
        if set(view_declared) != set(view_derived):
            failures.append(
                f"{device}/{view_name}: control id sets differ: "
                f"descriptor[skin.views.{view_name}.parts]={sorted(view_declared)} "
                f"model-render.json.views.{view_name}.controls={sorted(view_derived)}"
            )
        for control_id in sorted(set(view_declared) & set(view_derived)):
            if view_declared[control_id] != view_derived[control_id]:
                failures.append(
                    f"{device}/{view_name}: {control_id} rect drift: "
                    f"descriptor={view_declared[control_id]} "
                    f"model-render.json={view_derived[control_id]}"
                )

    return failures


def main(argv: list[str]) -> int:
    metadata_paths = sorted(SKINS.glob("*/model-render.json"))
    if not metadata_paths:
        print(
            "skin_drift=fail: no skins/*/model-render.json found -- a modelled skin "
            "was expected (a mass deletion would silently disable this gate)",
            file=sys.stderr,
        )
        return 1

    all_failures: list[str] = []
    for metadata_path in metadata_paths:
        all_failures.extend(check_skin(metadata_path))

    if all_failures:
        print("skin_drift=fail", file=sys.stderr)
        for failure in all_failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    devices = ",".join(p.parent.name for p in metadata_paths)
    print(f"skin_drift=pass models={len(metadata_paths)} devices={devices}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
