# regression/caps/fixtures/

Vendored capture fixtures for the SPIKE-0 (tsp-9sx.1) descriptor↔probe diff.

## `a523-capture.json`

A capture-shaped synthetic gamepad probe for the a523. Seeded from the E5
sim's `sim/synth/baseline/a523/capture.json` (Xbox-360 HID superset via
`045e:028e`), augmented with `BTN_TL2` + `BTN_TR2` so the pad matches the a523
descriptor **as of `tsp-5p1`** (2026-06-27), which recorded that the a523's
L2/R2 are DIGITAL (kernel emits `BTN_TL2/BTN_TR2`), not analog `ABS_Z/RZ`.

Used by `test_caps.py` to prove `pf caps probe-diff --device a523` goes green
end-to-end against a valid a523 capture — the tsp-9sx.5 acceptance gate.

Not a device transcript; SPIKE-0's on-silicon phase will produce those.
