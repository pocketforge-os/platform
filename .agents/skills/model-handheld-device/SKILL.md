---
name: model-handheld-device
description: Build, derive, refine, validate, and ship source-owned semantic OpenSCAD models of handheld gaming devices. Use for new handheld device models, shared-chassis variants, near-photoreal control/port/label placement, iterative owner visual review, deterministic evidence renders, semantic control highlighting and skin atlases, privacy-safe reference-photo comparison, or PocketForge device-model and runtime-skin handoffs.
---

# Model Handheld Device

Create an evidence-backed visual/UI model in physical millimetres. Reuse an
accepted in-repository baseline whenever possible, preserve uncertainty
honestly, and keep semantic controls reproducible from source through rendered
skin assets.

## Load the relevant guidance

- Read [references/evidence-checklist.md](references/evidence-checklist.md)
  before gathering measurements, photos, or public sources.
- When working in PocketForge `platform/device-models`, also read
  [references/pocketforge-contract.md](references/pocketforge-contract.md)
  before editing.
- Use [scripts/validate_model_package.py](scripts/validate_model_package.py)
  for quick iteration checks and the full pre-sign-off proof.

## Follow the workflow

### 1. Establish the scope

Identify:

- manufacturer, product name, model number, and repository device ID;
- whether this is a new chassis or a derivative of an accepted model;
- whether the request covers only the source model or also generated runtime
  skin integration;
- the semantic input IDs expected by the device descriptor;
- the owner’s available photos and physical measurements.

Do not block on a perfect evidence set. Record missing measurements and lower
their confidence. Ask only when a missing value would materially change the
model or create a false manufacturing claim.

### 2. Enter the repository workflow

Read the repository’s `AGENTS.md` and follow its task, worktree, branch, review,
and merge rules. In a Beads repository:

1. inspect and claim the model task before editing;
2. create the required per-task worktree;
3. keep the model task separate from runtime-skin wiring when their acceptance
   gates differ;
4. leave owner visual acceptance open until the owner explicitly approves the
   evidence views.

Never edit a shared checkout when the repository requires worktrees.

### 3. Choose the baseline

Search the model library and device descriptors before drawing:

```bash
rg --files device-models devices skins
rg -n "CONTROL_IDS|PART=|HIGHLIGHT|MODEL_RENDERERS" device-models skins
```

Prefer, in order:

1. the same chassis or a documented hardware revision;
2. a sibling product with the same enclosure and controls;
3. the closest accepted model with compatible renderer semantics;
4. a clean model built from measured evidence.

Copy and adapt an accepted package only inside the task worktree. Preserve
proven dimensions and cameras unless evidence demonstrates a visible delta.
Never remodel shared geometry merely to make the derivative look independently
authored.

### 4. Build an honest physical model

Use a fixed millimetre coordinate system and separate:

- shell outline, face, rear, and edge depth;
- screen recess/glass from the published active display;
- interactive crowns/caps from decorative or LED rings;
- controls from legends, ports, speakers, vents, and identity artwork;
- measured dimensions from published dimensions and photo-derived estimates.

Expose every drawable semantic control independently through the package’s
`PART`, `CONTROL_ID`, and `HIGHLIGHT` contract. Reuse one visual part for
multiple logical inputs only when the descriptor and hardware intentionally do
so, such as clickable stick inputs reusing `stick_l` and `stick_r`.

Express alignment constraints algebraically when possible. For example, align
a button edge to a stick ring using their radii rather than maintaining two
unrelated coordinates.

### 5. Document provenance while modeling

Maintain the model README as evidence is applied. Include:

- coordinate system and nominal envelope;
- measurement/provenance/confidence table;
- baseline lineage and preserved geometry;
- semantic IDs and intentional visual reuse;
- reproduction commands, font/tool requirements, and known limits;
- public corroboration links;
- private owner-reference filenames or locations without copying them into
  git.

Do not describe photo-derived geometry as manufacturing-tolerance data.

### 6. Keep rendering deterministic and private

Adapt the accepted renderer and comparison tool rather than inventing a second
pipeline. Preserve:

- fixed cameras and canvas transforms;
- neutral render plus one-control-at-a-time highlights;
- pairwise-disjoint semantic rectangles;
- a lit atlas composed from those individual control renders;
- six fixed evidence views;
- fresh PNG comparison outputs that carry no source EXIF or text metadata.

Keep original owner photos outside the repository. Never commit a private
reference image, a transformed copy of it, or an output that retains its
metadata.

### 7. Validate in two passes

During iteration, run the validator from this skill directory:

```bash
python3 .agents/skills/model-handheld-device/scripts/validate_model_package.py \
  device-models/<slug> --quick
```

Before visual sign-off, run the full proof:

```bash
python3 .agents/skills/model-handheld-device/scripts/validate_model_package.py \
  device-models/<slug> --photos /path/to/private/reference-directory
```

The full proof compile-checks the tools, enables OpenSCAD hard warnings,
renders deterministic repeated evidence views, sweeps standalone semantic
control geometry, derives the complete semantic atlas, checks descriptor ID
parity and rectangle separation, and optionally verifies privacy-safe
comparison PNGs.

Also run repository-specific validation such as `render.py --check`,
`device-models/check-skin-drift.py`, or capability validation when generated
runtime assets are in scope.

### 8. Iterate visually without moving approved geometry

Open the exact worktree source in OpenSCAD for owner review. Apply feedback as
small, explicit constraints:

- translate “move inward” into the front-view coordinate direction;
- distinguish the interactive control edge from its recess or LED ring;
- preserve already approved areas;
- change one coherent visual relationship per iteration;
- render from the fixed evidence camera after every change;
- record the final coordinates and validation evidence.

Before requesting final approval, commit the validated candidate and open that
exact revision in OpenSCAD. Any later geometry or camera change invalidates the
approval and must be shown again.

If the live GUI makes an off-screen raster repeat differ, close it during the
clean deterministic pass, then reopen the exact committed revision.

Do not merge on “nearly done.” Require the owner’s explicit visual approval
when the task carries a visual gate.

### 9. Ship and hand off

After approval:

1. verify the final branch is committed and pushed;
2. wait for every required PR check;
3. merge through the repository’s required review flow;
4. verify the approved head is on the default branch;
5. remove the task worktree and close/sync task tracking;
6. unblock, but do not silently implement, a separate runtime-skin task.

Report the merged artifact, validation result, and any remaining
manufacturing-grade measurement gaps.
