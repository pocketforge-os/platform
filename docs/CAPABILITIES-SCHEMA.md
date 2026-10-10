# Device capability descriptor schema (`devices/<id>/capabilities.toml`)

Declarative **data**, not code. The NET-NEW per-variant **sibling** to
[`profile.toml`](./PROFILE-SCHEMA.md), joined to it ONLY by `device.id`. The build
profile owns kernel/gpu/bootchain/flash; **this** file owns what a device can **SENSE,
ACTUATE, and LOOK LIKE**. Validator + tooling live in `core/caps.py`
(`pf caps validate <id|--all>`); the contract is `schemas/capabilities.schema.json`
(standard JSON-Schema Draft 2020-12 — editors and the reference `jsonschema` library
validate it identically; `pf caps` itself uses a stdlib-only subset engine so it runs on
any host with Python 3.11+, like `core/profile.py`).

**One descriptor, three consumers:** the capability broker (E2/infra-101) advertises
exactly these codes/ranges; the simulator (E5/infra-104) synthesizes a `uinput` device +
renders the skin from them; CI (E7/infra-106) asserts the contract from the same file.

## Core invariants
- **descriptor = EXPECTATION; the live `EVIOCGBIT`/`EVIOCGABS` probe = GROUND TRUTH.** On
  mismatch a control renders greyed / typed `hardware-absent`, never a crash. SPIKE-0
  (`tsp-9sx.1`) reconciles the descriptor to silicon.
- **Missing hardware = ROW OMISSION**, never a fabricated row (`additionalProperties:false`
  everywhere rejects stub/`present=false` markers). The base a133 descriptor is the a523
  one MINUS the rows for hardware it lacks.
- **Both units share one Xbox-360 HID (`045e:028e`)** advertising the full button superset
  on a133 too. The descriptor is the authority for *physical, drawable* controls; the
  SPIKE-0 fidelity check is **asymmetric** (descriptor codes ⊆ probe codes; extra
  advertised-but-unwired codes are expected, not mismatches).
- **Screen geometry is render INTENT, not the panel's pixel truth.** For the kernel, panel dims
  live in the DTS; v1 descriptors do not duplicate them. `rotation` is a logical ENUM
  (`none`/`cw90`/`cw180`/`cw270`), never the per-SoC magic number (a133 `768`, a523 `0`).
  The only cross-check against the build profile is the **`device.id` JOIN**. Schema v2 adds
  OPTIONAL per-screen panel facts (`panel_px`, `fourcc`, `diagonal_in`, `active_mm`) for the
  simulator's screen contract (decision D7); the DTS stays authoritative for the kernel.

## Button naming (position / label / code / action)

Four things get conflated; the descriptor keeps them separate (the SDL3 model — our
downstream consumer moved its API from `A/B/X/Y` to positional `SOUTH/EAST/WEST/NORTH`
plus a separate per-vendor label lookup):

- **position** (`id` = `south`/`east`/`west`/`north`) — the spatial diamond slot. The
  vendor-neutral binding key: a Switch-format device differs from Xbox by DATA only.
- **label** (`label` = `"A"`/`"B"`/`"X"`/`"Y"`, or a shape) — the printed glyph, for prompts.
- **code** (`code` = `BTN_A`...) — the evdev symbol the driver EMITS (ground truth).
- **action** (confirm/cancel/jump) — NOT here; lives in the broker/SDK layer (E2). The
  descriptor carries at most a single `accept_default` hint.

Emitting the SDL `gamecontrollerdb` uses the fixed Xbox-semantic token table
(`south→a, east→b, west→x, north→y`), so the canonical X360 line is unchanged.

## Actuator semantics vs wire format (`inputs.semantics`)

`kind`/`ev_type`/`code`/`range` describe **what the kernel emits** (the wire). `semantics`
describes **what the physical actuator IS**. On most inputs they agree unambiguously —
a `button` is binary, a `stick` is analog, a `hat` is a step enum. But on `kind=trigger`
they can DIVERGE: an X360-style trigger is a proportional analog channel on the wire
(`ABS_Z`/`ABS_RZ`, 0..255) yet the physical actuator may be a plain binary switch that
fires only the endpoints. The TrimUI 5040 (a133) and 5050 (a523) L2/R2 are exactly this
case (SPIKE-0 tsp-9sx.1, 2026-07-11: full-swing endpoint values only, zero intermediates,
graze included). Setting `semantics = "binary"` records that truth in the descriptor
where all three consumers can act on it:

- **E2 capability broker / action-map** (infra-101) — may PRESENT the trigger to apps as
  a digital input (either 0 or the endpoint value; no proportional passthrough).
- **E5 simulator** (infra-104) — synthesizes endpoint-only values on a press; never a
  ramp / intermediate.
- **CI** (infra-106) — asserts endpoint-only behavior against a live capture (or an
  invariance test); an intermediate ABS value would indicate a hardware/model divergence.

`semantics` is OPTIONAL. Omitted = the natural semantics of `kind`. The validator restricts
it to `kind=trigger` because that is the one place in today's vocabulary where wire and
semantics diverge; extending to a new kind (e.g. a pressure-sensitive shoulder in the
future) is a schema change, not a descriptor licence. `pf caps emit-sdldb` does NOT consult
`semantics` — the SDL wire mapping stays the wire mapping (a2/a5), by design.

## Sections

| table | key | required | notes |
|---|---|---|---|
| (top-level) | `schema_version` | | integer; absent = 1. `2` unlocks the [schema v2](#schema-v2) keys |
| `[identity]` | `id` | ✅ | canonical id `^[a-z0-9][a-z0-9-]*$`; MUST equal the directory name AND `profile.toml [device].id` (the join) |
| | `manufacturer`, `model` | ✅ | e.g. `TrimUI` / `Smart Pro S` |
| | `codename` | | Android-picker leaf (`5040`/`5050`) |
| | `sdl_guid` | ✅ | 32 lowercase hex; the `gamecontrollerdb` key (see `pf caps emit-sdldb`, E1.4) |
| | `match` | ✅ | `{ evdev_name, vid, pid }` — hwdb-style probe match (`vid`/`pid` 4 hex) |
| `[[screens]]` | `role` | ✅ | `primary`\|`secondary` |
| | `render_canvas` | ✅ | `{ w, h }` the LANDSCAPE buffer the app draws into (e.g. 1280×720); the app must NOT pre-rotate |
| | `present` | ✅ | `landscape`\|`portrait` — the orientation the user sees |
| | `rotation` | ✅ | logical enum `none`/`cw90`/`cw180`/`cw270`; `rotation(render_canvas)` must be consistent with `present` |
| | `display_rect` | | `{ x, y, w, h }` where the live framebuffer composites on the bezel (skin/portrait frame) |
| `[[inputs]]` | `id` | ✅ | unique; `^[a-z0-9_]+$`. FACE buttons use POSITIONAL ids `south`/`east`/`west`/`north` (SDL3-aligned); other controls keep semantic ids (`start`, `l1`, `dpad`, `lstick`, `home`...). Binds to `[skin.parts.<id>]` via `skin_part` |
| | `kind` | ✅ | `button`\|`hat`\|`stick`\|`stick-click`\|`trigger` |
| | `ev_type` | ✅ | `EV_KEY`\|`EV_ABS` (must agree with the code prefix) |
| | `code` | ✅ | the evdev code the driver EMITS, comma-sep for hat/stick. xpad face buttons = `BTN_A/B/X/Y` (0x130/131/133/134); the spatial aliases `BTN_NORTH`/`BTN_WEST` share the numbers but swap X↔Y — trust `id` for position, `code` for the wire |
| | `label` | | printed glyph on the button (`"A"`/`"B"`/`"X"`/`"Y"` or a shape); for app/skin prompts. A Switch-format device swaps only `label` (+ `accept_default`), never `id`/`code`/skin |
| | `label_kind` | | `letter` (default) \| `shape` (PlayStation-style) |
| | `range` / `x` / `y` | | `{ min, max, flat?, fuzz?, resolution? }` absinfo; `trigger`→`range`, `stick`→`x`+`y` |
| | `semantics` | | `analog`\|`binary` — what the physical actuator IS, DISTINCT from the wire format described by `kind`/`ev_type`/`code`. Only meaningful on `kind=trigger` (see "Actuator semantics vs wire format" below); other kinds have unambiguous semantics from `kind` itself and the validator rejects it there |
| | `skin_part`, `ui` | | skin rect id (face buttons use positional `btn_south`...); UI hint (e.g. `slider_above`) |
| `[[sensors]]` | `id`, `kind`, `iio_device` | ✅ | `kind` ∈ accel/gyro/mag/accel+gyro/imu (+ gnss/gps, no `iio_device`; + `hinge_angle` at v2, the value a joint feeds); `iio_device` e.g. `qmi8658`. OMIT DT-but-unbound sensors until SPIKE-0 proves they bind |
| | `units`, `mount_matrix`, `ui` | | `mount_matrix` = 3×3 numbers; `ui` e.g. `tilt_bubble` |
| `[[actuators]]` | `id`, `kind` | ✅ | `kind` ∈ `rumble`\|`led_array` |
| | `ev_type`/`code`, `sysfs` | | rumble: `EV_FF`/`FF_RUMBLE` + `pwm-vibrator` |
| | `controller`, `count` | | led_array: controller name + LED count |
| `[skin]` | `body` | ✅ (for acceptance) | repo-relative PNG bezel path (source-owned schematic art or a render from a source-owned semantic device model) |
| | `lit_body` | | all-lit overlay PNG (same dims as `body`); the AVD layered model — light a control by compositing `lit_body` cropped to its rect |
| | `parts` | ✅ | `[skin.parts.<id>] = { x, y, w, h, lit? }` named rects, each inside the bezel; every `inputs.skin_part` must resolve here |
| (top-level) | `accept_default` | | default "confirm" face button id (Xbox/PS `south`, Switch-region `east`). A HINT only — full confirm/cancel/action mapping is the broker/SDK layer (E2), not this file |

Bezels are generated by `skins/generate-bezel.py <id|--all>`. Devices without a semantic
model use descriptor-authored rectangles and source-owned schematic art. Model-backed
devices render neutral plus one-control images, derive pairwise-disjoint rectangles, and
compose the shared all-lit atlas from those passes, so control geometry, neighbouring
highlights, the raster atlas, and descriptor hitboxes cannot silently drift.
See `device-models/README.md` for that reusable contract.

## Schema v2

Decision D5 (simulator epic tsp-h5ed.46), implemented in tsp-h5ed.46.3. `schema_version = 2`
unlocks the keys below, ALL optional. They exist so the 3D simulator can bind a descriptor to a
glTF model and articulate it (D6). A v1 descriptor (no `schema_version`, or `1`) validates exactly
as before; a v2 key in a v1 descriptor is `E_V2_AT_V1`, and a version above 2 is
`E_SCHEMA_VERSION`. Principle: **descriptor = presence, wiring, geometry; state = anything a
slider or the guest changes** (joint angle, lid switch value, touch points).

| table | key | required | notes |
|---|---|---|---|
| `[[screens]]` | `id` | when > 1 screen | `^[a-z0-9_]+$`; unique; a lone screen's id defaults to its `role`. Postures name screens by id |
| | `node` | | glTF node of the screen's emissive quad (UV 0..1 over the active area) |
| | `panel_px` | | `{ w, h }` native panel pixels (e.g. 720×1280 for the portrait-native a133 panel) |
| | `fourcc` | | DRM fourcc of the scanout, 4 chars (e.g. `XR24`) |
| | `diagonal_in`, `active_mm` | | panel diagonal (in) and active area `{ w, h }` (mm). dpi is DERIVED, never declared |
| | `[screens.touch]` | | presence = touchscreen: `protocol` `mt-b`\|`st`, `slots` (mt-b only), `source` (its evdev node, never the primary gamepad node), `x`/`y`/`pressure` absinfo |
| `[physical]` | `envelope_mm` | ✅ | body envelope `{ w, h, d }` in mm (>0), frame pf-mm-v1. Per-panel facts live on `[[screens]]` |
| | `mass_g`, `source` | | mass (>0; omit when unmeasured); provenance strings per field |
| `[model]` | `glb` | ✅ | root-relative path of the glTF 2.0 binary; must exist and parse. Like `source` and catalog `package`, it must resolve INSIDE the root: absolute paths, `..` escapes and symlinks pointing outside are refused (symlinks staying inside are followed) |
| | `frame` | ✅ | `pf-mm-v1`: millimetres, X left→right, Y bottom→top, Z rear→front |
| | `naming` | ✅ | `pf-semantic-v1`: every `inputs[].skin_part`, `screens[].node` and `joints[].node` names exactly one glb node; a joint's node is `pivot_<joint id>` |
| | `source` | | model package directory (e.g. `device-models/trimui-smart-pro`) |
| | (no sha) | | the glb's sha256 lives in `skins/<id>/model-glb.json` (written by `export_gltf.py`, owned by the drift gate; the `E_MODEL_SHA` message still names `model-render.json`); any `*sha*` key here is `E_MODEL_SHA` |
| `[[joints]]` | `id` | ✅ | `^[a-z0-9_]+$`, unique |
| | `kind` | ✅ | `hinge`\|`swivel` (values in degrees) \| `slide` (values in mm) |
| | `node` | ✅ | the glTF pivot node; its children are the moving assembly |
| | `axis` | ✅ | `[x, y, z]` in the model frame, non-zero: rotation axis (right-hand rule, positive value = positive rotation) or slide direction |
| | `range` | ✅ | `[min, max]`, min < max |
| | `rest` | | joint value the glb is authored at; default `range[0]` |
| | `default`, `detents` | | start value and snap values, all inside `range` |
| | `parent` | | joint whose moving assembly carries this pivot (chains); acyclic |
| | `drive` | | `{ joint, map = [[in, out], ...] }`: this joint FOLLOWS another by a piecewise-linear map (inputs strictly increasing and inside the source range, outputs inside this range); a driven joint has no postures and no slider; acyclic |
| | `sensor` | | id of a `[[sensors]]` row of kind `hinge_angle` that receives the value |
| | `switches` | | `[{ ev_type = "EV_SW", code = "SW_LID", source, active = [lo, hi], hysteresis }]`: the switch reads 1 while the joint value is inside `active` (a sub-range of `range`); `source` is its evdev node, never the primary gamepad node |
| `[[joints.postures]]` | `id`, `range` | ✅ | named sub-range of the joint (ids unique per joint) |
| | `active_screens` | | screen ids lit in this posture; `[]` = all off; absent = all on |
| | `reachable_inputs` | | input ids still pickable; absent = all |
| | `screen_rotation` | | `{ <screen id> = none\|cw90\|cw180\|cw270 }`, relative to the screen's declared `rotation` |
| `[maturity]` | `declared` | ✅ | `planned`\|`model-only`\|`sim-ready` (D18), bounded by the derived rung |

**Posture semantics.** Postures are UI/simulator groupings over ONE joint value; hardware has
no posture concept. In document order they must TILE the joint range exactly: the first starts
at `range[0]`, each starts where the previous ends, the last ends at `range[1]`; each covers
`[lo, hi)` and the last `[lo, hi]`. So every joint value falls in exactly one posture. Switch
events are NOT posture side effects: they are thresholds on the joint value (`switches`), so the
lid switch fires at the same angle however the user got there.

**Maturity (descriptor).** The derived rung is the highest one the descriptor's own content
supports: sim-ready requires [model], a node for every screen, and a skin_part on every input
except class = "system" inputs, which the simulator reaches through its toolbar and control
plane rather than the 3D model; `model-only` = `[model]` present with some binding missing;
`planned` = no `[model]`. `declared` above the derived rung is `E_MATURITY_EXCEEDS`.

**Rule names.** Every v2 error starts with a stable name: `E_SCHEMA_VERSION`, `E_V2_AT_V1`,
`E_SCREEN_PRIMARY` (exactly one primary and it is `screens[0]`: consumers index `screens[0]`),
`E_SCREEN_ID`, `E_SCREEN_TOUCH`, `E_PHYSICAL`, `E_MODEL_SHA`, `E_MODEL_GLB`, `E_MODEL_SOURCE`,
`E_MODEL_NODE`, `E_JOINT_DUPLICATE` (id or pivot node), `E_JOINT_NODE`, `E_JOINT_AXIS`,
`E_JOINT_RANGE`, `E_JOINT_REF` (parent, sensor), `E_JOINT_SWITCH`, `E_JOINT_DRIVE`,
`E_POSTURE_TILING`, `E_POSTURE_DUPLICATE`, `E_POSTURE_REF`, `E_MATURITY_EXCEEDS`.

Not in v2 yet: `EV_SW`/`EV_REL` `[[inputs]]` rows (switch/wheel kinds). The simulator's input
synthesiser rejects `EV_SW` today, so these wait for its v2 (D8). A lid switch is expressed on
the joint instead.

**Reference fixture.** `tests/caps-fixtures/clamshell/` is a SYNTHETIC two-screen clamshell
(lid hinge 0–180°, postures `closed` [0,10) / `half` [10,150) / `open` [150,180], `SW_LID`
active in [0,10], a touch bottom screen, 12 inputs), with a generated PNG skin and a tiny glb
(`gen_fixture.py`, `--check` = drift gate) in the exporter's convention (metres, `asset.extras`
frame/units/naming as `device-models/export_gltf.py` writes; see the fixture's README). It lives outside `devices/`, so it is never in
`ci-matrix.toml`, `pf build` or the catalog:
`pf caps --root tests/caps-fixtures/clamshell validate`.

## Device catalog (`devices/catalog.toml`)

One `[[devices]]` row per retail product (D17), schema `schemas/device-catalog.schema.json`,
`schema_version = 1`. Listed with `pf caps catalog [list|validate] [--format tsv|json]` and
checked by `pf caps validate` (no id) / `--all`.

| key | required | notes |
|---|---|---|
| `id` | ✅ | product slug `^[a-z0-9][a-z0-9-]*$`, unique (`E_CATALOG_DUPLICATE`) |
| `manufacturer`, `name` | ✅ | marketing name (`TrimUI` / `Smart Pro`); WARN if it disagrees with the descriptor's `identity` |
| `code_name` | | the maker's code name (`TG5040`, `TG5050`, `TG3040`) |
| `platform_id` | | the `devices/<dir>` with the descriptor; must have a `capabilities.toml` and must not be a build variant (`[device].base`) (`E_CATALOG_REF`). Variants are derived, never listed |
| `package` | | model package directory (`device-models/<slug>`); must exist inside the root (`E_CATALOG_REF`) |
| `maturity` | ✅ | declared rung `planned`\|`model-only`\|`sim-ready` |

Derived rung per row: `sim-ready` = `platform_id`'s descriptor validates AND the package exists;
`model-only` = the package exists; `planned` = neither. `maturity` above the derived rung is
`E_CATALOG_MATURITY`; below it is allowed (the X55 is declared `planned` while its package holds
only the fixture reference model). Hardware verification is not a rung (D18).

## What `pf caps validate` checks
1. **Schema** (structure, types, enums, patterns, `additionalProperties:false`).
2. **`device.id` JOIN** — `identity.id` == directory == `profile.toml [device].id` (the sole build-profile cross-check; geometry stays in the DTS).
3. **Codes** — every `code` is a known Linux input-event-code; `ev_type` ⇄ code prefix; `kind` ⇄ code shape; FF codes for actuators.
4. **Ranges** — `min ≤ max`, `flat ≤ span`.
5. **Geometry coherence** — `rotation(render_canvas)` matches `present` (catches a forgotten rotation / pre-rotated app).
6. **Skin bounds** — `body` is a real PNG; every part rect + `display_rect` fits the bezel; every `skin_part` reference resolves; lit overlays exist (warn).
7. **Schema v2** (when `schema_version = 2`) — the [rules above](#schema-v2).
8. **With no id or `--all`** — also the CI gate matrix and the device catalog. Under `--root`
   (a fixture tree) a missing `ci-matrix.toml`/`catalog.toml` is a SKIP; in the repo it is an error.

Self-tests: `python3 regression/caps/test_caps.py` (device-free; asserts the positive path,
a battery of negatives, and agreement with the reference `jsonschema` when installed) and
`python3 regression/caps/test_caps_v2.py` (the v2 rules and the catalog: every rule's hostile
addition next to its positive control in one invocation). Both run in `regression/run-offline.sh`.

See `devices/a133/capabilities.toml` (base set) and `devices/a523/capabilities.toml`
(= a133 + pure data rows: home/L3/R3/imu/rumble) for the authored descriptors.
