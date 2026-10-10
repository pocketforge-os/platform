# PocketForge shell input contract v2

This directory freezes the v2 input contract consumed by the runtime
`GlyphResolver`/`ActionSource` ports (F01/F06) and by the transactional remap
flow. It separates physical positions from printed labels and semantic actions:
consumers bind positions, while glyph presentation prefers a device's printed
label and otherwise uses the named, source-owned PocketForge fallback glyph.

`fixtures/trimui-smart-pro.json` is the A133 device contract. In particular, the
TrimUI Smart Pro prints **A** at `east` and **B** at `south`, while its effective
map assigns `Activate` to east and `Back` to south. The protected `SystemMenu`
action is a single press of the unlabeled guide control. `binding-shapes.json`
records every ruled settings alternative without changing the shipped defaults.

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

### Provider protocol v1

`schemas/system-menu-provider-v1.schema.json` and
`fixtures/system-menu-provider-v1.json` define the versioned provider message
set. In addition to registration, `system_menu`, acknowledgements, and `return`,
the provider can send `shown` after the menu frame has been committed. The broker
accepts and logs `shown`; v1 does not enforce a deadline or health policy for it.

Version 1 requires only the fields shown in the fixture and receivers ignore
unknown optional fields. Adding optional fields, including a future owner-approved
`{app_id, gen, rev, items}` snapshot, is additive. Changing an existing field's
meaning or making a new field mandatory requires a new major version.

The current acknowledgement deadline remains 250 ms: it is long enough for
local scheduling jitter and short enough to keep fallback escape responsive.
The proposed 500 ms `shown` deadline, 1 s open-menu health watch, and 2 s
router-owned Menu hold are reserved vocabulary/policy only; they are not
owner-approved or enforced by this contract change.

## v1 compatibility and migration

Version 1 remains frozen at
`schemas/shell-input-contract-v1.schema.json`: it continues to identify
`SafeReturn`, `safe_return_alternatives`, `safe_return_defaults`, and the
`SafeReturn-never-unreachable` invariant exactly as before. Version 2 has a new
schema ID at `schemas/shell-input-contract-v2.schema.json`; v2 documents use
`SystemMenu`, the corresponding `system_menu_*` keys, and the stronger
`SystemMenu-and-Return-never-unreachable` invariant. Consumers must branch on
`schema_version` and must never interpret a v2 document as v1.

`validate.py` accepts both frozen representations. Its `migrate_v1()` function
is a fail-closed compatibility path: it validates v1, performs the mechanical
rename, and returns only a result that passes all v2 rules. Contracts or binding
sets which use a legal v1 value outside the ruled v2 System Menu set are rejected
with `migration-unsupported`. The one-document helper always rejects defaults
registries because it cannot also migrate their referenced contract fixtures; a
coordinated release must create the v2 fixtures and registry together. A registry
and each referenced fixture must declare the same version.

| Device identity | Physical control | Shipped binding | Presentation truth |
| --- | --- | --- | --- |
| `a523` | labeled Home, `KEY_HOMEPAGE` | Home single press | printed `Home` label |
| `a133` | unlabeled guide, `BTN_MODE` | guide single press | source-owned `pf-guide` fallback glyph |
| `fixture-buttonless` | no guide-class control | Select+Start chord | source-owned `pf-select` + `pf-start` glyphs |

The synthetic buttonless identity is a portability proof, not a descriptor under
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
moved to `fixture-buttonless` resolves to Select+Start. The typed negative fixture
`shipped-default-absent-control.json` proves that a registry entry cannot ship a
default which its own device contract lacks.

The contract is deliberately single-context/single-screen v2 data. It does not
implement input handling, remapping, UI, probing, or display topology.

Validate the schema, shipped fixtures, round trips, and typed negative cases:

```sh
python3 shell-input-contract/test_contract.py
python3 shell-input-contract/validate.py
```

Validation failures have stable reason codes suitable for CI and consumers:
`schema`, `missing-required-action`, `absent-physical-control`, and
`system-menu-cardinality` and `system-menu-collision` (with the legacy
`safe-return-*` equivalents retained for v1 documents).
The small declarative recipes under `fixtures/invalid/` are negative fixtures;
the test suite applies each to its corresponding positive contract and asserts
its reason code.
