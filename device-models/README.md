# Semantic device models

This directory is the source-owned 3D device library used by PocketForge UI
surfaces.  A model is authored in millimetres and names its physical controls
with semantic ids. Every model produces the glTF model (`skins/<id>/model.glb`)
the 3D virtual device pfvd loads and six orthographic review views of that
glb. A model with a descriptor uses the same ids as
`devices/<id>/capabilities.toml` and also produces the neutral/lit skin pair
consumed by `pf-hwprobe` and the sim; a model-only package (the Brick) has
neither yet.

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
[`trimui-smart-pro/`](trimui-smart-pro/README.md), whose seventeen semantic
controls (including the top-edge POWER key and the two volume-rocker halves)
map directly to the A133 capability descriptor. Its shared-chassis derivative
[`trimui-smart-pro-s/`](trimui-smart-pro-s/README.md) carries the TG5050
identity, cooling details and an eighteenth semantic `btn_home` control for the
A523 descriptor without redrawing the accepted TG5040 baseline.
The [`trimui-brick/`](trimui-brick/README.md) package is the independent TG3040
vertical-handheld source model. It preserves the owner-measured stepped
envelope and exposes all eighteen visible physical controls across front, rear
shoulder-shelf, and side review views; descriptor and runtime-skin integration
remain a separate post-approval task.

## From measurements to a device, in order

The cold-start walkthrough, with every command's output, is sim's
[`docs/ADD-A-DEVICE.md`](https://github.com/pocketforge-os/sim/blob/main/docs/ADD-A-DEVICE.md).
In this repository the steps are:

1. **Measure** the unit and record provenance (handbook:
   [Model a handheld](https://pocketforge-os.github.io/handbook/hardware/model-handheld/)).
2. **Model** it: `device-models/<slug>/<slug>.scad` with `CONTROL_IDS`, the
   `PART`/`CONTROL_ID`/`HIGHLIGHT` selectors and the palette tokens the
   exporter reads (`shell_rear_color`, `control_color`, `glass_color`), plus
   `render.py`, `compare.py` and a README (see the list above).
3. **Register** the package with the exporter: one `MODELS` row in
   [`export_gltf.py`](export_gltf.py) (slug, skin id, descriptor or `None`
   for a model-only package). `regen.sh` refuses an unregistered slug.
4. **Describe** it (descriptor-backed packages only):
   `devices/<id>/capabilities.toml`, schema v2 for pfvd (`[model]`, screen
   `node`, `[physical]`, `[maturity]`, optional `[[joints]]`), keys in
   [`docs/CAPABILITIES-SCHEMA.md`](../docs/CAPABILITIES-SCHEMA.md). Its
   `[skin.parts]` keys must equal `CONTROL_IDS` before the first export
   (`export_gltf.py --write` refuses a mismatch); the rect values come next.
5. **Regenerate** every derivative: `device-models/regen.sh <slug>` (next
   section). On a new descriptor-backed package the first run stops at its
   last step, the drift gate, because the descriptor's rects are not the
   rendered ones yet:

   ```text
   skin_drift=fail
     - a133: btn_east rect drift: descriptor={'x': 1300, 'y': 190, 'w': 57, 'h': 55} model-render.json={'h': 55, 'w': 57, 'x': 1326, 'y': 190}
   ```

   Copy what `render.py --write` recorded in `skins/<id>/model-render.json`
   into the descriptor: the control rects (printed as `derived_rects=`) into
   `[skin.parts]`, and `display_rect` (printed as `display_rect=`) into the
   primary screen's `display_rect` (`screens[0]`); for a skin with extra
   views, each `view_rects[<view>]=` into `[skin.views.<view>.parts]`. Then
   run `regen.sh` again; `render.py` never edits the descriptor.
6. **List** it: a `devices/catalog.toml` row (with `platform_id` when it has
   a descriptor) and, when it has a descriptor, a `ci-matrix.toml` posture
   (or none: a new descriptor auto-joins as advisory).
7. **Check** it: `python3 core/caps.py validate` (descriptors, matrix,
   catalog), `python3 device-models/check-skin-drift.py`, and pfvd's package
   report, `pfvd-cli device report --device <catalog id> --platform .`,
   whose derived rung (`planned`, `model-only`, `sim-ready`) is the most the
   descriptor and the catalog row may declare.

A **model-only** package (the Brick: `MODELS` row with descriptor `None`, no
`platform_id` in its catalog row) skips step 4 and the rect copy: `regen.sh`
skips `render.py` when the skin has no `model-render.json`, exports the glb
with the screen quad's rotation at 0, renders the six views and runs the
gates, which check its glb and views; there is no 2D skin, descriptor or
posture row. Its rung is `model-only`.

## After editing a `.scad`: `regen.sh`

**After editing a `.scad`, run `device-models/regen.sh <slug>` and commit
everything it changed; CI refuses a stale derivative.**

```bash
device-models/regen.sh trimui-smart-pro     # or trimui-smart-pro-s, trimui-brick
```

It runs, in order, `<slug>/render.py --write` (plus `--write-views` when the
skin has extra clickable views; skipped for a model-only package such as the
Brick), `export_gltf.py --model <slug> --write`,
`render_glb_views.py skins/<id>/model.glb`, then `check-skin-drift.py` and
`export_gltf.py --check`, and prints every file it changed. It refuses to start
without OpenSCAD (`OPENSCAD=<path>` overrides) or without numpy and Pillow, and
refuses a slug that is not in `export_gltf.MODELS`:

```text
regen.sh: refusing: unknown model slug 'synth-clamshell' (known: trimui-brick trimui-smart-pro trimui-smart-pro-s)
```

A run ends with the gates and the list of changed files:

```text
== 4/4 gates: check-skin-drift.py, export_gltf.py --check
skin_drift=pass models=2 devices=a133,a523 glbs=3 glb_devices=a133,a523,trimui-brick views=6
glb device=a133 triangles=67077 budget=150000
glb device=a523 triangles=81072 budget=150000
glb device=trimui-brick triangles=82626 budget=150000
glb_check=pass models=3
regen=pass slug=trimui-smart-pro skin=a133 changed=0 (outputs already current)
```

The glb and its views are deterministic for a given `.scad`, OpenSCAD and
font set. The 2D skin renders are not always byte-stable: on one host three
consecutive runs over an unedited `trimui-smart-pro` changed
`body_top.png`, `body_lit_top.png` and `model-render.json`, then restored the
committed bytes, then reported `changed=0`. When the `.scad` is unedited and
a run reports changes, inspect `git diff` and commit only what follows from
your edit (`render.py --check` has the same host-jitter caveat, see the drift
gate section).

Every file derived from a `.scad`, and the gate that refuses it stale (both
jobs live in [`.github/workflows/skin-drift.yml`](../.github/workflows/skin-drift.yml)):

| Derived file | Written by | Recorded in | Gate (CI job) |
|---|---|---|---|
| `skins/<id>/body.png`, `body_lit.png` | `render.py --write` | `model-render.json` `body_sha256`, `body_lit_sha256` | `check-skin-drift.py` (`skin-drift`) |
| `skins/<id>/body_<view>.png`, `body_lit_<view>.png` | `render.py --write-views` | `model-render.json["views"]` | `check-skin-drift.py` (`skin-drift`) |
| `skins/<id>/model-render.json` control rects, `display_rect` | `render.py --write` | `.scad` and `render.py` sha256 in the same file | `check-skin-drift.py` (`skin-drift`): equal to `devices/<id>/capabilities.toml` `[skin.parts]`, `[skin.views.*.parts]`, `display_rect` |
| `skins/<id>/model.glb` | `export_gltf.py --write` | `model-glb.json` `glb_sha256`, `source_sha256`, `exporter_sha256`, `nodes` | `check-skin-drift.py` (`skin-drift`): nodes == `CONTROL_IDS` == `[skin.parts]`; `export_gltf.py --check` and the Khronos validator (`skin-drift-glb`) |
| `skins/<id>/views/{front,back,left,right,top,bottom}.png` | `render_glb_views.py` | `model-glb.json["views"]` (`glb_sha256`, `renderer_sha256`, `files`) | `check-skin-drift.py` (`skin-drift`) and `check-skin-drift.py --views-only` (`skin-drift-glb`) |

`render.py --check` (full OpenSCAD re-render) stays a local companion, see the
drift-gate section below.

**Downstream.** pfvd consumes `skins/<id>/model.glb` through its `platform.pin`
and its package report checks `model-glb.json` against the glb, so a model fix
reaches pfvd through a `platform.pin` bump (a one-line PR). The pfvd Model
review artifact is refreshed by the coordinator from the committed
`skins/<id>/views/*.png`. No doc embeds the renders as images: the handbook's
[Model a handheld](https://pocketforge-os.github.io/handbook/hardware/model-handheld/)
chapter and sim `docs/ADD-A-DEVICE.md` refer to them by path. The copy of the
a133 descriptor in pocketforge-automation's fixtures is a deliberate test
snapshot and is not regenerated.

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

Within `fixture_interface.envelope`, `xy_bounds_mm` is always the holder-contact
shell datum. An interface may also declare `physical_xy_bounds_mm` when controls,
shoulders, triggers, or other collision geometry extend beyond that contact
shell. Keep-outs may use the larger physical bounds; contact regions, access
regions, and XY datums remain constrained to the contact shell. Omitting the
optional field preserves the original rule: every region must remain inside
`xy_bounds_mm`.

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
python3 device-models/test_fixture_snapshot.py
```

These commands are render-free and the validator is read-only. To review the
hash produced by an intentional edit:

```bash
python3 device-models/validate_fixture_contracts.py \
  --print-interface-hash \
  device-models/<slug>/fixture-contract.json
```

### Deterministic downstream snapshot

[`export_fixture_snapshot.py`](export_fixture_snapshot.py) is the only
machine-readable cross-repository export. It produces canonical JSON containing:

- the exact platform fixture-state revision and contract-schema hash;
- one sorted record per device, including aliases, with the raw contract hash
  and resolved interface hash; and
- one full, deduplicated fit-bearing payload per resolved interface hash.

The source revision is the newest **first-parent** commit that changed any
`fixture-contract.json` or the contract schema. It is deliberately not the
current visual-model `HEAD`. A later SCAD, skin, camera, label, shader, or
render-evidence commit therefore produces byte-identical snapshot output.
Changing even non-fit contract metadata changes that contract's raw hash and
the fixture-state revision; changing a fit-bearing value additionally changes
the resolved interface hash and payload. Shared-chassis device records remain
distinct while their identical interface payload is stored once.

Generate twice and verify exactly as CI does:

```bash
snapshot_dir="$(mktemp -d)"
python3 device-models/export_fixture_snapshot.py export \
  --output "$snapshot_dir/fixture-dependencies-a.json"
python3 device-models/export_fixture_snapshot.py export \
  --output "$snapshot_dir/fixture-dependencies-b.json"
python3 device-models/export_fixture_snapshot.py verify \
  --snapshot "$snapshot_dir/fixture-dependencies-a.json"
cmp "$snapshot_dir/fixture-dependencies-a.json" \
  "$snapshot_dir/fixture-dependencies-b.json"
```

Generation requires a clean Git tree and writes only outside the repository.
Snapshots are transport artifacts, not platform source: do not commit them.
Downstream automation must verify the snapshot against the named platform
revision before proposing a holder-profile update. The fixture-contract CI gate
runs the regression suite, generates twice, verifies the first result, and
byte-compares both outputs.

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

## 3D model export — `export_gltf.py` → `skins/<id>/model.glb` (tsp-h5ed.46 D4)

The simulator loads each device as a glTF 2.0 binary exported from the same
`.scad`. The `.scad` stays the source of truth; the glb is committed beside the
skin so the app never needs OpenSCAD.

```bash
python3 device-models/export_gltf.py --model trimui-smart-pro --write   # local, needs openscad
python3 device-models/export_gltf.py --all --write
python3 device-models/export_gltf.py --check                            # CI, stdlib only
python3 device-models/render_glb_views.py skins/a133/model.glb          # six review PNGs
```

| Model package | Skin dir | Descriptor |
|---|---|---|
| `trimui-smart-pro` | `skins/a133/` | `devices/a133/capabilities.toml` |
| `trimui-smart-pro-s` | `skins/a523/` | `devices/a523/capabilities.toml` |
| `trimui-brick` | `skins/trimui-brick/` | none (descriptor on hold; model-only) |

`--write` runs OpenSCAD once per part (`PART=shell` → `body`,
`PART=control CONTROL_ID=<id>` → one node per control, `PART=screen` → the
screen quad's extent), caches the STLs under `device-models/.cache/` (ignored),
and writes `skins/<id>/model.glb` plus `skins/<id>/model-glb.json` (glb, source
and exporter sha256, OpenSCAD version, node list, screens, triangle count). It
refuses a model whose `CONTROL_IDS` differ from the descriptor `[skin.parts]`.
Two limits today: the `PART=screen` probe is single-panel, so a descriptor
with more than one `[[screens]]` is refused, and no `pivot_<joint>` nodes are
written yet. The synthetic two-screen clamshell under
`tests/caps-fixtures/clamshell/` therefore has its glb written by its own
`gen_fixture.py` in the exporter's conventions (metres, `asset.extras`), and
`gen_fixture.py --check` is its drift gate.
The bytes are deterministic for a given `.scad`: OpenSCAD 2021.01 writes the
same triangles in a different order on every run, so the exporter sorts them
first. The shell's silkscreen uses the same fonts as `render.py`, so a host
with different fonts can still produce a new sha; re-export on the host that
exported last.

The glb contract (full text in the `export_gltf.py` docstring): one scene root
`body`; one child node per control id with its pivot at the footprint centre /
lowest Z; a `screen_main` quad (the descriptor `screens[].node`) with UV 0..1
and `extras.panel_rotation_deg` from the descriptor `rotation`; reserved names
`body`, `screen_*`, `pivot_*` (a future moving assembly hangs under an empty
`pivot_<joint id>` node, D4/D6); pf-mm-v1 axes in metres; smooth normals with a
30° crease; one material per part class from the `.scad` palette (OpenSCAD
2021.01 STL has no colour, so bodies are monochrome); at most 150,000
triangles.

CI (`skin-drift.yml`, job `skin-drift-glb`, no OpenSCAD): the Khronos
glTF-Validator pinned by sha256 (`gltf_validate.py --fetch`), `export_gltf.py
--check`, and `test_export_gltf.py` (hostile extra/missing node, name
mismatch, invalid glb, sha/rotation/UV/budget drift). The consistency job's
`check-skin-drift.py` adds the lockstep: every rendered skin has a
`model-glb.json`; the recorded `.scad`/exporter/glb hashes match; glb control
nodes == `.scad` `CONTROL_IDS` == descriptor `[skin.parts]`, both directions;
screen node and rotation match the descriptor. Editing a `.scad` therefore
needs every regeneration step below; `regen.sh` runs them.

`skins/<id>/views/{front,back,left,right,top,bottom}.png` are orthographic
renders of the committed glb (not the `.scad`) for the owner's visual review.
`render_glb_views.py` records them in `model-glb.json["views"]` and the gate
hashes them (next section).

## What CI validates

Every job below is render-free except `sim-suite`; none runs OpenSCAD, so the
full re-render (`render.py --check`) and `regen.sh` stay local.

| Workflow · job | Runs | On a PR touching |
|---|---|---|
| `skin-drift.yml` · `skin-drift` | `check-skin-drift.py`: `.scad`/`render.py`/PNG hashes in `model-render.json`, rects == `[skin.parts]`, `display_rect`, every view atlas, the glb lockstep (`model-glb.json` hashes; glb nodes == `CONTROL_IDS` == `[skin.parts]`; screen node and rotation) and the six glb views | `device-models/**`, `skins/**`, `devices/**` |
| `skin-drift.yml` · `skin-drift-glb` | `test_export_gltf.py`, the Khronos glTF-Validator pinned by sha256 (`gltf_validate.py`, 0 errors and 0 warnings), `export_gltf.py --check` (glb hashes, structure, triangle budget), `check-skin-drift.py --views-only` | same |
| `fixture-contract.yml` · `fixture-contract` | `validate_fixture_contracts.py`, `test_fixture_contracts.py`, `test_fixture_snapshot.py`, the snapshot exported twice, verified and byte-compared, and the PR-vs-base revision/qualification rules | `device-models/**`, `schemas/device-fixture-contract.schema.json` |
| `sim-descriptor-gate.yml` · `descriptor-matrix` | `core/caps.py matrix validate` and the matrix rows (blocking, advisory) for the next job | `devices/**`, `skins/**`, `device-models/**`, `schemas/**` |
| `sim-descriptor-gate.yml` · `sim-suite` | the pinned sim image with this PR's descriptors, running the headless control, sensor and skin suites per matrix row | same (same-repository PRs only) |
| `regression-suites.yml` · `pf-regression-suites` | `regression/run-offline.sh`, which includes `regression/caps/test_caps.py` (every shipped descriptor validates) and `test_caps_v2.py` (schema v2 rules, the catalog's declared ≤ derived rungs, `gen_fixture.py --check` for the clamshell fixture) | every PR |

Run the same checks locally from the repository root. The glb job's
validator is the pinned Khronos binary; without `GLTF_VALIDATOR` set,
`test_export_gltf.py` skips its validator test (`OK (skipped=1)`), so fetch
it the way CI does:

```bash
python3 device-models/check-skin-drift.py
tools="$(mktemp -d)"
validator="$(python3 device-models/gltf_validate.py --fetch "$tools" --print-path)"
GLTF_VALIDATOR="$validator" PF_REQUIRE_GLTF_VALIDATOR=1 python3 device-models/test_export_gltf.py
python3 device-models/gltf_validate.py --validator "$validator"
python3 device-models/export_gltf.py --check
python3 device-models/check-skin-drift.py --views-only
python3 device-models/validate_fixture_contracts.py
python3 core/caps.py validate
python3 regression/caps/test_caps_v2.py
```

The fixture-contract job's snapshot reproduction is in
[Deterministic downstream snapshot](#deterministic-downstream-snapshot);
`regression/run-offline.sh` and the sim suite run the rest.

pfvd's package report (`pfvd-cli device report`) is not a platform CI job:
pfvd's own CI runs it against the platform commit in its `platform.pin`.
