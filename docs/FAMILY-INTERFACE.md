# The per-SoC-family interface (the seam)

A family plugin lives in `families/<family>/` and implements a fixed contract of **four
hooks** the core dispatches to. The core owns everything *between* the hooks; the family
owns everything *inside* them. This is the only thing the core and a family share.

```
core (SoC-agnostic)                         family plugin (families/<family>/)
pf build --device <id>
  ├─ parse profile + merge family.toml + core defaults   [core]
  ├─ resolve platform.lock → exact SHAs                   [core]
  ├─ fetch blob groups (multistage fetch, by CID)         [core; B3]
  ├─ build_rootfs()  (mmdebstrap, SoC-agnostic)           [core; B4]
  ├─ FAMILY.build_kernel(profile)      ───────────────▶   build-kernel.sh
  ├─ FAMILY.build_bootchain(profile)   ───────────────▶   build-bootchain.sh
  ├─ FAMILY.assemble_image(profile)    ───────────────▶   assemble-image.sh
  ├─ reproducibility_finalize()                           [core; B4/B6]
  └─ emit artifact + SHA + provenance                     [core]
pf flash --device <id>
  └─ FAMILY.flash(profile, image)      ───────────────▶   flash.sh
```

## The contract

| hook | input | output | sunxi | snapdragon (stub) |
|---|---|---|---|---|
| `build-kernel.sh` | profile, pinned src | `Image`/DTB/`/lib/modules` | gcc-10.3 cross, `pocketforge_*_defconfig` | aarch64 cross, msm defconfig, in-tree GPU |
| `build-bootchain.sh` | profile, src **or** blob group | SPL/U-Boot/BL31 **or** signed fw | a523: build U-Boot+TF-A; a133: pass-through blob group | pass-through signed XBL/TZ/modem |
| `assemble-image.sh` | kernel+bootchain+rootfs | flashable `.img` + SHA | genimage / extlinux | mkbootimg boot.img + GPT |
| `flash.sh` | profile, artifact | flashed device | `dd` to SD via the automation (Dell `--slot`, pf-lock) | fastboot / EDL |

## How the core hands data to a hook (the env contract)

The dispatcher (`core/pf-build.sh`) resolves + flattens the profile into `PF_*` env vars
(`core/profile.py env <id>`) and exports them before calling each hook:

```
PF_DEVICE_ID PF_FAMILY PF_SOC PF_ARCH
PF_KERNEL_REPO PF_KERNEL_REF PF_KERNEL_DEFCONFIG PF_KERNEL_DTB PF_TOOLCHAIN_CC
PF_GPU_REPO PF_GPU_REF PF_GPU_MODULES
PF_BOOTCHAIN_MODEL PF_BOOT_PROTO PF_BOOTCHAIN_BLOB_GROUP PF_UBOOT_REPO PF_SPL_OFFSET_KIB
PF_IMAGE_ASSEMBLER PF_IMAGE_NAME PF_PART_TABLE PF_BOOT_LABEL PF_ROOT_LABEL
PF_BLOB_GROUPS PF_BUILD_IMAGE PF_FLASH_METHOD PF_FLASH_SLOT
PF_OUT_DIR PF_BEAD PF_DRY_RUN PF_IMAGE_REPO PF_PLATFORM_DIR
```

Anything not flattened is in the resolved JSON (`pf resolve <id>`).

## Adding a family

1. `families/<new>/family.toml` + the four hooks.
2. A device profile with `family = "<new>"`.
3. The **core must not change.** `ci/core-purity-check.sh` asserts the core stays free of
   the new family's vocabulary; B8 (`tsp-1dl.8`) extends the gate to "core/ did not change
   to onboard the family." If the core needed edits, the seam leaked — fix the seam.
