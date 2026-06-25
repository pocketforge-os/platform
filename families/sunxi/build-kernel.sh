#!/usr/bin/env bash
# families/sunxi/build-kernel.sh — sunxi FAMILY hook: build_kernel.
# Contract (docs/FAMILY-INTERFACE.md): in = resolved profile via PF_* env + a pinned
# kernel source checkout; out = Image + DTB + /lib/modules under $PF_OUT_DIR/kernel/.
#
# M-1 SKELETON (tsp-1dl.1): today the kernel is built OUTSIDE the container from the
# per-device repo (a133=kernel-tsp, a523=kernel-tsp-a523) and consumed by the legacy
# image build. This hook documents that mapping and exercises the dispatch seam.
#   B2 (tsp-1dl.2): collapse to kernel-sunxi (device=branch) + build-from-pinned-artifact.
#   B4 (tsp-1dl.4): build here INSIDE the multistage container from the platform.lock SHA.
set -euo pipefail
echo "[sunxi/build_kernel] device=$PF_DEVICE_ID repo=$PF_KERNEL_REPO ref=$PF_KERNEL_REF"
echo "[sunxi/build_kernel]   defconfig=$PF_KERNEL_DEFCONFIG dtb=$PF_KERNEL_DTB toolchain=${PF_TOOLCHAIN_CC:-?}"
echo "[sunxi/build_kernel] M-1: kernel produced outside the container (legacy); see B2/B4 above."
