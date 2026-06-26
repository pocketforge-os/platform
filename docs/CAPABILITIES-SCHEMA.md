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
| `[[inputs]]` | `id` | ✅ | unique; `^[a-z0-9_]+$`; binds to `[skin.parts.<id>]` via `skin_part` |
| | `kind` | ✅ | `button`\|`hat`\|`stick`\|`stick-click`\|`trigger` |
| | `ev_type` | ✅ | `EV_KEY`\|`EV_ABS` (must agree with the code prefix) |
| | `code` | ✅ | canonical Linux-Gamepad-spec code(s), comma-sep for hat/stick (`BTN_SOUTH`, `ABS_HAT0X,ABS_HAT0Y`, `ABS_X,ABS_Y`) |
| | `range` / `x` / `y` | | `{ min, max, flat?, fuzz?, resolution? }` absinfo; `trigger`→`range`, `stick`→`x`+`y` |
| | `skin_part`, `ui` | | skin rect id; UI hint (e.g. `slider_above`) |
| `[[sensors]]` | `id`, `kind`, `iio_device` | ✅ | `kind` ∈ accel/gyro/mag/accel+gyro/imu; `iio_device` e.g. `qmi8658`. OMIT DT-but-unbound sensors until SPIKE-0 proves they bind |
| | `units`, `mount_matrix`, `ui` | | `mount_matrix` = 3×3 numbers; `ui` e.g. `tilt_bubble` |
| `[[actuators]]` | `id`, `kind` | ✅ | `kind` ∈ `rumble`\|`led_array` |
| | `ev_type`/`code`, `sysfs` | | rumble: `EV_FF`/`FF_RUMBLE` + `pwm-vibrator` |
| | `controller`, `count` | | led_array: controller name + LED count |
| `[skin]` | `body` | ✅ (for acceptance) | repo-relative PNG bezel path (original art, traced from the FCC public-record photos) |
| | `lit_body` | | all-lit overlay PNG (same dims as `body`); the AVD layered model — light a control by compositing `lit_body` cropped to its rect |
| | `parts` | ✅ | `[skin.parts.<id>] = { x, y, w, h, lit? }` named rects, each inside the bezel; every `inputs.skin_part` must resolve here |

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
