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

## Fixture contracts — the manufacturing handoff

The semantic `.scad` model is intentionally **not** the input to a pressure fit,
clamp, or DUT carrier. A model package may additionally carry
`fixture-contract.json`, validated by
[`schemas/device-fixture-contract.schema.json`](../schemas/device-fixture-contract.schema.json).
That file is the explicit, evidence-backed handoff to `test-node-hw`:

- a fixed millimetre coordinate system and measured/nominal envelope;
- local contact-depth facts or honest fit-derived proxies;
- allowed contact regions plus control, port, vent, optical and cable
  keep-outs;
- service/access regions, optical/mechanical datums and clearance
  requirements;
- per-field provenance, confidence and unresolved measurements; and
- a qualification state scoped to the exact interface features physically
  exercised.

There are two contract forms. A `fixture_interface` owns complete fit-bearing
data. A `shared_chassis_alias` carries its own product/device identity but
resolves a sibling contract and must have the exact same interface hash. An
alias is forbidden from declaring a fit-relevant delta; make a new full
contract when the enclosure or contact interface actually differs.

The current examples are the canonical
[`trimui-smart-pro/fixture-contract.json`](trimui-smart-pro/fixture-contract.json)
and the
[`trimui-smart-pro-s/fixture-contract.json`](trimui-smart-pro-s/fixture-contract.json)
shared-chassis alias. Their physical qualification is limited to the accepted
six-hook contact windows, rear clearance, central service access and display
visibility recorded by `tsp-bcx.21.22`. The contracts explicitly leave exact
edge-depth variation and the full Z/control/port/vent envelope unresolved.

### Identity and invalidation

`fixture_interface_sha256` is the content identity consumed by downstream
holder profiles. Its versioned canonicalization includes only the coordinate
system and fit-bearing `fixture_interface` payload. It normalizes object-key
order, decimal spelling/signed zero, ID-keyed collection order and set-like
reference order. It deliberately excludes:

- the semantic OpenSCAD source and rendered skins;
- product prose, evidence notes and unresolved-measurement prose;
- qualification/acceptance metadata; and
- `interface_revision`, which is the human-readable monotonic revision rather
  than geometry identity.

Therefore a label, shader, camera, visual control or skin change does not
invalidate a fixture. A changed coordinate, range, tolerance, contact,
keep-out, access region, datum or clearance changes the hash. PR comparison
also requires the revision to increase when that hash changes, rejects a
meaningless revision bump when it does not, and forces a previously qualified
interface back to `unqualified` unless new physical acceptance evidence is
recorded.

Validate every discovered contract and run its regression suite with:

```bash
python3 device-models/validate_fixture_contracts.py
python3 device-models/test_fixture_contracts.py
```

Both commands are render-free and the validator is read-only. To review the
hash produced by an intentional edit:

```bash
python3 device-models/validate_fixture_contracts.py \
  --print-interface-hash \
  device-models/<slug>/fixture-contract.json
```

Do not treat that output as permission to preserve qualification. For an
intentional fit change:

1. edit the interface and increment `interface_revision`;
2. record the reviewed hash and set qualification to `unqualified`;
3. let the downstream holder-profile validation show the geometric impact;
4. print the coupon or affected parts and obtain explicit physical acceptance;
5. only then record the new acceptance reference and qualified hash.

Generated STLs remain owned by `test-node-hw`; they are never committed here.
Regenerating an already accepted holder must require only committed sources,
contracts and toolchains—not an AI model. An agent may help author a new
contract or retention family, but the resulting data and code become the
reproducible interface.

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
