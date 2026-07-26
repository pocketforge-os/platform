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

## `a133-capture-rev5-20260725.json`

The first COMMITTED a133 kernel-node capture. A REAL on-silicon transcript:
the static C dumper (`evdev-dump.c`, built `-static` for aarch64) run over SSH on
the **rev-5.0 replacement** TrimUI Smart Pro base (A133), PocketForge dev image,
owned 4.9.191 kernel fork, 2026-07-25 (tsp-65jc.11 / infra-113 D8). `/dev/input`
on our image = event0 `sunxi-keyboard` (KEY_VOLUMEUP/DOWN only) + event1
`audiocodec sunxi Audio Jack` — no pad, no axp2202-pek (our image lacks the
input-synthesis layer that stock synthesizes the "TRIMUI Player1" uinput gamepad
above the kernel; tracked on the tsp-ozbp/E2 lane).

`pf caps probe-diff --device a133 --probe a133-capture-rev5-20260725.json` returns
exactly ONE owner-adjudicated, EXPLAINED error — `no probe node matches
identity.match.evdev_name 'TRIMUI Player1'` — i.e. green modulo the missing pad
anchor. That is the expected asymmetric-diff result until the input-synthesis
daemon first runs on-device.

Provenance note: the ORIGINAL SPIKE-0 a133 capture (tsp-9sx.1, 2026-07-11) came
from the board later destroyed 2026-07-17 and was never committed as a fixture —
it lived only in a bead comment. This is its committed rev-5.0 successor. A
structural diff of the 2026-07-11 destroyed-board capture vs this rev-5.0 capture
is **node/code/id IDENTICAL** — no rev-5.0 delta (the expected finding; VOL± was
already proven end-to-end).
