# A133 open 7.x stack scope

`a133-open-7x` remains the minimal 7.x boot-bring-up profile.  Do not change it
in place to `gpu.model = "open"`.  Add a second, opt-in 7.x profile for the
display and launcher first; promote that profile to the full open GPU stack only
after the GE8300 kernel path has been ported, built, and independently validated.

This note is separate from `A133-7X-IMAGE-PATH.md` because that document records
the original image-path decision and implementation work.  This note records the
later stack-scope decision after the display replay landed and the absence of the
launcher from build 15 was noticed.

## Why `none` exists

The values are deliberate, not resolver defaults.  Commit
`f796a1883153f718610885314e7820ae60627dba` (bead `tsp-mc9m.56`, platform PR
#153) introduced `devices/a133-open-7x/profile.toml:22` with
`[gpu].model = "none"`.  Its design note says that replay step 7 had not started
and the v7.2 kernel did not yet contain the A133 PowerVR changes.  Commit
`02f2b603e277cfeca46968f69b7e5324a6c79397` (bead `tsp-mc9m.56.3`, platform PR
#154) then added `devices/a133-open-7x/profile.toml:33` with
`[display].pipeline = "none"`, because display replay step 5 had not yet landed.
The profile was intentionally a stable boot/storage bring-up lane whose success
did not depend on graphics.

The name describes the intended product lineage, not its present contents.  The
profile comment, commit history, and `docs/A133-7X-IMAGE-PATH.md` are the
authoritative statement of its current GPU-less contract.

There is an important consequence a future reader must act on: with
`model = "none"`, `core/profile.py:380` emits no `PF_LAUNCHER_SHA`, so **pf-shell
is absent from every 7.x image and launcher rotation work from launcher PR #141
has no device coverage on this lane at all**.  The runtime SHA is universal and
therefore its half of the rotation change can still be present; that does not
exercise pf-shell.

## What has changed since profile creation

### Display pipeline

The source prerequisites now exist.  Kernel-sunxi-7.x PR #9, merged as
`2c6a39955b20dcc8f5a740126076b8c833a65078` and included by the current platform
pin, replayed the A133 DE2, TCON/TCON-TOP, DSI/D-PHY, OTM1289A panel, PWM, and
backlight stack.  The pinned `a133_defconfig` enables `CONFIG_DRM`,
`CONFIG_DRM_SUN4I`, `CONFIG_DRM_SUN6I_DSI`, and the OTM1289A panel driver, and
the pinned PocketForge TSP DTS enables the DSI panel path.

That establishes source and build availability, not device acceptance.  PR #9
explicitly says its first-boot criterion (panel prepares and scans a deterministic
full-screen pattern with full-frame timing and extent) was not executed in the
headless lane.  The later successful 7.x userspace/storage boots do not close
that display criterion while the profile continues to advertise and package
`PF_DISPLAY_PIPELINE=none`.

### GE8300 open GPU

The 6.x open-stack integration does not transfer merely by selecting `open`.
The 6.x `a133-open` profile selects `sun50i-a133-pocketforge-odyssey.dtb`, enables
`CONFIG_DRM_POWERVR=m`, stages `powervr.ko`, installs the GE8300 firmware, and
uses the open Mesa userspace.  Its kernel also contains PocketForge GE8300 work
beyond the upstream driver, including the A133 clock/reset adaptation and the
SIPF-v1/HWRT changes.  The 7.x tree contains the upstream Imagination driver,
but its pinned `a133_defconfig` does not enable `CONFIG_DRM_POWERVR`, and its
`sun50i-a133-pocketforge-tsp.dts` deliberately defers GPU policy and has no
Odyssey GPU node.

Build #10 on 2026-09-22 proves that the pinned 6.x image integration can assemble
the open kernel, firmware, Mesa userspace, and launcher inputs.  The reusable
parts are the image stage structure, open Mesa userspace, firmware inventory,
launcher/runtime sources, and the already-replayed display pipeline.  It does
not prove that the GE8300-specific kernel changes apply to 7.x, that a 7.x
`powervr.ko` builds, or that the 6.x module can be reused; a kernel module must be
built from and for the selected 7.x kernel.  No such 7.x build evidence was found.

Making a full `open` profile therefore requires, at minimum:

1. porting and auditing the A133/GE8300 kernel delta against the 7.x Imagination
   driver, including clock/reset, GPU DT/power-domain policy, SIPF-v1, and HWRT
   changes;
2. enabling `CONFIG_DRM_POWERVR=m` and adding a 7.x Odyssey-equivalent board DTS;
3. building the exact pinned 7.x kernel and proving module release/vermagic,
   firmware, Mesa/ICD, and image provenance gates;
4. running GPU enumeration/render and KMS-present device acceptance independently
   from the minimal boot lane.

## Decision and costs

Add a second profile.  Keep `a133-open-7x` as the minimal boot/storage lane, and
introduce an explicitly named display/launcher 7.x profile before a full-GPU
variant.  A suitable shape is `gpu.model = "none"`,
`display.pipeline = "fbdev"`, plus an explicit launcher-inclusion fact; launcher
selection must no longer be inferred from `gpu.model`.  This preserves a usable
boot regression artifact when display or GPU work breaks, while giving display
and launcher changes an honest provenance identity.

The smallest source change that enables launcher rotation testing on 7.x is this
display-only profile plus the narrow platform/image wiring that selects pf-shell
from the launcher fact rather than from `PF_GPU_MODEL=open`.  The image already
has a GPU-less kernel path, and pf-shell's tested backend is fbdev, so the GPU
port is not a prerequisite.  The new profile must nevertheless pass a hermetic
image build and the display criterion from kernel PR #9 before its launcher result
is meaningful.

The alternatives cost more in risk or provide less evidence:

- Flipping `a133-open-7x` to `open` couples boot regression coverage to an
  unported GPU path and falsely implies that existing 6.x evidence applies.
- Leaving only the present profile keeps boot bring-up cheap, but can never test
  pf-shell.  Until the display-only profile is available, launcher PR #141 must
  receive compensating device coverage on the 6.x `a133-open` profile: build the
  coupled launcher/runtime pins, boot that exact image on the A133 bench DUT, and
  verify the pf-shell scene is presented in the panel's intended orientation via
  the normal screen-capture review and explicit visual acceptance.  Build #10's
  image-integration success alone is not that coverage.
- Adding the second profile costs one profile golden, an explicit launcher
  inclusion contract in `core/profile.py`, matching launcher selector/staging
  changes in the image repository, and a separate build/device receipt.  This is
  smaller than the GE8300 port and keeps failures attributable to one stack.

## Uncertainties

- The build-15 log named in the originating bead is on a build host not available
  in this worker environment; its quoted provenance was accepted as the observed
  input, not independently reread here.
- The current 7.x display source compiles, but no device receipt found in the
  inspected repository/PR evidence satisfies kernel PR #9's scanout criterion.
- The GE8300-specific 6.x delta has not been forward-ported or compiled against
  the pinned 7.x kernel.  The exact conflicts and additional adaptations remain
  unknown until that bounded port is attempted.
- The reusable 6.x firmware and Mesa userspace are plausible inputs because both
  target the same GE8300/BVNC and DRM userspace ABI, but compatibility with the
  eventual 7.x kernel delta is unproven.
- No current device receipt was found that visually accepts launcher PR #141 on
  the 6.x lane.  If such a receipt exists outside the repositories inspected
  here, it should be linked from the follow-up that closes this coverage gap.
