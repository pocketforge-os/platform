# PocketForge shell input contract v3

This directory freezes the input contract consumed by the runtime
`GlyphResolver`/`ActionSource` ports (F01/F06) and by the transactional remap
flow. It separates physical positions from printed labels and semantic actions:
consumers bind positions, while glyph presentation prefers a device's printed
label and otherwise uses the named, source-owned PocketForge fallback glyph.

`fixtures/trimui-smart-pro.json` is the A133 device contract. In particular, the
TrimUI Smart Pro prints **A** at `east` and **B** at `south`, while its effective
map assigns `Activate` to east and `Back` to south. The protected `SystemMenu`
action is a single press of the unlabeled guide control. `binding-shapes.json`
records every ruled settings alternative without changing the shipped defaults.

## v3: device classes, keyboard and pointer contexts (tsp-ihne1.3)

Version 3 is the device input profile generation. It keys bindings on the retail
product, not the chip (the TrimUI Brick shares the A133 but has no sticks), and
carries every action ruled by the every-menu spec §4.1 (on-screen keyboard) and
§4.3.1 (pointer buttons).

- **Positions** grow from 12 to 20: `l3`, `r3` (present only when the device has
  stick clicks; adjudication D4-M8) and `dpad_up`, `dpad_down`, `dpad_left`,
  `dpad_right`, `lstick`, `rstick`. D-pad and stick controls carry no
  `input_code` (they are not `BTN_*`/`KEY_*` rows).
- **Binding shapes** gain `stick_axis` (one stick control plus `axis:
  horizontal|vertical`), `stick_direction` (one stick control plus `direction:
  up|down|left|right`) and `on_screen` (no controls — the action exists as a key
  on the keyboard surface itself).
- **Contexts** are ruled: `shell`, `search`, `global`, `osk`, `osk.edit`,
  `pointer`. `osk.num` is an inheriting context (it reuses `osk/Type`,
  `osk/Close`, `osk/Backspace`, `osk/Commit`) and must never carry mappings of
  its own (`inherited-context-mapping`). Action names are only legal in their
  ruled contexts (`action-context-mismatch`); `Back` legitimately exists in
  `shell`, `osk.edit` and `pointer`.
- **Contracts** declare `device_class` (`two_stick`, `no_stick`, `minimal`) and
  v3 adds `Start` to the required actions (`global/Start`, single press) so the
  platform contract and the runtime's protected-action set agree.

`fixtures/device-class-defaults.json` is the shipped per-class binding table —
the device-class defaults the settings "Reset to default" action restores. A v3
contract's `osk`, `osk.edit` and `pointer` mappings must equal its class table
exactly: an entry with a binding must appear with that binding
(`class-default-mismatch`), a `null` entry must be absent
(`unexpected-class-action` when present), and a missing non-null keyboard entry
is `unreachable-keyboard-action`.

Reachability and protection rules (every-menu spec §4.1/§4.2):

- Every keyboard action (`osk`, `osk.edit`) must resolve to a physical binding
  on a present control or to `on_screen`; the validator fails any device where a
  keyboard action is unreachable (`unreachable-keyboard-action`), like the
  existing rule for the System Menu.
- `osk/Type`, `osk/Close`, `osk/Backspace`, `osk/Space` and `osk/SuggestPick`
  must keep a **physical** binding on every class (rule P2 —
  `keyboard-action-requires-physical`). `osk/Shift`, `osk/Symbols`,
  `osk/Commit` and the cursor keys may drop to on-screen-only because those keys
  always exist on the keyboard surface.
- `on_screen` is only legal in the keyboard contexts
  (`on-screen-outside-keyboard`).
- A keyboard action may not use the control the System Menu is bound to
  (`menu-reserved-control`); the ruled System Menu bindings themselves stay
  reserved from every application action, as in v2.

Fixtures: `trimui-smart-pro.json` (a133, `two_stick`), `trimui-smart-pro-s.json`
(a523, `two_stick` with `home`, `l3`, `r3`), `fixture-no-stick.json` (synthetic
Brick-like `no_stick`: faces, D-pad, L1/R1, Start/Select, no sticks, no
shoulders beyond L1/R1, SystemMenu as the Select+Start chord) and
`fixture-minimal.json` (synthetic `minimal`: four faces, D-pad, Start, Select).
The synthetic identities are portability proofs, not claims about shipped
hardware; the Brick descriptor itself stays on owner HOLD.

### Registry cross-checks against the device descriptors

For non-synthetic registry entries the validator opens the referenced
`devices/<id>/capabilities.toml` (schema v3) and fails when

- `input_profile.device_class` disagrees with the contract's `device_class`
  (`device-class-mismatch`), or
- `accept_default` is not the contract's `shell/Activate` position
  (`accept-default-mismatch`). This is X18 made mechanical: the a133/a523
  chassis is Nintendo-arranged, the printed **A** is the `east` position, and the
  confirm hint must name the printed Accept button.

### X19 pointer precedence (normative)

A user remap is a **position translation applied before** an app's
`pf_pointer_config.by_position` claims: when an app asks for `east`, it gets the
control the *user's* contract currently binds to that position's semantic action
— the app's `east` means "the user's Activate control". An app's own pointer
claims win only for the buttons it claims; a press of the Accept control on a
text field always opens the on-screen keyboard whatever `pointer/LeftClick` is
bound to. Remap edits apply live at commit: the router re-resolves the running
app's `by_position` claims through the new translation (adjudication D2-G7).

### X16 router-owned remap document

User remaps live in one system-owned document
(`/var/lib/pocketforge/input/remaps.json`), keyed per device identity and served
by the input router; the shell and Settings write through the router (or a
prefs-policy writer), never into their own state directories. The legacy
`<shell state dir>/remaps.json` is migrated on first load; see the runtime
`pf-input-map` crate for the store and migration rules.

## Per-device System Menu defaults

`fixtures/safe-return-defaults.json` is the identity-keyed source of contract
truth. Its entries reference the repository device descriptors and full contract
fixtures; the validator runs each full fixture through the same physical-presence,
required-action, and cross-context collision checks as the A133 contract.

`SystemMenu` is a protected system action, never application input. A Menu press
is offered to the registered system-menu provider as `system_menu`; the provider
must acknowledge within `SYSTEM_MENU_ACK_TIMEOUT` (250 ms). No registration, an
unhealthy provider, an invalid acknowledgement, or expiry of that deadline uses
the existing `safe_return` authority RPC directly. The menu's **Return** item
uses that same RPC and state machine, so there is one return implementation. This
keeps return reachable before the provider ships and while it is crashed or hung.
`open keyboard` is a declared future item only; this contract invents no others.

## Frozen generations and migration

Version 1 remains frozen at
`schemas/shell-input-contract-v1.schema.json`: it continues to identify
`SafeReturn`, `safe_return_alternatives`, `safe_return_defaults`, and the
`SafeReturn-never-unreachable` invariant exactly as before. Version 2 is frozen at
`schemas/shell-input-contract-v2.schema.json`; v2 documents use `SystemMenu`, the
corresponding `system_menu_*` keys, and the stronger
`SystemMenu-and-Return-never-unreachable` invariant. Consumers must branch on
`schema_version` and must never interpret a document of one version as another.
Byte-frozen v1 and v2 copies of every shipped document live under
`fixtures/frozen/v1/` and `fixtures/frozen/v2/`; the test suite revalidates them
and replays the migrations against them.

`validate.py` accepts all three representations. Its `migrate_v1()` function
is a fail-closed compatibility path: it validates v1, performs the mechanical
rename, and returns only a result that passes all v2 rules. Contracts or binding
sets which use a legal v1 value outside the ruled v2 System Menu set are rejected
with `migration-unsupported`. The one-document helper always rejects defaults
registries because it cannot also migrate their referenced contract fixtures; a
coordinated release must create the fixtures and registry together. A registry
and each referenced fixture must declare the same version.

`migrate_v2_to_v3()` is deliberately fail-closed (`migration-unsupported`): v3
adds the class table, the new contexts and the new positions, which no mechanical
rename can invent. The v3 release ships new fixtures and a new registry together,
and old readers must keep reading the frozen v2 documents until every consumer
moves.

| Device identity | Physical control | Shipped binding | Presentation truth |
| --- | --- | --- | --- |
| `a523` | labeled Home, `KEY_HOMEPAGE` | Home single press | printed `Home` label |
| `a133` | unlabeled guide, `BTN_MODE` | guide single press | source-owned `pf-guide` fallback glyph |
| `fixture-no-stick` | no guide-class control | Select+Start chord | source-owned `pf-select` + `pf-start` glyphs |
| `fixture-minimal` | no guide-class control | Select+Start chord | source-owned `pf-select` + `pf-start` glyphs |
| `fixture-buttonless` (frozen v1/v2) | no guide-class control | Select+Start chord | source-owned `pf-select` + `pf-start` glyphs |

The synthetic identities are portability proofs, not descriptors under
`devices/` and not a claim about currently shipped PocketForge hardware.

## Normative device-portability re-resolution rule

System Menu bindings are keyed by device identity. At boot or whenever device
identity changes, a consumer **MUST** compare every control referenced by the
stored binding with the current device's `physical_controls`. If any referenced
control is absent, the consumer **MUST** replace the effective binding with the
current device's shipped default and surface a one-time, honest notice that the
binding changed. The stale binding must not remain effective silently. SystemMenu
is **NEVER** permitted to become unreachable or application-rebindable. Through
its Return item or fail-safe fallback, return is **NEVER** permitted to become
unreachable.

The registry carries two machine-checkable portability proofs: an A523 Home
binding moved to A133 resolves to the A133 guide default, and a guide binding
moved to `fixture-minimal` resolves to Select+Start. The typed negative fixture
`shipped-default-absent-control.json` proves that a registry entry cannot ship a
default which its own device contract lacks.

The contract is deliberately single-screen data. It does not implement input
handling, remapping, UI, probing, or display topology.

Validate the schema, shipped fixtures, round trips, and typed negative cases:

```sh
python3 shell-input-contract/test_contract.py
python3 shell-input-contract/validate.py
```

Validation failures have stable reason codes suitable for CI and consumers:
`schema`, `missing-required-action`, `absent-physical-control`,
`system-menu-cardinality`, `system-menu-collision` (with the legacy
`safe-return-*` equivalents retained for v1 documents), and the v3 codes
`unknown-device-class`, `unknown-context`, `inherited-context-mapping`,
`action-context-mismatch`, `duplicate-mapping`, `menu-reserved-control`,
`on-screen-outside-keyboard`, `unreachable-keyboard-action`,
`keyboard-action-requires-physical`, `class-default-mismatch`,
`unexpected-class-action`, `device-class-mismatch`, `accept-default-mismatch`
and `migration-unsupported`.
The small declarative recipes under `fixtures/invalid/` are negative fixtures;
the test suite applies each to its corresponding positive contract and asserts
its reason code.
