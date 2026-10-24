# PowKiddy X55 semantic model

`powkiddy-x55.scad` is PocketForge's source-owned visual model of the black
PowKiddy X55. Its coordinate space is millimetres: X is physical left to
right, Y is bottom to top, and Z is rear to front.

This is a nominal visual/UI model for device identity, input highlighting,
fixture visualization, simulator-skin generation, and layout studies. It is
not a manufacturing-tolerance enclosure drawing. Holder contact and retention
geometry continues to come from the measured contract and physical fit work in
`test-node-hw`, not by treating this visual surface as a pressure-fit scan.

The black shell is the default because it matches the owner's device. Set
`COLORWAY="blue"` to expose the alternate public-reference colorway when the
stronger contrast makes curved-shell review easier.

## Baseline lineage

The package contract, semantic selection, deterministic rendering, and
privacy-safe comparison flow derive from the accepted
`device-models/trimui-smart-pro/` and `device-models/trimui-brick/` packages.
The X55 shares no enclosure geometry with either device. Its waisted face,
rear grip lobes, shoulder forms, display, controls, ports, and labels are
authored independently from X55 evidence.

No trustworthy public X55 CAD, scan, STEP, or source mesh was found during the
initial evidence pass. Public product and review photographs therefore
constrain this first source-owned reconstruction. The existing X55 cradle
preview is used only for owner-measured envelope and top-feature coordinates;
it is not imported as accepted device geometry.

This task deliberately stops before runtime integration. There is no committed
X55 runtime descriptor or generated simulator skin in this package. The
semantic IDs below are stable model-stage names; runtime integration remains a
separate owner-approved follow-up.

## Measurement and provenance

| Feature | Value used | Evidence | Confidence |
|---|---:|---|---|
| Manufacturer maximum envelope | 212.5 × 94.5 × 19.0 mm | PowKiddy product specification | High as nominal marketing data |
| Owner-traced primary face | 210.0 × 88.76 mm | `20260721_051032.jpg`; X55 cradle work `tsp-bcx.21.27` | High for the traced X/Y contact profile |
| Shell depth topology | 19.0 mm at grip crowns; approximately 14.3 mm at centre rear; 13.0 mm shallow core | Manufacturer maximum plus owner cradle reconstruction and public rear/edge photographs | Medium; exact local Z measurements remain open |
| Active display | 5.5 in, 16:9; 121.76 × 68.49 mm calculated | PowKiddy specification | High |
| Display glass | 133.0 × 78.5 mm, centred at (106.25, 47.80) | Calibrated official orthographic front elevation and owner front photograph | Medium |
| Left stick | centre (23.0, 67.0); 22.4 mm well, 20.0 mm ring, 13.2 mm cap | Calibrated official orthographic front elevation | Medium |
| D-pad | centre (23.0, 40.0); 24.0 mm overall with 9.0 mm arms | Calibrated official elevation and owner front photograph | Medium |
| Face cluster | centre (188.0, 66.0); 8.90 mm cardinal pitch; 7.7 mm crowns | Calibrated official elevation; Nintendo X/A/B/Y public product layout | Medium |
| Right stick | centre (188.0, 39.0); same provisional geometry as left stick | Calibrated official orthographic front elevation | Medium |
| System controls | Select (20.2, 15.8), Vol+ (32.6, 15.8), Vol− (179.9, 15.8), Start (191.5, 15.8); 7.0 mm crowns | Calibrated official elevation and owner front photograph | Medium |
| Top interface centres | power 42.38, audio 67.14, USB-C DC/OTG 94.0, mini-HDMI 120.0, USB-C host 147.4, reset 168.77 mm from left datum | Owner cradle annotations reconciled with a perpendicular public top photograph | High in X for owner datums; provisional opening profiles |
| Bottom interfaces | 13.5 × 2.2 mm nominal TF openings centred at X 89.0 and 126.5; 13 × 5 staggered 0.62 mm speaker-hole fields in moulded end panels | Public perpendicular bottom photographs | Medium for order/pattern; opening dimensions remain visual estimates |
| Shoulder controls | L2/L1 and R2/R1 as separate four-segment rounded sweeps that follow the traced corner locally | Public front, top, rear, short-end, and oblique photographs | Medium-low for exact footprint, curvature, and travel |
| Rear grip topology | paired smoothstep palm lobes tangent-blended into the shallow central back with no pad seam | Independent multi-angle review photographs | Medium for topology; exact sections provisional |
| Rear fasteners and printing | eight surface-registered recessed screws; centred PowKiddy/MODE:X55 mark; left-aligned power copy followed by CE/recovery/recycle/age/WEEE marks | Public rear photographs | Medium for placement; microcopy is representational |

Public references:

- PowKiddy X55 official product page:
  <https://powkiddy.com/products/powkiddy-x55-5-5-inch-1280-720-ips-screen-rk3566-handheld-game-console-jelos-system-open-source-retro-console-childrens-gifts>
- TikGadget independent multi-angle review:
  <https://www.tikgadget.jp/powkiddy-x55-review/>
- Handhelds Wiki X55 hardware summary:
  <https://handhelds.wiki/POWKIDDY_X55>

The locally reviewed owner evidence is:

- `/home/matt/Downloads/20260721_051006.jpg`
- `/home/matt/Downloads/20260721_051032.jpg`

Neither original is copied into git. `compare.py` applies EXIF orientation,
decodes RGB pixels, selects fixed device/trace crops, and writes fresh PNGs
with no inherited metadata.

## Semantic controls

The OpenSCAD source exposes:

`dpad`, `stick_l`, `stick_r`, `btn_north`, `btn_east`, `btn_south`,
`btn_west`, `btn_select`, `vol_up`, `vol_down`, `btn_start`, `btn_l1`,
`trig_l`, `trig_r`, `btn_r1`, `btn_power`, and `btn_reset`.

The directional face IDs name physical position. Printed glyphs use the
Nintendo layout: X north, A east, B south, and Y west. `trig_l`/`trig_r` name
the physical L2/R2 keys and do not imply analog travel. The stick caps are
clickable on the physical device, but this source-stage atlas gives each stick
one visual region; runtime aliases can be resolved with the eventual device
descriptor.

Useful OpenSCAD overrides:

```text
PART="assembly"                 complete coloured device
PART="shell"                    non-interactive geometry and detail
PART="controls"                 all semantic controls
PART="control" CONTROL_ID="…"  one semantic control
PART="screen"                   active display surface
HIGHLIGHT="" | "*" | "…"       neutral, all, or one magenta control
COLORWAY="black" | "blue"       owner unit or contrast-review colorway
QUALITY="draft" | "render"      tessellation level
```

`render.py` exposes the same 17 IDs. `render_skin_set()` produces a
source-model review atlas with front controls in the first tile and
top-edge/shoulder controls in the second. Every semantic rectangle comes from
a one-control render and is proven pairwise disjoint. This is model evidence,
not a committed runtime skin contract.

The fixed orthographic evidence cameras are `front`, `rear`, `top`, `bottom`,
`left`, and `right`. Curved-surface inspection adds the fixed evidence-only
`front-left`, `front-right`, `rear-left`, and `rear-right` cameras. Those
three-quarter images support visual iteration; they are not measurement
projections or runtime clickable views.

## Reproduce and compare

From the platform repository root:

```bash
# Complete six-view deterministic orthographic evidence set.
python3 device-models/powkiddy-x55/render.py \
  --views /tmp/powkiddy-x55-views \
  --colorway black \
  --quality render

# Final curved-surface evidence set.
python3 device-models/powkiddy-x55/render.py \
  --views /tmp/powkiddy-x55-obliques \
  --only front-left,front-right,rear-left,rear-right \
  --colorway black \
  --quality render

# Fast selective front review in the physical black colorway.
python3 device-models/powkiddy-x55/render.py \
  --views /tmp/powkiddy-x55-front \
  --only front

# High-contrast curved-front inspection without rendering unrelated surfaces.
python3 device-models/powkiddy-x55/render.py \
  --views /tmp/powkiddy-x55-front-inspection \
  --only front,front-left,front-right \
  --colorway blue \
  --quality draft

# Shoulder/grip continuity review.
python3 device-models/powkiddy-x55/render.py \
  --views /tmp/powkiddy-x55-rear-inspection \
  --only top,rear,rear-left,rear-right

python3 device-models/powkiddy-x55/render.py \
  --semantic-output /tmp/powkiddy-x55-semantic
python3 device-models/powkiddy-x55/render.py --check
python3 device-models/powkiddy-x55/compare.py \
  --photos /home/matt/Downloads \
  --views /tmp/powkiddy-x55-views \
  --output /tmp/powkiddy-x55-comparison
python3 /home/matt/.codex/skills/model-handheld-device/scripts/validate_model_package.py \
  device-models/powkiddy-x55 \
  --photos /home/matt/Downloads \
  --output /tmp/powkiddy-x55-validation
```

Rendering requires OpenSCAD 2021.01 or newer, Pillow, Liberation Sans, and
DejaVu Sans. Fixed cameras and output transforms live in `render.py`;
comparison output and generated evidence stay outside the repository.

Every geometry iteration uses a render-inspect-correct loop: render the minimum
named camera set, open every resulting PNG at high/original detail, record the
pixel-visible discrepancy against the corresponding evidence, change one
coherent relationship, then re-render and inspect the same views. A successful
OpenSCAD export alone is not a visual review.

The front silhouette IoU emitted by `compare.py` is a regression aid. Phone
lens distortion, perspective, shadows, and thresholding make it unsuitable as
a tolerance or fit claim.

## Known limits and next evidence gate

- The public maximum envelope and owner's traced X/Y outline are strong. The
  exact centre-back depth, grip crown sections, edge rolls, and the transition
  between them are continuous visual interpolations.
- Shoulder ordering and broad topology are verified. Exact L1/R1/L2/R2
  footprints, rearward projection, slopes, corner radii, bevels, seams, travel
  gaps, and local Z positions need owner measurements.
- Front placement is registered from a true orthographic product elevation,
  but control diameters, stick well/cap sections, D-pad arm geometry, system
  button crowns, display-glass bounds, bezel radius, and local face offsets
  remain measurement-review targets.
- Port order and owner X datums are verified. Opening width/height, metal lip,
  insertion depth, label bounds, and top/bottom edge curvature are provisional.
- Bottom microSD opening dimensions, slot spacing, speaker-hole diameters,
  pitches, and exact stagger pattern remain visual estimates despite their
  perpendicular-photo registration.
- Rear fastener recesses, mould seams, printed copy, shell finish, and display
  reflectance are representational OpenSCAD materials rather than scanned
  surfaces.
- No runtime descriptor, runtime atlas, simulator routing, or fixture contract
  is added in this task. Those remain separate gates after explicit owner
  approval of the physical model.
