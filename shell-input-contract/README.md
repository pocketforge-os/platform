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
is the deterministic compatibility path: validate v1, set `schema_version` to
2, rename the protected action and the one representation-specific top-level
key, update the invariant, then validate the v2 result. Tests cover all three
document shapes in both versions and prove that migration yields the shipped v2
fixtures.

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
