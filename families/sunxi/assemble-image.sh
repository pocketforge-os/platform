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
# M-1 SKELETON (tsp-1dl.1): the a523 seam still maps to today's legacy `image` build
# (a523 = boards/tsp-s/assemble-sd.sh + build-rootfs-a523.sh), which is device-specific
# and NOT cleanly BOARD-parameterized. The a133 legacy assemble (`make build-image` with
# substrate mounts) was RETIRED (B4 / tsp-1dl.4.5; code removed tsp-7xe) — a133 now builds
# via the container multistage (image/build/Dockerfile.pf, PF_ENGINE=docker default), not
# this hook. The a523 branch stays until the A523 migration onto pf build (tsp-jet). Until
# then this hook prints the legacy invocation (DRY by default); set PF_DRY_RUN=0 to actually
# shell it (requires the legacy env: BLOBS_SRC/KERNEL_*_SRC/GPU_*_SRC/LIBSDL3_SRC).
set -euo pipefail
: "${PF_IMAGE_REPO:?set PF_IMAGE_REPO to the image-repo checkout (M-1 legacy build)}"
case "$PF_DEVICE_ID" in
  a133) echo "[sunxi/assemble_image] a133 legacy assemble is RETIRED (tsp-7xe) — build via the container multistage (pf build, PF_ENGINE=docker default), not the hooks seam." >&2; exit 2 ;;
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
