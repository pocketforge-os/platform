#!/usr/bin/env bash
# families/sunxi/assemble-image.sh — sunxi FAMILY hook: assemble_image.
# Contract: in = kernel + bootchain + rootfs; out = flashable .img + SHA.
#
# The sunxi family owns BOTH assemble variants already in the tree (declarative via
# image.assembler / bootchain.boot_proto), instead of two silently-diverging board
# scripts (the tsp-bcx.19 class):
#   - a133 (assembler=genimage, boot_proto=boot_package_fex): vendor boot0 +
#     dragonsecboot boot_package.fex + abootimg boot.img  (image/boards/tsp/genimage.cfg)
#   - a523 (assembler=family-script, boot_proto=extlinux): mainline U-Boot SPL +
#     extlinux                                              (image/boards/tsp-s/assemble-sd.sh)
#
# M-1 SKELETON (tsp-1dl.1): the real assemble lives in the legacy `image` build, which
# is device-specific and NOT cleanly BOARD-parameterized (a133 = `make build-image`
# with substrate mounts; a523 = boards/tsp-s/assemble-sd.sh + build-rootfs-a523.sh) and
# builds kernel/GPU/SDL OUTSIDE the container with LOCAL_BLOBS. B4 (tsp-1dl.4) RETIRES
# this for one container-multistage assemble from platform.lock SHAs. Until then this
# hook prints the legacy invocation (DRY by default); set PF_DRY_RUN=0 to actually
# shell it (requires the legacy env: BLOBS_SRC/KERNEL_*_SRC/GPU_*_SRC/LIBSDL3_SRC).
set -euo pipefail
: "${PF_IMAGE_REPO:?set PF_IMAGE_REPO to the image-repo checkout (M-1 legacy build)}"
case "$PF_DEVICE_ID" in
  a133) legacy_board=tsp   ; legacy="make -C '$PF_IMAGE_REPO' build-image   # + SUBSTRATE/BLOBS_SRC/KERNEL_TSP_SRC/GPU_KM_TSP_SRC/LIBSDL3_SRC" ;;
  a523) legacy_board=tsp-s ; legacy="bash '$PF_IMAGE_REPO/boards/tsp-s/assemble-sd.sh'  # + build-rootfs-a523.sh, board.env" ;;
  *) echo "[sunxi/assemble_image] no legacy-board mapping for device=$PF_DEVICE_ID" >&2; exit 2 ;;
esac
echo "[sunxi/assemble_image] device=$PF_DEVICE_ID legacy_board=$legacy_board assembler=$PF_IMAGE_ASSEMBLER image_name=$PF_IMAGE_NAME"
echo "[sunxi/assemble_image] M-1 legacy invocation: $legacy"
if [ "${PF_DRY_RUN:-1}" = 1 ]; then
  echo "[sunxi/assemble_image] PF_DRY_RUN=1 (default): not invoking the legacy build (skeleton dispatch only)."
  exit 0
fi
echo "[sunxi/assemble_image] PF_DRY_RUN=0: shelling the legacy image build (needs the full legacy env)."
eval "$legacy"
