# regression/caps/fixtures/

Vendored capture fixtures for the SPIKE-0 (tsp-9sx.1) descriptor↔probe diff.

## `a523-capture.json`

A REAL on-silicon transcript: `regression/caps/evdev-probe.py` run on the TrimUI
Smart Pro S (A523) over SSH, stock vendor OS (Buildroot / Linux 5.15.147 Longan),
2026-07-11, SPIKE-0 (tsp-9sx.1). Cross-validated byte-identical against the static
C dumper (`evdev-dump.c`) in the same session. Full node inventory: sunxi-keyboard
(incl. KEY_HOMEPAGE), pwm-vibrator (FF), axp2202-pek, audiocodec Headphones, and
the trimui_inputd-synthesized uinput gamepad "TRIMUI Player1" (045e:028e).

Used by `test_caps.py` to prove `pf caps probe-diff --device a523` goes green
end-to-end against real silicon under the asymmetric rule.

(History: until 2026-07-11 this was a synthetic capture seeded from the E5 sim and
augmented with BTN_TL2/TR2 per tsp-5p1's digital-trigger claim — which the real
silicon REFUTED: the pad advertises ABS_Z/ABS_RZ trigger axes and no TL2/TR2.)
