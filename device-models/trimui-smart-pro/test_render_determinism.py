#!/usr/bin/env python3
"""Local self-test: render.py --write-views is byte-stable on an unedited .scad (tsp-h5ed.46.29).

OpenSCAD 2021.01 draws a few tie pixels differently from one process to the next,
so regen.sh over an unedited .scad dirtied body_top.png/body_lit_top.png. render.py
keeps the committed bytes when a re-render of the same .scad only tie-jitters
(see JITTER_MAX_PIXELS). In one invocation:

  1. hermetic (no OpenSCAD): a 1-pixel and a JITTER_MAX_PIXELS-pixel difference
     keep the committed PNG; JITTER_MAX_PIXELS + 1 pixels, a resized image, a
     missing PNG, an edited .scad or render.py, or a moved rect write the fresh
     render; --write keeps a 1-pixel change to body.png/body_lit.png (and the
     views block) with unedited inputs and writes it after a render.py edit;
  2. positive: --write-views run twice over a scratch copy of the committed a133
     skin leaves body_top/body_lit_top/model-render.json byte-identical to the
     committed files both times, and a third time with one tie pixel injected
     into every raw OpenSCAD frame (so the jitter is present on every run, not
     only when OpenSCAD happens to flip); the same injected run after a
     render.py edit writes both view PNGs;
  3. negative: a seeded one-line .scad mutation (shell depth 10.7 -> 11.7 mm)
     changes body_top.png, so (2) cannot pass by never writing.

Local only, like render.py --check: needs OpenSCAD (OPENSCAD=<path>) and Pillow.
Run:  python3 device-models/trimui-smart-pro/test_render_determinism.py
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import render  # noqa: E402

MUTATION = ("local_shell_depth = 10.7;", "local_shell_depth = 11.7;")
# The raw top-view pixel measured flipping between (10,11,13) and (12,13,14).
TIE_PIXEL = (1140, 664)

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        _failures.append(name)
        if detail:
            print("  " + detail.replace("\n", "\n  "))


def with_changed_pixels(image: Image.Image, count: int) -> Image.Image:
    changed = image.copy()
    pixels = changed.load()
    for index in range(count):
        x, y = index % changed.width, index // changed.width
        red, green, blue = pixels[x, y]
        pixels[x, y] = ((red + 2) % 256, green, blue)
    return changed


def hermetic_cases(work: Path) -> None:
    committed = work / "committed.png"
    with Image.open(render.TOP_BODY) as source:
        base = source.convert("RGB")
    render.save_png(base, committed)
    limit = render.JITTER_MAX_PIXELS
    check("keep: identical render", render.keeps_committed(committed, base, True))
    check("keep: 1 tie pixel", render.keeps_committed(committed, with_changed_pixels(base, 1), True))
    check(f"keep: {limit} tie pixels (the bound)",
          render.keeps_committed(committed, with_changed_pixels(base, limit), True))
    check(f"write: {limit + 1} changed pixels",
          not render.keeps_committed(committed, with_changed_pixels(base, limit + 1), True))
    check("write: different size",
          not render.keeps_committed(committed, base.resize((base.width - 1, base.height)), True))
    check("write: no committed PNG",
          not render.keeps_committed(work / "absent.png", base, True))
    check("write: 1 pixel but a different derivation",
          not render.keeps_committed(committed, with_changed_pixels(base, 1), False))

    inputs = {"source_sha256": render.sha256(render.MODEL),
              "renderer_sha256": render.sha256(render.RENDERER)}
    check("inputs: this .scad and this render.py", render.inputs_unchanged(inputs))
    check("inputs: an edited .scad differs",
          not render.inputs_unchanged({**inputs, "source_sha256": "0" * 64}))
    check("inputs: an edited render.py differs",
          not render.inputs_unchanged({**inputs, "renderer_sha256": "0" * 64}))
    check("inputs: no committed metadata differs", not render.inputs_unchanged(None))

    view = {"camera": {"crop": [1, 2, 3, 4]}, "canvas": {"w": 1, "h": 1},
            "controls": {"btn_l1": {"x": 1, "y": 2, "w": 3, "h": 4}}}
    keys = render.VIEW_DERIVATION_KEYS
    check("derivation: same inputs and rects", render.same_derivation(view, True, view, keys))
    moved = copy.deepcopy(view)
    moved["controls"]["btn_l1"]["x"] = 2
    check("derivation: a moved rect differs", not render.same_derivation(view, True, moved, keys))
    check("derivation: edited inputs differ", not render.same_derivation(view, False, view, keys))
    check("derivation: no committed view differs",
          not render.same_derivation(None, True, view, keys))


def scratch_root(work: Path) -> Path:
    """A scratch ROOT holding copies of the a133 skin files --write/--write-views touch."""
    root = work / "root"
    skin = root / render.SKIN_DIR.relative_to(render.ROOT)
    skin.mkdir(parents=True)
    for path in (render.METADATA, render.BODY, render.BODY_LIT,
                 render.TOP_BODY, render.TOP_BODY_LIT):
        shutil.copyfile(path, skin / path.name)
    model = root / render.MODEL.relative_to(render.ROOT)
    model.parent.mkdir(parents=True)
    shutil.copyfile(render.MODEL, model)
    return root


def point_render_at(root: Path) -> dict:
    """Redirect render.py's module paths into ``root``; return the originals."""
    saved = {name: getattr(render, name)
             for name in ("ROOT", "MODEL", "METADATA", "BODY", "BODY_LIT", "SKIN_VIEWS")}
    skin = root / render.SKIN_DIR.relative_to(render.ROOT)
    render.ROOT = root
    render.MODEL = root / saved["MODEL"].relative_to(saved["ROOT"])
    render.METADATA = skin / saved["METADATA"].name
    render.BODY = skin / saved["BODY"].name
    render.BODY_LIT = skin / saved["BODY_LIT"].name
    views = copy.deepcopy(saved["SKIN_VIEWS"])
    for view in views.values():
        view["body"] = skin / view["body"].name
        view["body_lit"] = skin / view["body_lit"].name
    render.SKIN_VIEWS = views
    return saved


def set_recorded_renderer(sha: str) -> None:
    metadata = json.loads(render.METADATA.read_text(encoding="utf-8"))
    metadata["renderer_sha256"] = sha
    render.METADATA.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")


def front_write_cases(originals: dict[Path, bytes]) -> None:
    """--write's front path without OpenSCAD: a 1-pixel change to body.png and
    body_lit.png is kept with unedited inputs and written after a render.py edit."""
    committed = json.loads(originals[render.METADATA])
    derived = {key: value for key, value in committed.items()
               if key not in ("views", "body_sha256", "body_lit_sha256")}
    derived["source_sha256"] = render.sha256(render.MODEL)
    derived["renderer_sha256"] = render.sha256(render.RENDERER)
    images = []
    for path in (render.BODY, render.BODY_LIT):
        with Image.open(path) as source:
            images.append(with_changed_pixels(source.convert("RGB"), 1))
    for label, recorded, kept in (
        ("unedited inputs", derived["renderer_sha256"], True),
        ("render.py edited", "0" * 64, False),
    ):
        for path, data in originals.items():
            path.write_bytes(data)
        set_recorded_renderer(recorded)
        render.write_outputs(images[0], images[1], dict(derived))
        for path in (render.BODY, render.BODY_LIT):
            check(f"front --write, {label}: 1-pixel change to {path.name} "
                  + ("keeps the committed bytes" if kept else "is written"),
                  (path.read_bytes() == originals[path]) == kept)
        views = json.loads(render.METADATA.read_text(encoding="utf-8")).get("views")
        check(f"front --write, {label}: views block "
              + ("carried over" if kept else "dropped for --write-views to re-render"),
              (views == committed.get("views")) if kept else views is None)
    for path, data in originals.items():
        path.write_bytes(data)


def write_views_with_tie_pixel() -> None:
    """--write-views where OpenSCAD's random tie flip happens on every frame: one
    raw pixel takes the neighbouring face's shade (+2, as measured at (1140, 664))."""
    real_run_openscad = render.run_openscad

    def tie_jitter_openscad(output: Path, **kwargs) -> None:
        real_run_openscad(output, **kwargs)
        with Image.open(output) as source:
            frame = source.convert("RGB")
        x, y = TIE_PIXEL
        red, green, blue = frame.getpixel((x, y))
        frame.putpixel((x, y), (min(255, red + 2), min(255, green + 2), blue))
        frame.save(output)

    render.run_openscad = tie_jitter_openscad
    try:
        render.write_views()
    finally:
        render.run_openscad = real_run_openscad


def render_pair(work: Path) -> None:
    root = scratch_root(work)
    saved = point_render_at(root)
    try:
        originals = {path: path.read_bytes()
                     for path in (render.METADATA, render.BODY, render.BODY_LIT)}
        front_write_cases(originals)

        view = render.SKIN_VIEWS["top"]
        outputs = (view["body"], view["body_lit"], render.METADATA)
        committed = [
            (saved["ROOT"] / path.relative_to(root)).read_bytes() for path in outputs
        ]
        for run in (1, 2):
            render.write_views()
            for path, before in zip(outputs, committed):
                check(f"run {run}: unedited .scad leaves {path.name} byte-identical to the committed file",
                      path.read_bytes() == before)

        # Run 3 forces the tie flip OpenSCAD makes at random onto every frame.
        write_views_with_tie_pixel()
        for path, before in zip(outputs, committed):
            check(f"run 3 (injected tie pixel): {path.name} byte-identical to the committed file",
                  path.read_bytes() == before)

        # The same tie pixel after a render.py edit is a fresh render, not jitter.
        set_recorded_renderer("0" * 64)
        write_views_with_tie_pixel()
        for path, before in zip(outputs[:2], committed):
            check(f"render.py edited + injected tie pixel: {path.name} is written",
                  path.read_bytes() != before)
        render.METADATA.write_bytes(committed[2])

        source = render.MODEL.read_text(encoding="utf-8")
        check("seeded mutation line is present exactly once", source.count(MUTATION[0]) == 1)
        render.MODEL.write_text(source.replace(MUTATION[0], MUTATION[1]), encoding="utf-8")
        render.write_views()
        check("negative: a one-line .scad mutation rewrites body_top.png",
              view["body"].read_bytes() != committed[0])
    finally:
        for name, value in saved.items():
            setattr(render, name, value)


def main() -> int:
    openscad = os.environ.get("OPENSCAD", "openscad")
    if shutil.which(openscad) is None:
        print(f"test_render_determinism: refusing: OpenSCAD not found ({openscad})",
              file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="tsp-render-determinism-") as directory:
        work = Path(directory)
        api = ("keeps_committed", "same_derivation", "inputs_unchanged")
        if all(hasattr(render, name) for name in api):
            hermetic_cases(work)
        else:
            check("render.py has the tie-jitter canonicaliser (" + ", ".join(api) + ")", False)
        render_pair(work)

    print()
    if _failures:
        print(f"{len(_failures)} FAILURE(S): " + ", ".join(_failures))
        return 1
    print("ALL RENDER DETERMINISM SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
