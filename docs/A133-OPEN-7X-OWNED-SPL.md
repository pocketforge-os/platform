# A133 full Linux 7 owned-SPL contract

## Selected boot chain

Only `a133-open-7x-gpu` selects this existing source-owned path:

`BROM -> owned SPL @ 0x20000 -> owned U-Boot -> source-built TF-A BL31 -> booti Image/dtb.bin/initrd.gz from FAT mmc 0:4 -> Linux`

The profile contract is `sunxi-spl-uboot` / `sunxi-spl-booti`, U-Boot `tg5040_defconfig`, TF-A `PLAT=sun50i_a133`, and `spl_offset_kib=128`. The inherited `sunxi-a133-boot-chain` blob group remains present for the existing inert vendor slots and layout. It is not the selected boot path. The minimal `a133-open-7x` profile and every default profile retain the vendor boot chain.

## Exact source pins

- Linux 7: `kernel-sunxi-7.x` at `3e0a7373bddd5a801f5f07a71d02cf4d6e97e99d`.
- U-Boot: `u-boot-tsp-a133` at `ec2adf4c1d139ce2c0906354a26fc541490b67c6`.
- TF-A: `tfa-tsp-a133` at `199316464722231e1a818e0d3f927be9c0fc2798`.
- Image source selected for publication: `3c990a208fbc5a91649c8c36adc993aa62ebe7af`. The start-head image pin `00ab25c8d6900d46ba8e04e9dfd795ba8083a224` contains the same owned-bootchain implementation; `build/Dockerfile.pf` and `scripts/build-sd-image.sh` are byte-identical between those commits.

## Evidence limits

The historical owned-chain artifact `749fcb2c24b2f55533b45a21350a24bd4db35549184b06c09a55483f7b6f8db4` proves cold SD boot through the owned SPL, U-Boot, and BL31 to a working 4.9 system. It does not prove Linux 7.

The Linux 7 Boot 8 artifact `d0af502c48e9607f8d885e8b5f5eebfa6be0951b52f276eca0461cbcc0ea4f59` proves Linux 7 userspace and storage behind U-Boot 2025.10 through FelBoot. It does not prove the exact cold BROM-to-SPL path, the final full-GPU artifact, or the cold-profile command line.

Linux 7 source owns the DE/DSI/panel sequence, and an owned-U-Boot Linux 7 run initialized sun4i DRM and attached the OTM1289A panel. There is not yet a cold-boot visible-frame receipt for the exact full profile. Resolver tests are source evidence only and are not hardware acceptance.

The exact first full7 raw artifact `b419e5dc2172a69a06aecc9f0a64ce9af7d090ef59a99ee4cc6c0a5f5a198617` contains an ARM64 Image whose header advertises `image_size=0x00fa0000` (16,384,000 bytes), a 995,180-byte initrd, and a 26,263-byte DTB. U-Boot `ec2adf4c1d139ce2c0906354a26fc541490b67c6` loads them at `0x45000000`, `0x46000000`, and `0x48000000`, respectively. Those exact ranges do not overlap, but only `0x60000` (393,216 bytes) separates the advertised end of the kernel from the initrd load address. This is exact-artifact, current-pinned-kernel evidence only, not a size guarantee for a later image.

## Command line and boot experience

Cold owned U-Boot bakes:

```text
console=ttyS0,115200 earlyprintk=sunxi-uart,0x05000000 rdinit=/init root=PARTLABEL=userdata rootwait init=/sbin/init loglevel=8 cma=64M gpt=1 androidboot.hardware=sun50iw10p1
```

Boot 8 recorded only `console=ttyS0,115200 rdinit=/init`; it does not validate the exact cold command line above. `tg5040_defconfig` has no A133 video/DSI/panel configuration, so owned U-Boot draws neither the vendor splash nor charger UI. This is a parent hardware observation item, not evidence that vendor display state should be restored.

## Parent hardware gates

The parent must use one exact merged, resolved full image and separately prove:

1. Complete platform, image, kernel, U-Boot, TF-A, Mesa, SDL, firmware, launcher, recovery, compressed-image, and raw-image provenance.
2. Before touching the DUT, an offline range check for every actual full image using the ARM64 header's advertised `image_size` plus the actual initrd and DTB sizes at the pinned U-Boot load addresses. Also prove exact owned SPL bytes at raw `0x20000`; matching FAT p4 `Image`, `dtb.bin`, and `initrd.gz`; inert vendor boot-package/environment slots; and userdata matching the exported rootfs.
3. A caller-held fresh serial cold boot from BROM through owned SPL, U-Boot, and BL31 to the FAT payloads, `Starting kernel`, the exact Odyssey model, and writable userspace/storage without vendor `get card0 para fail`.
4. The actual `/proc/cmdline`, reconciled with the baked command line and evaluated against behavior rather than inferred from the FelBoot receipt.
5. Linux 7 display initialization from cold state and the resulting panel/backlight outcome, including the known absence of U-Boot splash/charger UI.
6. Actual GE8300 BVNC admission through the profile-specific experimental option, exact firmware loading, successful PowerVR initialization, a real open-Mesa workload, and a captured visible frame.
7. Full-panel performance and coverage under the GPU epic presentation children rather than as a source-child merge gate.
