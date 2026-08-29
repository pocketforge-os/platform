# PocketForge shell input contract v1

This directory freezes the v1 input contract consumed by the runtime
`GlyphResolver`/`ActionSource` ports (F01/F06) and by the transactional remap
flow. It separates physical positions from printed labels and semantic actions:
consumers bind positions, while glyph presentation prefers a device's printed
label and otherwise uses the named, source-owned PocketForge fallback glyph.

`fixtures/trimui-smart-pro.json` is the A133 device contract. In particular, the
TrimUI Smart Pro prints **A** at `east` and **B** at `south`, while its effective
map assigns `Activate` to east and `Back` to south. The protected `SafeReturn`
action is a single press of the unlabeled guide control. `binding-shapes.json`
records every ruled settings alternative without changing the shipped defaults.

## Per-device Safe Return defaults

`fixtures/safe-return-defaults.json` is the identity-keyed source of contract
truth. Its entries reference the repository device descriptors and full contract
fixtures; the validator runs each full fixture through the same physical-presence,
required-action, and cross-context collision checks as the A133 contract.

| Device identity | Physical control | Shipped binding | Presentation truth |
| --- | --- | --- | --- |
| `a523` | labeled Home, `KEY_HOMEPAGE` | Home single press | printed `Home` label |
| `a133` | unlabeled guide, `BTN_MODE` | guide single press | source-owned `pf-guide` fallback glyph |
| `fixture-buttonless` | no guide-class control | Select+Start chord | source-owned `pf-select` + `pf-start` glyphs |

The synthetic buttonless identity is a portability proof, not a descriptor under
`devices/` and not a claim about currently shipped PocketForge hardware.

## Normative device-portability re-resolution rule

Safe Return bindings are keyed by device identity. At boot or whenever device
identity changes, a consumer **MUST** compare every control referenced by the
stored binding with the current device's `physical_controls`. If any referenced
control is absent, the consumer **MUST** replace the effective binding with the
current device's shipped default and surface a one-time, honest notice that the
binding changed. The stale binding must not remain effective silently. SafeReturn
is **NEVER** permitted to become unreachable.

The registry carries two machine-checkable portability proofs: an A523 Home
binding moved to A133 resolves to the A133 guide default, and a guide binding
moved to `fixture-buttonless` resolves to Select+Start. The typed negative fixture
`shipped-default-absent-control.json` proves that a registry entry cannot ship a
default which its own device contract lacks.

The contract is deliberately single-context/single-screen v1 data. It does not
implement input handling, remapping, UI, probing, or display topology.

Validate the schema, shipped fixtures, round trips, and typed negative cases:

```sh
python3 shell-input-contract/test_contract.py
python3 shell-input-contract/validate.py
```

Validation failures have stable reason codes suitable for CI and consumers:
`schema`, `missing-required-action`, `absent-physical-control`, and
`safe-return-collision`.
The small declarative recipes under `fixtures/invalid/` are negative fixtures;
the test suite applies each to its corresponding positive contract and asserts
its reason code.
