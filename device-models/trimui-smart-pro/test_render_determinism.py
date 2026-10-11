#!/usr/bin/env python3
"""Local self-test: render.py --write/--write-views are byte-stable on an unedited .scad (tsp-h5ed.46.29).

OpenSCAD 2021.01 draws a few tie pixels differently from one process to the next,
so regen.sh over an unedited .scad dirtied body_top.png/body_lit_top.png. render.py
keeps the committed bytes when a re-render of the same .scad only tie-jitters
(see JITTER_MAX_PIXELS), and keeps a committed rect a tie pixel moved by one edge
pixel (see JITTER_RECT_PIXELS; ported from the a523 by tsp-h5ed.46.34). In one
invocation:

  1. hermetic (no OpenSCAD): a 1-pixel and a JITTER_MAX_PIXELS-pixel difference
     keep the committed PNG; JITTER_MAX_PIXELS + 1 pixels, a resized image, a
     missing PNG, an edited .scad or render.py, or a moved rect write the fresh
     render; a rect edge 1 pixel off takes the committed rect, 2 pixels, another
     id set or edited inputs do not; --write keeps a 1-pixel change to
     body.png/body_lit.png (and the views block) with unedited inputs and writes
     it after a render.py edit;
  2. positive: --write-views run twice over a scratch copy of the committed a133
     skin leaves body_top/body_lit_top/model-render.json byte-identical to the
     committed files both times, and a third time with one tie pixel injected
     into every raw OpenSCAD frame (so the jitter is present on every run, not
     only when OpenSCAD happens to flip); the same injected run after a
     render.py edit writes both view PNGs; --write and --check over the
     unedited scratch skin leave every file byte-identical and pass;
  3. negative: a seeded one-line .scad mutation (shell depth 10.7 -> 11.7 mm)
     changes body_top.png, so (2) cannot pass by never writing;
  4. hermetic (no OpenSCAD; tsp-h5ed.46.34), per file render.py hashes and then
     uses: the committed PNG kept by --write, the committed PNG compared by
     --check, model-render.json (--write, --write-views, --check) and the .scad. Positive:
     the honest file is read once and used. Negative: the file is replaced right
     after render.py read it (the render._after_read test hook) or the .scad is
     edited during the render, and render.py refuses, naming the file.

Local only, like render.py --check: needs OpenSCAD (OPENSCAD=<path>) and Pillow.
Run:  python3 device-models/trimui-smart-pro/test_render_determinism.py
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
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
    committed = committed.read_bytes()
    limit = render.JITTER_MAX_PIXELS
    check("keep: identical render", render.keeps_committed(committed, base, True))
    check("keep: 1 tie pixel", render.keeps_committed(committed, with_changed_pixels(base, 1), True))
    check(f"keep: {limit} tie pixels (the bound)",
          render.keeps_committed(committed, with_changed_pixels(base, limit), True))
    check(f"write: {limit + 1} changed pixels",
          not render.keeps_committed(committed, with_changed_pixels(base, limit + 1), True))
    check("write: different size",
          not render.keeps_committed(committed, base.resize((base.width - 1, base.height)), True))
    check("write: no committed PNG", not render.keeps_committed(None, base, True))
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

    rects = {"trig_r": {"x": 1217, "y": 25, "w": 196, "h": 69},
             "btn_l1": {"x": 10, "y": 20, "w": 30, "h": 40}}
    step = render.JITTER_RECT_PIXELS
    grown = copy.deepcopy(rects)
    grown["trig_r"].update(y=25 - step, h=69 + step)  # the move measured on the a523's trig_r
    check(f"rects: an edge {step} px off takes the committed rect",
          render.canonical_rects(grown, rects, True) == rects)
    shifted = copy.deepcopy(rects)
    shifted["btn_l1"].update(x=10 - step, w=30 + 2 * step)  # both side edges, 1 px each
    check(f"rects: two edges {step} px off take the committed rect",
          render.canonical_rects(shifted, rects, True) == rects)
    far = copy.deepcopy(rects)
    far["trig_r"].update(y=25 - step - 1, h=69 + step + 1)
    check(f"rects: an edge {step + 1} px off is derived fresh",
          render.canonical_rects(far, rects, True) == far)
    check("rects: edited inputs derive fresh",
          render.canonical_rects(grown, rects, False) == grown)
    check("rects: no committed rects derive fresh",
          render.canonical_rects(grown, None, True) == grown)
    extra = {**copy.deepcopy(rects), "btn_menu": {"x": 1, "y": 1, "w": 1, "h": 1}}
    check("rects: a different id set derives fresh",
          render.canonical_rects(extra, rects, True) == extra)



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
    # --write records the renderer path relative to ROOT; the copy hashes the same.
    shutil.copyfile(render.RENDERER, root / render.RENDERER.relative_to(render.ROOT))
    return root


def point_render_at(root: Path) -> dict:
    """Redirect render.py's module paths into ``root``; return the originals."""
    saved = {name: getattr(render, name)
             for name in ("ROOT", "MODEL", "RENDERER", "METADATA", "BODY", "BODY_LIT",
                          "SKIN_VIEWS")}
    skin = root / render.SKIN_DIR.relative_to(render.ROOT)
    render.ROOT = root
    render.MODEL = root / saved["MODEL"].relative_to(saved["ROOT"])
    render.RENDERER = root / saved["RENDERER"].relative_to(saved["ROOT"])
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
        render.write_outputs(images[0], images[1], dict(derived), render._read_metadata())
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


@contextlib.contextmanager
def replaced_after_read(target: Path):
    """render.py's read hook replaces ``target`` right after render.py first reads it:
    a new file of the same size with one byte changed, as an editor or a checkout
    writes it."""
    real_hook = render._after_read
    pending = [True]

    def replace(path: Path) -> None:
        if path == target and pending:
            pending.clear()
            data = path.read_bytes()
            replacement = path.with_name(path.name + ".replacement")
            replacement.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
            os.replace(replacement, path)

    render._after_read = replace
    try:
        yield
    finally:
        render._after_read = real_hook
    check(f"test hook: {target.name} was replaced after render.py read it", not pending)


def refuses(name: str, path: Path, action) -> None:
    """``action`` refuses with a message naming ``path``."""
    try:
        action()
    except RuntimeError as error:
        check(name, path.name in str(error) and "changed" in str(error), f"error={error}")
    else:
        check(name, False, "render.py used the file")


@contextlib.contextmanager
def stubbed_view_render(views: dict, during=None):
    """render_view_set without OpenSCAD: the committed view PNGs and rects. ``during``
    runs inside the render."""
    real_render_view_set = render.render_view_set

    def stub(work: Path, name: str, view: dict, *args) -> tuple:
        if during is not None:
            during()
        images = []
        for path in (view["body"], view["body_lit"]):
            with Image.open(path) as source:
                images.append(source.convert("RGB"))
        meta = {key: value for key, value in views[name].items()
                if not key.endswith("_sha256")}
        return images[0], images[1], copy.deepcopy(meta)

    render.render_view_set = stub
    try:
        yield
    finally:
        render.render_view_set = real_render_view_set


def pinned_read_cases(work: Path) -> None:
    """Every file render.py hashes and then uses is read once, through one open file
    (tsp-h5ed.46.34): per site, the honest file is used, and a file replaced between
    the read and its use is refused with its path."""
    root = scratch_root(work / "pinned")
    saved = point_render_at(root)
    try:
        top = render.SKIN_VIEWS["top"]
        files = (render.MODEL, render.METADATA, render.BODY, render.BODY_LIT,
                 top["body"], top["body_lit"])
        originals = {path: path.read_bytes() for path in files}

        def restore() -> None:
            for path, data in originals.items():
                path.write_bytes(data)

        def unchanged(paths) -> bool:
            return all(path.read_bytes() == originals[path] for path in paths)

        committed = json.loads(originals[render.METADATA])
        derived = {key: value for key, value in committed.items()
                   if key not in ("views", "body_sha256", "body_lit_sha256")}
        derived.update(render.input_hashes())
        images = []
        for path in (render.BODY, render.BODY_LIT):
            with Image.open(path) as source:
                images.append(with_changed_pixels(source.convert("RGB"), 1))
        body_sha = hashlib.sha256(originals[render.BODY]).hexdigest()

        # The committed PNG --write keeps: decided, hashed and kept from one read.
        sha = render.save_canonical_png(images[0], render.BODY, True)
        check("--write keep, honest body.png: the kept bytes' hash is returned and the file left",
              sha == body_sha and unchanged([render.BODY]), sha)
        with replaced_after_read(render.BODY):
            refuses("--write keep, body.png replaced after the read: refused", render.BODY,
                    lambda: render.save_canonical_png(images[0], render.BODY, True))
        restore()

        # The committed PNG --check compares: compared and copied from one read.
        generated = root / "generated.png"
        render.save_png(images[0], generated)
        status = render.committed_png_status(render.BODY, images[0], generated, True)
        check("--check, honest body.png: current, and the generated copy holds the committed bytes",
              status == "current" and generated.read_bytes() == originals[render.BODY], status)
        check("--check, no committed PNG: missing",
              render.committed_png_status(root / "absent.png", images[0], generated, True)
              == "missing")
        render.save_png(images[0], generated)
        with replaced_after_read(render.BODY):
            refuses("--check, body.png replaced after the read: refused", render.BODY,
                    lambda: render.committed_png_status(render.BODY, images[0], generated, True))
        restore()

        # model-render.json: --write overwrites only the file it read.
        render.write_outputs(images[0], images[1], dict(derived), render._read_metadata())
        check("--write, honest model-render.json: written, every file as committed",
              unchanged(files))
        with replaced_after_read(render.METADATA):
            previous = render._read_metadata()
        replaced = render.METADATA.read_bytes()
        refuses("--write, model-render.json replaced after the read: refused", render.METADATA,
                lambda: render.write_outputs(images[0], images[1], dict(derived), previous))
        check("--write refused: the replacement is left and no PNG written",
              render.METADATA.read_bytes() == replaced and unchanged(files[2:]))
        restore()

        # model-render.json: --write-views overwrites only the file it read.
        with stubbed_view_render(committed["views"]):
            render.write_views()
        check("--write-views, honest model-render.json: written, every file as committed",
              unchanged(files))
        with stubbed_view_render(committed["views"]), replaced_after_read(render.METADATA):
            refuses("--write-views, model-render.json replaced after the read: refused",
                    render.METADATA, render.write_views)
        replaced = render.METADATA.read_bytes()
        check("--write-views refused: the replacement is left and no PNG written",
              replaced != originals[render.METADATA] and unchanged(files[2:]))
        restore()

        # model-render.json: --check passes only while the path names the file it read.
        def passes(action) -> tuple[bool, str]:
            try:
                action()
            except RuntimeError as error:
                return False, str(error)
            return True, ""

        committed_images = []
        for path in (render.BODY, render.BODY_LIT):
            with Image.open(path) as source:
                committed_images.append(source.convert("RGB"))

        def check_front(previous) -> None:
            render.check_outputs(*committed_images, dict(derived), previous)

        ok, error = passes(lambda: check_front(render._read_metadata()))
        check("--check, honest model-render.json: the front check passes", ok, error)
        with replaced_after_read(render.METADATA):
            previous = render._read_metadata()
        refuses("--check, model-render.json replaced after the read: the front check refuses",
                render.METADATA, lambda: check_front(previous))
        restore()
        with stubbed_view_render(committed["views"]):
            ok, error = passes(lambda: render.check_views(render._read_metadata()))
            check("--check, honest model-render.json: the view check passes", ok, error)
            with replaced_after_read(render.METADATA):
                previous = render._read_metadata()
            refuses("--check, model-render.json replaced after the read: the view check refuses",
                    render.METADATA, lambda: render.check_views(previous))
        restore()

        # The .scad: hashed before the render, re-hashed before anything is written.
        def edit_model() -> None:
            render.MODEL.write_bytes(originals[render.MODEL] + b"// edited\n")

        with stubbed_view_render(committed["views"], during=edit_model):
            refuses("--write-views, .scad edited during the render: refused", render.MODEL,
                    render.write_views)
        check("--write-views refused on the .scad: nothing written", unchanged(files[1:]))
        restore()
        previous = render._read_metadata()
        edit_model()
        refuses("--write, .scad edited after its hash: refused", render.MODEL,
                lambda: render.write_outputs(images[0], images[1], dict(derived), previous))
        check("--write refused on the .scad: nothing written", unchanged(files[1:]))
        restore()
    finally:
        for name, value in saved.items():
            setattr(render, name, value)


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


def run_main(argv: list[str]) -> tuple[int, str]:
    try:
        return render.main(argv), ""
    except RuntimeError as error:
        return 1, str(error)


def front_render_cases(saved: dict, root: Path) -> None:
    """--write and --check over the unedited scratch a133 skin (OpenSCAD), through
    the canonical_rects wiring."""
    outputs = (render.BODY, render.BODY_LIT, render.METADATA)
    committed = [(saved["ROOT"] / path.relative_to(root)).read_bytes() for path in outputs]
    status, error = run_main(["--write"])
    check("front --write (unedited) succeeds", status == 0, error)
    for path, before in zip(outputs, committed):
        check(f"front --write (unedited): {path.name} byte-identical to the committed file",
              path.read_bytes() == before)
    status, error = run_main(["--check"])
    check("--check passes against the committed skin", status == 0, error)
    for path, before in zip(outputs, committed):
        path.write_bytes(before)


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

        front_render_cases(saved, root)

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
        api = ("keeps_committed", "same_derivation", "inputs_unchanged", "canonical_rects")
        if all(hasattr(render, name) for name in api):
            hermetic_cases(work)
        else:
            check("render.py has the tie-jitter canonicaliser (" + ", ".join(api) + ")", False)
        pinned = ("read_pinned", "ensure_pinned", "committed_png_status", "input_hashes",
                  "ensure_inputs", "_after_read")
        if all(hasattr(render, name) for name in pinned):
            pinned_read_cases(work)
        else:
            check("render.py reads each file it hashes once (" + ", ".join(pinned) + ")", False)
        render_pair(work)

    print()
    if _failures:
        print(f"{len(_failures)} FAILURE(S): " + ", ".join(_failures))
        return 1
    print("ALL RENDER DETERMINISM SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
