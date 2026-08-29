# PocketForge shell input contract v1

This directory freezes the v1 input contract consumed by the runtime
`GlyphResolver`/`ActionSource` ports (F01/F06) and by the transactional remap
flow. It separates physical positions from printed labels and semantic actions:
consumers bind positions, while glyph presentation prefers a device's printed
label and otherwise uses the named, source-owned PocketForge fallback glyph.

`fixtures/trimui-smart-pro.json` is the shipped default. In particular, the
TrimUI Smart Pro prints **A** at `east` and **B** at `south`, while its effective
map assigns `Activate` to east and `Back` to south. The protected `SafeReturn`
action is a single press of the unlabeled guide control. `binding-shapes.json`
records every ruled settings alternative without changing that default.

The contract is deliberately single-context/single-screen v1 data. It does not
implement input handling, remapping, UI, probing, or display topology.

Validate the schema, shipped fixtures, round trips, and typed negative cases:

```sh
python3 shell-input-contract/test_contract.py
python3 shell-input-contract/validate.py
```

Validation failures have stable reason codes suitable for CI and consumers:
`schema`, `missing-required-action`, and `safe-return-collision`.
The small declarative recipes under `fixtures/invalid/` are negative fixtures;
the test suite applies each to the shipped contract and asserts its reason code.
