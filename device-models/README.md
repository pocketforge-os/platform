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
controls map directly to the A133 capability descriptor. Its shared-chassis
derivative [`trimui-smart-pro-s/`](trimui-smart-pro-s/README.md) carries the
TG5050 identity, cooling details and fifteenth semantic `btn_home` control for
the A523 descriptor without redrawing the accepted TG5040 baseline.

## Start a new model

Follow the PocketForge admin chapter
[Model a handheld](https://pocketforge-os.github.io/handbook/hardware/model-handheld/)
before generating a device-specific DUT holder. It separates the useful
photo-derived first pass from the later caliper-backed acceptance gate and
defines the evidence, privacy, semantic, and handoff contracts.

Codex discovers the repository skill at
[`../.agents/skills/model-handheld-device/`](../.agents/skills/model-handheld-device/SKILL.md)
when launched anywhere in this repository. Invoke it explicitly with:

```text
$model-handheld-device Build the source model for <manufacturer> <product and
model number> as device ID <id>. Start from public evidence, derive from an
accepted shared chassis when appropriate, and stop for owner visual review
before runtime-skin integration.
```

Other agents can follow the same `SKILL.md`, its evidence checklist, and its
deterministic validator directly.

## Drift gate (CI) — `check-skin-drift.py`

The model, the rendered atlas, and the descriptor rects are **one chain**: the sim
GUI and `check-skin` consume `skins/<id>/{body,body_lit}.png` +
`skins/<id>/model-render.json` and `devices/<id>/capabilities.toml [skin.parts]`,
so they must stay in lockstep. [`check-skin-drift.py`](check-skin-drift.py) is the
CI gate that keeps them from silently diverging (infra-113 §6 Phase B5, decision
D9; wired as `.github/workflows/skin-drift.yml`, advisory — the required-check flip
is Phase B2).

It is **data-driven by auto-discovery** (it globs `skins/*/model-render.json`, so
committing a model's rendered skin is all it takes to enrol a new device — no code
edit) and runs **without OpenSCAD**, so it is byte-stable and fires on every PR
touching `device-models/**`, `skins/**`, or `devices/**`. For each discovered
device it asserts that `model-render.json`'s recorded `source` / `renderer` /
`body` / `body_lit` sha256 still match the committed `.scad` / `render.py` / PNGs
(the source and renderer paths are read from the metadata itself), and that its
control rects **equal** `devices/<id>/capabilities.toml [skin.parts]` and its
`display_rect` matches. A device with only legacy bezel art (no `model-render.json`)
is simply not discovered and not gated here. Run it locally exactly as CI does:

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

## Additional clickable views — the rotatable top-edge view (tsp-65jc.27)

Beyond the front atlas, a model may carry extra **views** rendered from other
cameras so a UI surface (the sim GUI) can rotate the device and expose controls a
front-on orthographic render only shows as slivers — above all the top-edge
shoulders/triggers (and the TG5050's HOME button). A view is the same `.scad`
rendered from a `VIEW_CAMERAS` camera into its **own** neutral/lit atlas restricted
to the controls visible from that angle, carrying **no** `display_rect` (the screen
is a front-face feature).

- **Generate/regenerate** with `render.py --write-views`. This is **additive**: it
  writes only `skins/<id>/body_<view>.png` + `body_lit_<view>.png` and the
  `model-render.json["views"]` block, and refreshes the shared `source`/`renderer`
  hashes — the **front** `body.png`/`body_lit.png` and the front top-level metadata
  are never touched, so the owner-accepted front baseline stays byte-identical.
- **Descriptor:** each view adds `[skin.views.<name>]` (body/lit_body) +
  `[skin.views.<name>.parts]`. Controls not visible from a view are simply absent.
- **Drift gate:** `check-skin-drift.py` gates every view exactly like the front —
  the view PNGs must hash to what `model-render.json` recorded, and each view's
  control rects must equal `[skin.views.<name>.parts]`. Adding a view = committing
  its rendered atlas + view block; no per-device code.
- **Host note:** `render.py --check` byte-exactness is host-blocked on some GPUs
  (tsp-vevy); the drift gate proves self-consistency without OpenSCAD, so a view
  rendered on any host is drift-green. A view's silkscreen may want a canonical
  re-render before a final owner visual-OK, but that is a mechanical follow-up.
