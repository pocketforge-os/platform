# Semantic device models

This directory is the source-owned 3D device library used by PocketForge UI
surfaces.  A model is authored in millimetres, names its physical controls with
the same semantic ids as `devices/<id>/capabilities.toml`, and can produce both
human-review views and the neutral/lit skin pair consumed by `pf-hwprobe`.

Each model directory should contain:

- one documented OpenSCAD source with a fixed physical coordinate system;
- a measurement/provenance table that separates measured, published, and
  photo-derived dimensions;
- deterministic rendering and stale-artifact checks;
- semantic control selection (`PART="control"`, `CONTROL_ID="…"`) and
  highlighting (`HIGHLIGHT="…"` or `"*"`);
- pairwise-disjoint runtime rectangles and an atlas composed from individual
  highlight renders, so a rectangular crop cannot light a neighbouring part;
- a clear limitations section.  Millimetre coordinates do not turn uncertain
  photo-derived surfaces into manufacturing-tolerance geometry.

Generated PNGs remain checked in because the target app must not need OpenSCAD.
The model source and render metadata make those PNGs reproducible.  Original
owner photographs stay outside git: comparison tooling may read them, but must
write fresh PNGs without copying EXIF metadata.

The first implementation is
[`trimui-smart-pro/`](trimui-smart-pro/README.md), whose fourteen semantic
controls map directly to the A133 capability descriptor.

## Drift gate (CI) — `check-skin-drift.py`

The model, the rendered atlas, and the descriptor rects are **one chain**: the sim
GUI and `check-skin` consume `skins/<id>/{body,body_lit}.png` +
`skins/<id>/model-render.json` and `devices/<id>/capabilities.toml [skin.parts]`,
so they must stay in lockstep. [`check-skin-drift.py`](check-skin-drift.py) is the
CI gate that keeps them from silently diverging (infra-113 §6 Phase B5, decision
D9; wired as `.github/workflows/skin-drift.yml`, advisory — the required-check flip
is Phase B2).

It is **data-driven** (add a modelled device = add a row to its `MODELS` list) and
runs **without OpenSCAD**, so it is byte-stable and fires on every PR touching
`device-models/**`, `skins/**`, or `devices/**`. For each modelled device it
asserts that `model-render.json`'s recorded `source` / `renderer` / `body` /
`body_lit` sha256 still match the committed `.scad` / `render.py` / PNGs, and that
its control rects **equal** `capabilities.toml [skin.parts]` and its `display_rect`
matches. Run it locally exactly as CI does:

```bash
python3 device-models/check-skin-drift.py
```

**Coverage & the one known gap (honesty contract).** Every guarantee above is a
**strict subset** of `render.py --check`: that command recomputes the same hashes
and rects from a fresh render, so a repo that passes `render.py --check` necessarily
passes this gate. The render-free gate catches every accidental "edit one artifact,
forget to regenerate the rest" drift, but it **cannot** catch a *consistent*
hand-edit of a rect in **both** `model-render.json` and `capabilities.toml` without
re-rendering — the two files still agree and the `.scad`/PNG hashes are untouched,
so the rect silently points where the rendered atlas no longer highlights. That
narrow, semi-adversarial case is closed by running **`render.py --check` locally**
(the full OpenSCAD re-render) whenever you touch a model — see each model's README.

`render.py --check` is deliberately **not** wired into CI: it byte-compares
freshly-rendered PNGs, which cannot be a green-on-main gate (the `.scad`'s
"Ubuntu Sans" variable font is absent from Debian bookworm → different silkscreen
pixels → red on main; the render suite times out under headless software GL; and
GPU-vs-`llvmpipe` anti-aliasing risks flaky reds). A flaky gate would poison the
gate-trust infra-113 exists to build, so the full re-render stays the local
full-fidelity companion.
