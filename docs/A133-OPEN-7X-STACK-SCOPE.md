# A133 open 7.x stack scope

`a133-open-7x` remains the minimal 7.x boot-bring-up profile.  Do not change it
in place to `gpu.model = "open"`.  The separate `a133-open-7x-gpu` profile is the
direct full graphics/image lane: it selects the reviewed 7.x GE8300 kernel path,
open Mesa, firmware, launcher, and recovery through the existing open-stack
selector.  It does not insert a temporary display-only profile or change the
launcher-selection contract.

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
`model = "none"`, the resolver emits no `PF_LAUNCHER_SHA`, so pf-shell remains
absent from the minimal `a133-open-7x` lane.  The full `a133-open-7x-gpu` sibling
uses `model = "open"`, so the existing selector emits non-empty launcher and
recovery pins without changing the minimal profile.

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

The 6.x open-stack integration did not transfer merely by selecting `open`.
The 6.x `a133-open` profile selects `sun50i-a133-pocketforge-odyssey.dtb`, enables
`CONFIG_DRM_POWERVR=m`, stages `powervr.ko`, installs the GE8300 firmware, and
uses the open Mesa userspace.  Its kernel also contains PocketForge GE8300 work
beyond the upstream driver, including the A133 clock/reset adaptation and the
SIPF-v1/HWRT changes.

Kernel-sunxi-7.x PRs #21 and #22 supplied the missing GPU and binding source
contracts.  PR #23 combined them with fail-closed schema hardening and merged as
`3e0a7373bddd5a801f5f07a71d02cf4d6e97e99d`.  Its candidate evidence builds the
kernel Image, modules and four DTBs, verifies 15 schemas and 14 DTEX cases, and
executes 18 PowerVR cases under ARM64 QEMU.  The Odyssey DTB and `a133_defconfig`
therefore provide the source inputs required by the new profile.  Exact
post-merge push CI run `36173942752` succeeded for merged source
`3e0a7373bddd5a801f5f07a71d02cf4d6e97e99d`, establishing the accepted kernel
source identity.  This is a source/build admission result; it is not firmware
initialization, Mesa rendering, or device acceptance.

Build #10 on 2026-09-22 proves that the pinned 6.x image integration can assemble
the open kernel, firmware, Mesa userspace, and launcher inputs.  The reusable
parts are the image stage structure, open Mesa userspace, firmware inventory,
launcher/runtime sources, and the already-replayed display pipeline.  The
combined PR #23 source now proves the 7.x module source/build half.  Image
assembly must still prove the
profile-declared module inventory, exact firmware/hash/license, and paired source
provenance.  Merged image PR #125 provides that profile-driven assembly contract
at `d81151a83ac8a260512c2ea66eb878e2136bd3b1`, and merged SDL PR #19 provides the
audited open-model build path at
`1e4bdcb77f9c1f466ea7076058a5440faf549cd7`.  Device acceptance must separately
prove runtime BVNC admission, firmware/device initialization, Mesa rendering, and
presented pixels.

## Decision and costs

Add one full-open sibling directly on `base = "a133"`.  Keep `a133-open-7x` as
the minimal boot/storage lane and use `a133-open-7x-gpu` for the 7.x Odyssey DTB,
`in-tree-7.x` PowerVR module, open firmware/Mesa, fbdev display, launcher, and
recovery.  Profile data explicitly declares the kernel modules image assembly
must prove: the established 6.x profile retains powervr/videobuf2/CSI/xradio,
while the 7.x GPU milestone declares powervr only.  The existing open selector
continues to own launcher and recovery selection.

A display-only 7.x image remains a valid independent diagnostic/use case: it can
isolate panel scanout and launcher orientation from GPU initialization.  It is
not inserted into this publication sequence, and adding it later would require
its own explicit launcher contract, image proof, and device receipt.  The direct
full profile is justified now because the reviewed kernel port exists; retaining
the minimal sibling still provides the cheap boot/storage regression lane.

## Uncertainties

- The build-15 log named in the originating bead is on a build host not available
  in this worker environment; its quoted provenance was accepted as the observed
  input, not independently reread here.
- The current 7.x display source compiles, but no device receipt found in the
  inspected repository/PR evidence satisfies kernel PR #9's scanout criterion.
- The reusable 6.x firmware and Mesa userspace are plausible inputs because both
  target the same GE8300/BVNC and DRM userspace ABI, but compatibility with the
  merged 7.x kernel remains unproven until exact-image device initialization and
  rendering evidence exists.  The 7.x driver's `exp_hw_support=1` parameter only
  admits this unmaintained BVNC; it is not compatibility evidence.
- The profile pins the accepted combined PR #23 merge, and the platform lock now
  pairs it with merged image PR #125 and merged SDL PR #19.  Full-image artifact
  provenance and device/runtime acceptance remain separate release-owner gates.
- No current device receipt was found that visually accepts launcher PR #141 on
  the 6.x lane.  If such a receipt exists outside the repositories inspected
  here, it should be linked from the follow-up that closes this coverage gap.
