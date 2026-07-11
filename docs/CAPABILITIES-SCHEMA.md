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
- **Screen geometry is render INTENT, not the panel's pixel truth.** Panel dims live in the
  kernel DTS and are NOT duplicated here. `rotation` is a logical ENUM
  (`none`/`cw90`/`cw180`/`cw270`), never the per-SoC magic number (a133 `768`, a523 `0`).
  The only cross-check against the build profile is the **`device.id` JOIN**.

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
| `[identity]` | `id` | ✅ | canonical id; MUST equal the directory name AND `profile.toml [device].id` (the join) |
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
| `[[sensors]]` | `id`, `kind`, `iio_device` | ✅ | `kind` ∈ accel/gyro/mag/accel+gyro/imu; `iio_device` e.g. `qmi8658`. OMIT DT-but-unbound sensors until SPIKE-0 proves they bind |
| | `units`, `mount_matrix`, `ui` | | `mount_matrix` = 3×3 numbers; `ui` e.g. `tilt_bubble` |
| `[[actuators]]` | `id`, `kind` | ✅ | `kind` ∈ `rumble`\|`led_array` |
| | `ev_type`/`code`, `sysfs` | | rumble: `EV_FF`/`FF_RUMBLE` + `pwm-vibrator` |
| | `controller`, `count` | | led_array: controller name + LED count |
| `[skin]` | `body` | ✅ (for acceptance) | repo-relative PNG bezel path (original art, traced from the FCC public-record photos) |
| | `lit_body` | | all-lit overlay PNG (same dims as `body`); the AVD layered model — light a control by compositing `lit_body` cropped to its rect |
| | `parts` | ✅ | `[skin.parts.<id>] = { x, y, w, h, lit? }` named rects, each inside the bezel; every `inputs.skin_part` must resolve here |
| (top-level) | `accept_default` | | default "confirm" face button id (Xbox/PS `south`, Switch-region `east`). A HINT only — full confirm/cancel/action mapping is the broker/SDK layer (E2), not this file |

Bezels are generated from the descriptor's own rects by `skins/generate-bezel.py <id|--all>`
(original schematic art traced from the FCC external-photo proportions — body.png and the
rects cannot drift). Real photographic art may replace `body.png`/`body_lit.png` later
without touching the rects.

## What `pf caps validate` checks
1. **Schema** (structure, types, enums, patterns, `additionalProperties:false`).
2. **`device.id` JOIN** — `identity.id` == directory == `profile.toml [device].id` (the sole build-profile cross-check; geometry stays in the DTS).
3. **Codes** — every `code` is a known Linux input-event-code; `ev_type` ⇄ code prefix; `kind` ⇄ code shape; FF codes for actuators.
4. **Ranges** — `min ≤ max`, `flat ≤ span`.
5. **Geometry coherence** — `rotation(render_canvas)` matches `present` (catches a forgotten rotation / pre-rotated app).
6. **Skin bounds** — `body` is a real PNG; every part rect + `display_rect` fits the bezel; every `skin_part` reference resolves; lit overlays exist (warn).

Self-test: `python3 regression/caps/test_caps.py` (device-free; asserts the positive path,
a battery of negatives, and agreement with the reference `jsonschema` when installed).

See `devices/a133/capabilities.toml` (base set) and `devices/a523/capabilities.toml`
(= a133 + pure data rows: home/L3/R3/imu/rumble) for the authored descriptors.
