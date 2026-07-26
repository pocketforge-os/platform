#!/usr/bin/env python3
"""Platform CI drift gate for the .scad -> skin -> [skin.parts] chain (infra-113 D9).

Deterministic, render-free consistency check over the committed
model -> rendered-skin -> device-descriptor chain for every modelled device. It
proves the chain cannot silently diverge WITHOUT running OpenSCAD, so it is cheap
and byte-stable enough to run on every relevant PR (no GL backend, no fonts, no
rendering non-determinism to fight).

For each modelled device it asserts:

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

Every guarantee here is a strict subset of what ``render.py --check`` proves by a
full re-render: ``render.py --check`` recomputes the recorded hashes and rects from
a fresh OpenSCAD render and compares them to the committed metadata, so a repo that
passes ``render.py --check`` necessarily passes this check. This is the fast,
byte-stable floor; ``render.py --check`` is the heavier OpenSCAD-dependent companion
(see the workflow that runs both, and each model's README).

Data-driven: adding a modelled device = adding a row to ``MODELS`` (or, later, a
descriptor-discovery pass); nothing else in this file is device-specific.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tomllib

# device-models/check-skin-drift.py -> repo root is one level up.
ROOT = Path(__file__).resolve().parents[1]

# One row per modelled device. Paths are repo-root-relative. Add a modelled
# device = add a row here (keep it data-driven; do not special-case in the logic
# below). A device with a descriptor but no .scad model simply has no row and is
# not gated by this check.
MODELS: list[dict[str, str]] = [
    {
        "id": "a133",
        "model": "TrimUI Smart Pro (TG5040)",
        "scad": "device-models/trimui-smart-pro/trimui-smart-pro.scad",
        "renderer": "device-models/trimui-smart-pro/render.py",
        "metadata": "skins/a133/model-render.json",
        "body": "skins/a133/body.png",
        "body_lit": "skins/a133/body_lit.png",
        "descriptor": "devices/a133/capabilities.toml",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm_rect(rect: dict) -> dict[str, int]:
    return {key: int(value) for key, value in rect.items()}


def check_model(entry: dict[str, str]) -> list[str]:
    """Return a list of human-readable drift failures for one modelled device."""
    failures: list[str] = []
    device = entry["id"]

    metadata_path = ROOT / entry["metadata"]
    if not metadata_path.is_file():
        return [f"{device}: missing render metadata {entry['metadata']}"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    # 1. Recorded source/renderer/asset hashes still match the committed files.
    for field, rel in (
        ("source_sha256", entry["scad"]),
        ("renderer_sha256", entry["renderer"]),
        ("body_sha256", entry["body"]),
        ("body_lit_sha256", entry["body_lit"]),
    ):
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"{device}: missing committed file {rel}")
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
    descriptor_path = ROOT / entry["descriptor"]
    if not descriptor_path.is_file():
        failures.append(f"{device}: missing descriptor {entry['descriptor']}")
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

    return failures


def main(argv: list[str]) -> int:
    all_failures: list[str] = []
    for entry in MODELS:
        all_failures.extend(check_model(entry))
    if all_failures:
        print("skin_drift=fail", file=sys.stderr)
        for failure in all_failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"skin_drift=pass models={len(MODELS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
