# Evidence and visual-review checklist

Use this checklist to distinguish reliable geometry from visual estimates.

## Minimum intake

Collect or identify:

- exact manufacturer, product name, model number, and hardware revision;
- nominal overall width, height, and depth;
- near-orthographic front and rear images;
- top, bottom, left, and right edge images;
- close-ups of controls, ports, labels, vents, and unusual hardware;
- at least one known physical dimension visible in a reference image;
- the closest accepted model, if the device shares a chassis;
- the descriptor or expected semantic control list.

The user may begin with only a device name. Research enough to form an evidence
plan, then request the highest-value missing views or measurements. Do not wait
for every ideal reference before building a reviewable first pass.

## Source priority

Use evidence in this order:

1. owner caliper/ruler measurements and perpendicular photographs;
2. official mechanical drawings, manuals, specifications, and product pages;
3. regulatory filings and teardown photography;
4. reputable multi-view retailer photography;
5. community measurements or licensed public models;
6. perspective-photo ratios and visual inference.

Browse for current or niche device facts. Prefer primary sources and preserve
URLs in the model README. Treat a public mesh as corroboration unless its
license, scale, and provenance are suitable for source reuse.

## Confidence vocabulary

- **High**: directly measured, mechanically specified, or repeatedly confirmed
  by independent perpendicular evidence.
- **Medium-high**: inherited from a proven shared chassis or strongly
  constrained by a measured image.
- **Medium**: consistent across good photographs but not directly measured.
- **Low**: perspective estimate, occluded detail, or single-source inference.

Never let millimetre coordinates imply a higher confidence than the evidence.

## Physical checklist

Record these separately where present:

- maximum shell envelope and clear-edge depth;
- endcap radii, chamfers, tapers, and grip bulges;
- screen recess, glass, active area, bezel, and corner radii;
- D-pad size and arm width;
- stick cap, recess, LED-ring diameters, height, and centres;
- face-button diameter, pitch, labels, and rotation;
- system-button crown, bezel, centres, and legends;
- shoulder and trigger extents;
- speaker-hole count, pitch, shape, and alignment;
- ports, switches, pinholes, slots, reset keys, and edge labels;
- front/rear branding and status motifs;
- ventilation, fan intake/exhaust, screws, feet, and seams.

For every alignment statement, name the compared edges. “Aligned with the
stick” is ambiguous; “button outer-bezel right edge equals stick LED-ring right
edge” is testable.

## Reference-photo handling

- Keep owner originals outside git.
- Preserve original filenames in private task notes or the model README only
  when that does not disclose sensitive path information.
- Apply EXIF orientation only while decoding.
- Re-encode comparison boards from RGB pixels.
- Reject comparison outputs carrying EXIF, XMP, IPTC, comments, or text chunks.
- Never use a committed crop of an owner photo as a modeling texture.

## Visual-review sequence

Use this order to reduce rework:

1. silhouette and measured envelope;
2. screen size and placement;
3. primary controls and interactive edges;
4. lower/system controls and speaker arrays;
5. ports and edge hardware;
6. identity artwork and legends;
7. rear topology and vents;
8. semantic highlighting and alternate views.

Keep a fixed-camera overview available while inspecting close-ups. Perspective
in the interactive OpenSCAD viewport can make a correct alignment appear
incorrect.

## Acceptance evidence

Before requesting sign-off, retain:

- hard-warning OpenSCAD compile result;
- deterministic six-view hashes;
- semantic control count and descriptor parity;
- pairwise-disjoint rectangle result;
- comparison result and metadata/privacy check;
- front, rear, top, and bottom evidence views;
- exact commit opened for the owner.

Treat silhouette IoU as a regression signal, not a tolerance certificate.
