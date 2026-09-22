# A133 v7.2 image path

The v7.2 replay is a second kernel line for the existing A133 open product, not
a product fork. Because profile resolution intentionally follows one base level,
`a133-open-7x` inherits directly from `a133` and explicitly declares its complete
open-variant kernel, GPU, and blob selections. The existing
`a133-open` profile and every existing lock pin remain unchanged, so 6.x builds
continue to resolve exactly the same inputs.

The alternative was to add a kernel-line switch inside `a133-open`. That would
make one device id resolve differently according to caller state, weaken the
profile-to-artifact provenance mapping, and risk changing the established 6.x
product while the 7.x lane is still experimental. A separate opt-in profile is
therefore the safer boundary; it can be retired when 7.x is promoted.

## GPU-less contract

Step 7 of the replay has not started, so the v7.2 kernel does not contain the
A133 PowerVR changes. The profile declares `[gpu].model = "none"`, clears every
inherited KM/UM repo and ref, sets `modules = []`, and removes the open PowerVR
firmware blob group. `core/profile.py` validates that `none` cannot carry GPU
sources or modules. Its build arguments consequently contain no GPU source SHA,
module, launcher, recovery, or firmware input. Image consumers must treat
`PF_GPU_MODEL=none` as an intentional, successful GPU-less build mode.

## Follow-up: pocketforge-automation

In `scripts/build-owned-image.sh`, the `--kernel` parser currently accepts only
`6.x` at lines 81–83 and otherwise exits with `reason=unsupported_kernel` and
`hint=use 6.x`. Extend the accepted values to `6.x|7.x`, retain the current
`--variant mainline` behavior, and map the selection explicitly: `6.x` uses
device profile `a133-open`, while `7.x` uses `a133-open-7x`. Thread that selected
profile through the existing platform build invocation and record both kernel
line and profile in the status/provenance output. Add parser and dry-run tests
which prove unsupported values still fail closed and that the 6.x command is
unchanged. This enables creation of the candidate image used for the step-2
serial/storage receipt; it performs no device validation itself.

## Follow-up: image

The following inspected image-repository sites must implement
`PF_GPU_MODEL=none` without changing the `ddk` or `open` branches:

- `build/Dockerfile.pf` kernel stage (arguments at lines 127–130, DTB lookup at
  lines 196–204, module install/provenance at lines 201–226): keep the generic
  locked kernel archive build, select `sun50i-a133-pocketforge-tsp.dtb`, install
  the full v7.2 `/lib/modules/<kernel.release>` tree, and preserve the release
  and vermagic provenance guards.
- `build/Dockerfile.pf` GPU and model-selector stages (GPU KM at lines 232–340;
  `gpu-um-mesa`, recovery, and launcher selectors near lines 533, 1059, and
  1126): add real `none` selector stages/branches that emit explicit
  NOT-SHIPPED provenance and never require or copy GPU KM, Mesa UM, PowerVR
  firmware, launcher, or recovery sources. The rootfs/assemble path near lines
  1163–1204 must accept the empty GPU module staging directory.
- `boards/tsp/initrd/build-initrd.sh` module selection and generated-init edits
  (roughly lines 70–125 and 190–270), plus `boards/tsp/initrd/init` PowerVR load
  block around lines 353–363: for `none`, package only non-GPU modules needed to
  reach storage/userspace and remove both closed and open GPU load attempts.
  Do not require `videobuf2-dma-contig.ko` unless a non-GPU first-boot service
  actually needs it.
- `scripts/build-rootfs.sh` module staging, `modules-load.d`, firmware, and GPU
  userland branches, and `scripts/build-sd-image.sh` GPU artifact assertions:
  key each assertion on the model; `none` installs the kernel's modules and runs
  `depmod` for the discovered v7.2 release but installs/asserts no GPU module,
  firmware, ICD, or PowerVR userspace. Never hard-code a 6.x release directory.

The image follow-up must verify that every staged `.ko` belongs to the discovered
v7.2 `kernel.release` (vermagic remains the load gate with `MODVERSIONS=n`), that
the selected DTB exists under the locked kernel output, and that negative checks
find no GPU artifacts in the GPU-less rootfs/initramfs. Its first device receipt
then targets plan step 2: fresh serial reaches userspace with the expected v7.2
identity; SD and eMMC enumerate and their partitions read; and the log contains
no unresolved A133 clock, reset, or power-domain dependency.
