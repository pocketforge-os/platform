# A133 full Linux 7 owned-SPL contract

## Selected boot chain

The `a133-open-7x-gpu`, `a133-open-7x-gpu-spl-trace`, and
`a133-open-7x-gpu-noradio` profiles select this existing source-owned path:

`BROM -> owned SPL @ 0x20000 -> owned U-Boot -> source-built TF-A BL31 -> booti Image/dtb.bin/initrd.gz from FAT mmc 0:4 -> Linux`

Their shared profile contract is `sunxi-spl-uboot` / `sunxi-spl-booti`, TF-A `PLAT=sun50i_a133`, and `spl_offset_kib=128`. The normal and no-radio profiles use U-Boot `tg5040_defconfig`; the SPL-trace profile uses `tg5040_mmc_trace_defconfig`. The no-radio profile changes only the selected DTB (its lock-owned kernel pin now equals the canonical pin): its DTB disables MMC1, its Wi-Fi power sequence, and the XR829 Bluetooth UART path. The inherited `sunxi-a133-boot-chain` blob group remains present for the existing inert vendor slots and layout. It is not the selected boot path. The minimal `a133-open-7x` profile and every default profile retain the vendor boot chain.

## Exact source pins

- Linux 7: `kernel-sunxi-7.x` at `1b1da76f0adfa0f72379449f36746ed2104a9223` (device/a133: #45 `CONFIG_INPUT_UINPUT`, #46 gamepad MCU uart3/uart4, serial3/4 aliases, PD11 rail, eight 8250 slots, ext4 ACLs and fq_codel; tsp-mc9m.41.923.53). Previously `ee23555d9ba5362548c56573e558139541d3e702` (#42 headphone-jack detection, #44 removes the PL8 usb1-vbus regulator and fixes the SD mmc0 regression; tsp-mc9m.41.923.42), before that `85fddb4b06e8526e0ac6f30276b8bc4290af4e51` (#36 I2C userspace access, #39 sun4i-usb VBUS validation, #40 RTC topology CI, #41 `CONFIG_FB_DEVICE=y` restores `/dev/fb0`; tsp-mc9m.41.923.48), before that `03822b3fceb6ec000b4a0de58e5486c32a33ff9c` (#37 no-radio diagnostic DTS target, #38 A133 xradio chip ID; tsp-mc9m.41.923.46), before that `bbfce0312a69662afa013a5276afa3bd4b513dba`.
- Linux 7 for `a133-open-7x-gpu-noradio`: a lock-owned profile pin at `1b1da76f0adfa0f72379449f36746ed2104a9223`, equal to the canonical pin and moved with it, so the diagnostic differs from the normal build only in the selected DTB (tsp-mc9m.41.923.42). The pin stays an explicit entry because the owned-image workflow requires the resolved noradio kernel to equal it (`noradio_kernel_not_profile_pin`). It was previously `0a475ab54c04101a06d0c48c95a0e3cf5d778c05`, the bisect-era reviewed child of `bbfce0312a69662afa013a5276afa3bd4b513dba` that added only the diagnostic DTB target and its semantic-diff checker; that kernel predates `CONFIG_FB_DEVICE` and the PL8 SD fix.
- U-Boot for the normal `a133-open-7x-gpu` profile: `u-boot-tsp-a133` at the canonical repository pin `c21fbfb88293b9427b471a0725d1851484a8adba` (u-boot#50: a FEL-loaded U-Boot never autoboots the SD kernel; tsp-3rd3.11). Its SPL banner is `U-Boot SPL 2025.10-gc21fbfb88293`, because the image stamps `-g<first 12 hex of PF_UBOOT_SHA>`. Previously `d34088ebaa98a6711b29ed1b46600c9990f0375c` (u-boot#49: `CONFIG_BOOTDELAY=0` and `vt.global_cursor_default=0`; tsp-3rd3.8; banner `2025.10-gd34088ebaa98`), before that `dfcc77739aa647fa195abd2e01d9fab6b2633474` (u-boot#48: kernel `0x44000000`, FDT `0x49000000`, initrd `0x4b000000`; banner `2025.10-gdfcc77739aa6`), before that `1bc129ad26229bfe6037cf038c3d087a2450a18c`.
- U-Boot for the diagnostic `a133-open-7x-gpu-spl-trace` profile: the same real `u-boot-tsp-a133` repository, selected by a lock-owned profile pin `dfcc77739aa647fa195abd2e01d9fab6b2633474`, deliberately NOT moved to the canonical `d34088eb` or `c21fbfb8` (tsp-3rd3.10; its banner stays `2025.10-gdfcc77739aa6`, and it lacks the u-boot#50 FEL autoboot guard). It contains the merged CLDO3 SD-boot gate and applies the u-boot#48 layout to `tg5040_mmc_trace_defconfig` as well.
- TF-A: `tfa-tsp-a133` at `199316464722231e1a818e0d3f927be9c0fc2798`.
- Image source pin: `bba639414adaeac3eb14d70d74c783e8d517f65d` (image#137 bounded self-flash SD discovery, image#138 A133-open default-app integration, image#139 real-systemd session-authority test under `tests/` only, image#140 unconditional disable of that privileged harness (`DISABLED reason=HOST_VT_INCIDENT`) under `tests/` only; #138 CHANGES `build/Dockerfile.pf`). Prior: `e765ba2cd5d278b977cde1d7c3de4bec83de368e` (image#132 kernel UTS identity stamp, image#133 no-radio profile admission, image#134/#135 Poolsuite dev-rootfs producer and cargo cache; #132 and #134 CHANGE `build/Dockerfile.pf`, so the byte-identity statements below apply only to earlier pins). Prior: `48872abd88d4757871bd3359060ed009f192c58d` (image#130 BlueZ CLIs and XR829 payload assertions; image#131 owned-SPL payload layout build gate, which CHANGES `build/Dockerfile.pf` and `scripts/build-sd-image.sh`, so the byte-identity statements below apply only to the prior pin). Prior: `78fc4873def3d114ea9478827c440940548fd684` (image#129: i2c-tools + usbutils in the mainline rootfs package list; `build/Dockerfile.pf` and `scripts/build-sd-image.sh` are byte-identical to `3c990a208fbc5a91649c8c36adc993aa62ebe7af`, the image source of the 2026-09-27 cold-boot acceptance build). Earlier: image source selected for publication `3c990a208fbc5a91649c8c36adc993aa62ebe7af`. The start-head image pin `00ab25c8d6900d46ba8e04e9dfd795ba8083a224` contains the same owned-bootchain implementation; `build/Dockerfile.pf` and `scripts/build-sd-image.sh` are byte-identical between those commits.

## Evidence limits

The historical owned-chain artifact `749fcb2c24b2f55533b45a21350a24bd4db35549184b06c09a55483f7b6f8db4` proves cold SD boot through the owned SPL, U-Boot, and BL31 to a working 4.9 system. It does not prove Linux 7.

The Linux 7 Boot 8 artifact `d0af502c48e9607f8d885e8b5f5eebfa6be0951b52f276eca0461cbcc0ea4f59` proves Linux 7 userspace and storage behind U-Boot 2025.10 through FelBoot. It does not prove the exact cold BROM-to-SPL path, the final full-GPU artifact, or the cold-profile command line.

Linux 7 source owns the DE/DSI/panel sequence, and an owned-U-Boot Linux 7 run initialized sun4i DRM and attached the OTM1289A panel. There is not yet a cold-boot visible-frame receipt for the exact full profile. The diagnostic profile's merged CLDO3 SD-boot gate source and resolver tests are source evidence only; they do not prove a full-image build, cold boot, or hardware acceptance.

The exact first full7 raw artifact `b419e5dc2172a69a06aecc9f0a64ce9af7d090ef59a99ee4cc6c0a5f5a198617` contains an ARM64 Image whose header advertises `image_size=0x00fa0000` (16,384,000 bytes), a 995,180-byte initrd, and a 26,263-byte DTB. U-Boot `ec2adf4c1d139ce2c0906354a26fc541490b67c6` loads them at `0x45000000`, `0x46000000`, and `0x48000000`, respectively. Those exact ranges do not overlap, but only `0x60000` (393,216 bytes) separates the advertised end of the kernel from the initrd load address. This is exact-artifact historical evidence for the prior PR23 kernel pin `3e0a7373bddd5a801f5f07a71d02cf4d6e97e99d` only, not a size guarantee for a later image. The `6d86d65efaa275eb18c810c531c19ec6249d85b5` kernel advertised `image_size=0x01010000` and crossed that gap: U-Boot refused `booti` with `RD image overlaps OS image (OS=45000000..46010000)` (tsp-mc9m.41.923.38/.40). u-boot#48 moves the layout to kernel `0x44000000`, FDT `0x49000000`, initrd `0x4b000000` (an 80 MiB kernel window) and image#131 gates the payload layout at build time. Full-image sizes and load ranges for the current kernel pin `1b1da76f0adfa0f72379449f36746ed2104a9223` (also the no-radio profile pin) still require verification by a new build.

## Command line and boot experience

At their respective locked U-Boot source pins, both profiles bake:

```text
console=ttyS0,115200 earlyprintk=sunxi-uart,0x05000000 rdinit=/init root=PARTLABEL=userdata rootwait init=/sbin/init loglevel=8 cma=64M gpt=1 androidboot.hardware=sun50iw10p1
```

Boot 8 recorded only `console=ttyS0,115200 rdinit=/init`; it does not validate the exact cold command line above. Neither the normal `tg5040_defconfig` nor the diagnostic `tg5040_mmc_trace_defconfig` has A133 video/DSI/panel configuration, so owned U-Boot draws neither the vendor splash nor charger UI. This is a parent hardware observation item, not evidence that vendor display state should be restored.

## Parent hardware gates

The parent must use one exact merged, resolved full image and separately prove:

1. Complete platform, image, kernel, U-Boot, TF-A, Mesa, SDL, firmware, launcher, recovery, compressed-image, and raw-image provenance.
2. Before touching the DUT, an offline range check for every actual full image using the ARM64 header's advertised `image_size` plus the actual initrd and DTB sizes at the pinned U-Boot load addresses. Also prove exact owned SPL bytes at raw `0x20000`; matching FAT p4 `Image`, `dtb.bin`, and `initrd.gz`; inert vendor boot-package/environment slots; and userdata matching the exported rootfs.
3. A caller-held fresh serial cold boot from BROM through owned SPL, U-Boot, and BL31 to the FAT payloads, `Starting kernel`, the exact Odyssey model, and writable userspace/storage without vendor `get card0 para fail`.
4. The actual `/proc/cmdline`, reconciled with the baked command line and evaluated against behavior rather than inferred from the FelBoot receipt.
5. Linux 7 display initialization from cold state and the resulting panel/backlight outcome, including the known absence of U-Boot splash/charger UI.
6. Actual GE8300 BVNC admission through the profile-specific experimental option, exact firmware loading, successful PowerVR initialization, a real open-Mesa workload, and a captured visible frame.
7. Full-panel performance and coverage under the GPU epic presentation children rather than as a source-child merge gate.
