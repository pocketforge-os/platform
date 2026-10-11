#!/usr/bin/env python3
"""Local self-test: render.py --semantic-output is byte-stable on an unedited .scad (tsp-h5ed.46.32).

The Brick copy of trimui-smart-pro/test_render_determinism.py (tsp-h5ed.46.29).
The Brick is model-only: regen.sh does not run its render.py, and its committed
glb and views come from export_gltf.py/render_glb_views.py. Its render.py writes
the semantic review atlas into a directory with recorded inputs
(semantic-model.json), and --check renders that atlas twice into one directory.
OpenSCAD 2021.01 draws a few tie pixels differently from one process to the next
(none measured at the Brick's cameras, the same renderer as the a133/a523), so a
re-render into a directory rendered from the same .scad and render.py keeps the
recorded bytes when it only tie-jitters (see JITTER_MAX_PIXELS) and keeps a
recorded rect a tie pixel moved by one edge pixel (see JITTER_RECT_PIXELS). In
one invocation:

  1. hermetic (no OpenSCAD): a 1-pixel and a JITTER_MAX_PIXELS-pixel difference
     keep the recorded PNG; JITTER_MAX_PIXELS + 1 pixels, a resized image, a
     missing PNG, an edited .scad or render.py, or a moved rect write the fresh
     render; a rect edge 1 pixel off takes the recorded rect, 2 pixels, another
     id set or edited inputs do not;
  2. positive: --semantic-output run twice into one scratch directory leaves
     semantic-neutral/semantic-lit/semantic-model.json byte-identical to the
     first run, and a third time with one tie pixel injected into every raw
     OpenSCAD frame; a recorded rect 1 pixel off the derived one is kept; the
     same injected run after a render.py edit writes both PNGs, and a recorded
     rect 2 pixels off is re-derived;
  3. negative: a seeded one-line .scad mutation (bottom corner radius 4.8 ->
     5.8 mm) changes semantic-neutral.png, so (2) cannot pass by never writing;
  4. hermetic (no OpenSCAD; tsp-h5ed.46.34), per file render.py hashes and then
     uses: the recorded PNG kept by --semantic-output, semantic-model.json and the
     .scad. Positive: the honest file is read once and used. Negative: the file is
     replaced right after render.py read it (the render._after_read test hook) or
     the .scad is edited during the render, and render.py refuses, naming the file.

Local only, like render.py --check: needs OpenSCAD (OPENSCAD=<path>) and Pillow.
Run:  python3 device-models/trimui-brick/test_render_determinism.py
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
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

MUTATION = ("bottom_corner_radius = 4.8;", "bottom_corner_radius = 5.8;")
# No Brick tie site was measured (174 frames byte-identical); this raw pixel lies on
# the device in every view and takes +2, the a133's measured tie step.
TIE_PIXEL = (750, 1050)
# A committed PNG for the hermetic bound cases.
SAMPLE_PNG = render.ROOT / "skins" / "trimui-brick" / "views" / "front.png"
OUTPUTS = ("semantic-neutral.png", "semantic-lit.png", "semantic-model.json")

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
    with Image.open(SAMPLE_PNG) as source:
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
    check("write: no recorded PNG", not render.keeps_committed(None, base, True))
    check("write: 1 pixel but a different derivation",
          not render.keeps_committed(committed, with_changed_pixels(base, 1), False))

    inputs = {"source_sha256": render.sha256(render.MODEL),
              "renderer_sha256": render.sha256(render.RENDERER)}
    check("inputs: this .scad and this render.py", render.inputs_unchanged(inputs))
    check("inputs: an edited .scad differs",
          not render.inputs_unchanged({**inputs, "source_sha256": "0" * 64}))
    check("inputs: an edited render.py differs",
          not render.inputs_unchanged({**inputs, "renderer_sha256": "0" * 64}))
    check("inputs: no recorded metadata differs", not render.inputs_unchanged(None))

    semantic = {"canvas": {"w": 1, "h": 1}, "display_rect": {"x": 1, "y": 1, "w": 1, "h": 1},
                "controls": {"dpad": {"x": 1, "y": 2, "w": 3, "h": 4}},
                "control_views": {"dpad": "front"},
                "views": {"front": {"crop": [1, 2, 3, 4]}}}
    keys = render.SEMANTIC_DERIVATION_KEYS
    check("derivation: same inputs and rects", render.same_derivation(semantic, True, semantic, keys))
    for key, value in (("controls", {"dpad": {"x": 2, "y": 2, "w": 3, "h": 4}}),
                       ("views", {"front": {"crop": [0, 2, 3, 4]}})):
        check(f"derivation: a different {key} differs",
              not render.same_derivation(semantic, True, {**semantic, key: value}, keys))
    check("derivation: edited inputs differ",
          not render.same_derivation(semantic, False, semantic, keys))
    check("derivation: no recorded metadata differs",
          not render.same_derivation(None, True, semantic, keys))

    rects = {"dpad": {"x": 100, "y": 200, "w": 50, "h": 50},
             "btn_l1": {"x": 10, "y": 20, "w": 30, "h": 40}}
    step = render.JITTER_RECT_PIXELS
    grown = copy.deepcopy(rects)
    grown["dpad"].update(y=200 - step, h=50 + step)
    check(f"rects: an edge {step} px off takes the recorded rect",
          render.canonical_rects(grown, rects, True) == rects)
    shifted = copy.deepcopy(rects)
    shifted["btn_l1"].update(x=10 - step, w=30 + 2 * step)
    check(f"rects: two edges {step} px off take the recorded rect",
          render.canonical_rects(shifted, rects, True) == rects)
    far = copy.deepcopy(rects)
    far["dpad"].update(y=200 - step - 1, h=50 + step + 1)
    check(f"rects: an edge {step + 1} px off is derived fresh",
          render.canonical_rects(far, rects, True) == far)
    check("rects: edited inputs derive fresh",
          render.canonical_rects(grown, rects, False) == grown)
    check("rects: no recorded rects derive fresh",
          render.canonical_rects(grown, None, True) == grown)
    extra = {**copy.deepcopy(rects), "btn_fn": {"x": 1, "y": 1, "w": 1, "h": 1}}
    check("rects: a different id set derives fresh",
          render.canonical_rects(extra, rects, True) == extra)


def scratch_root(work: Path) -> Path:
    """A scratch ROOT holding copies of the Brick .scad and render.py."""
    root = work / "root"
    for path in (render.MODEL, render.RENDERER):
        target = root / path.relative_to(render.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return root


def point_render_at(root: Path) -> dict:
    """Redirect render.py's module paths into ``root``; return the originals."""
    saved = {name: getattr(render, name) for name in ("ROOT", "MODEL", "RENDERER")}
    render.ROOT = root
    render.MODEL = root / saved["MODEL"].relative_to(saved["ROOT"])
    render.RENDERER = root / saved["RENDERER"].relative_to(saved["ROOT"])
    return saved


def edit_recorded(output: Path, edit) -> None:
    path = output / "semantic-model.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    edit(metadata)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@contextlib.contextmanager
def injected_ties():
    """OpenSCAD's random tie flip, forced onto every frame. Yields the captured stdout."""
    real_run_openscad = render.run_openscad

    def tie_jitter_openscad(output: Path, **kwargs) -> None:
        real_run_openscad(output, **kwargs)
        with Image.open(output) as source:
            frame = source.convert("RGB")
        x, y = TIE_PIXEL
        red, green, blue = frame.getpixel((x, y))
        frame.putpixel((x, y), (min(255, red + 2), min(255, green + 2), blue))
        frame.save(output)

    stdout = io.StringIO()
    render.run_openscad = tie_jitter_openscad
    try:
        with contextlib.redirect_stdout(stdout):
            yield stdout
    finally:
        render.run_openscad = real_run_openscad
        sys.stdout.write(stdout.getvalue())


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
def stubbed_render(neutral: Image.Image, during=None):
    """render_skin_set without OpenSCAD: hashes the inputs first like the real one,
    then returns ``neutral``, a lit copy and fixed rects. ``during`` runs inside the
    render."""
    real_render_skin_set = render.render_skin_set

    def stub(work: Path, committed: dict | None = None) -> tuple:
        inputs = render.input_hashes()
        if during is not None:
            during()
        metadata = {**inputs, "canvas": {"w": neutral.width, "h": neutral.height},
                    "controls": {"dpad": {"x": 1, "y": 2, "w": 3, "h": 4}},
                    "control_views": {"dpad": "front"}, "display_rect": None, "views": {}}
        return neutral, with_changed_pixels(neutral, 200), metadata

    render.render_skin_set = stub
    try:
        yield
    finally:
        render.render_skin_set = real_render_skin_set


def pinned_read_cases(work: Path) -> None:
    """Every file render.py hashes and then uses is read once, through one open file
    (tsp-h5ed.46.34): per site, the honest file is used, and a file replaced between
    the read and its use is refused with its path."""
    root = scratch_root(work / "pinned")
    saved = point_render_at(root)
    output = work / "pinned" / "semantic"
    try:
        with Image.open(SAMPLE_PNG) as source:
            base = source.convert("RGB")
        jittered = with_changed_pixels(base, 1)
        with stubbed_render(base):
            render.write_semantic_output(output)
        files = (render.MODEL,) + tuple(output / name for name in OUTPUTS)
        originals = {path: path.read_bytes() for path in files}
        neutral, recorded = output / OUTPUTS[0], output / OUTPUTS[2]

        def restore() -> None:
            for path, data in originals.items():
                path.write_bytes(data)

        def unchanged(paths) -> bool:
            return all(path.read_bytes() == originals[path] for path in paths)

        # The recorded PNG --semantic-output keeps: decided, hashed and kept from one read.
        sha = render.save_canonical_png(jittered, neutral, True)
        check("keep, honest semantic-neutral.png: the kept bytes' hash is returned and the file left",
              sha == hashlib.sha256(originals[neutral]).hexdigest() and unchanged([neutral]), sha)
        with replaced_after_read(neutral):
            refuses("keep, semantic-neutral.png replaced after the read: refused", neutral,
                    lambda: render.save_canonical_png(jittered, neutral, True))
        restore()

        # semantic-model.json: --semantic-output overwrites only the file it read.
        with stubbed_render(jittered):
            render.write_semantic_output(output)
        check("--semantic-output, honest semantic-model.json: written, every file as recorded",
              unchanged(files))
        with stubbed_render(jittered), replaced_after_read(recorded):
            refuses("--semantic-output, semantic-model.json replaced after the read: refused",
                    recorded, lambda: render.write_semantic_output(output))
        check("--semantic-output refused: the replacement is left and no PNG written",
              recorded.read_bytes() != originals[recorded] and unchanged(files[1:3]))
        restore()

        # The .scad: hashed before the render, re-hashed before anything is written.
        def edit_model() -> None:
            render.MODEL.write_bytes(originals[render.MODEL] + b"// edited\n")

        with stubbed_render(jittered, during=edit_model):
            refuses("--semantic-output, .scad edited during the render: refused",
                    render.MODEL, lambda: render.write_semantic_output(output))
        check("--semantic-output refused on the .scad: nothing written", unchanged(files[1:]))
        restore()
    finally:
        for name, value in saved.items():
            setattr(render, name, value)


def render_pair(work: Path) -> None:
    root = scratch_root(work)
    saved = point_render_at(root)
    output = work / "semantic"
    try:
        render.write_semantic_output(output)
        first = {name: (output / name).read_bytes() for name in OUTPUTS}

        def restore() -> None:
            for name, data in first.items():
                (output / name).write_bytes(data)

        render.write_semantic_output(output)
        for name in OUTPUTS:
            check(f"run 2: unedited .scad leaves {name} byte-identical to run 1",
                  (output / name).read_bytes() == first[name])

        # Run 3 forces the tie flip OpenSCAD makes at random onto every frame.
        with injected_ties() as stdout:
            render.write_semantic_output(output)
        check("run 3 (injected tie pixel): the jitter reached a PNG and was kept",
              "tie_jitter=kept path=" in stdout.getvalue(), stdout.getvalue())
        for name in OUTPUTS:
            check(f"run 3 (injected tie pixel): {name} byte-identical to run 1",
                  (output / name).read_bytes() == first[name])

        # A recorded rect one edge pixel off the derived one is a tie, two are not.
        dpad = json.loads(first["semantic-model.json"])["controls"]["dpad"]
        rect_step = getattr(render, "JITTER_RECT_PIXELS", 1)
        for step, kept in ((rect_step, True), (rect_step + 1, False)):
            moved = {**dpad, "y": dpad["y"] + step, "h": dpad["h"] - step}
            edit_recorded(output, lambda metadata: metadata["controls"].update(dpad=moved))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                render.write_semantic_output(output)
            sys.stdout.write(stdout.getvalue())
            written = json.loads((output / "semantic-model.json").read_text())["controls"]["dpad"]
            check(f"recorded dpad {step} px off: "
                  + ("the recorded rect is kept" if kept else "the rect is derived fresh"),
                  written == (moved if kept else dpad), f"recorded={moved} written={written}")
            check(f"recorded dpad {step} px off: tie_jitter=kept rects=dpad "
                  + ("printed" if kept else "not printed"),
                  ("tie_jitter=kept rects=dpad" in stdout.getvalue()) == kept)
            restore()

        # The same tie pixel after a render.py edit is a fresh render, not jitter.
        edit_recorded(output, lambda metadata: metadata.update(renderer_sha256="0" * 64))
        with injected_ties():
            render.write_semantic_output(output)
        for name in OUTPUTS[:2]:
            check(f"render.py edited + injected tie pixel: {name} is written",
                  (output / name).read_bytes() != first[name])
        restore()

        source = render.MODEL.read_text(encoding="utf-8")
        check("seeded mutation line is present exactly once", source.count(MUTATION[0]) == 1)
        render.MODEL.write_text(source.replace(MUTATION[0], MUTATION[1]), encoding="utf-8")
        render.write_semantic_output(output)
        check("negative: a one-line .scad mutation rewrites semantic-neutral.png",
              (output / "semantic-neutral.png").read_bytes() != first["semantic-neutral.png"])
    finally:
        for name, value in saved.items():
            setattr(render, name, value)


def main() -> int:
    openscad = os.environ.get("OPENSCAD", "openscad")
    if shutil.which(openscad) is None:
        print(f"test_render_determinism: refusing: OpenSCAD not found ({openscad})",
              file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="brick-render-determinism-") as directory:
        work = Path(directory)
        api = ("keeps_committed", "same_derivation", "inputs_unchanged", "canonical_rects",
               "SEMANTIC_DERIVATION_KEYS")
        if all(hasattr(render, name) for name in api):
            hermetic_cases(work)
        else:
            check("render.py has the tie-jitter canonicaliser (" + ", ".join(api) + ")", False)
        pinned = ("read_pinned", "ensure_pinned", "input_hashes", "ensure_inputs", "_after_read")
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
