#!/usr/bin/env bash
# families/sunxi/build-kernel.sh — sunxi FAMILY hook: build_kernel.
# Contract (docs/FAMILY-INTERFACE.md): in = resolved profile via PF_* env + a pinned
# kernel source checkout; out = Image + DTB + /lib/modules under $PF_OUT_DIR/kernel/.
#
# M-1 SKELETON (tsp-1dl.1): today the kernel is built OUTSIDE the container and consumed
# by the legacy image build. This hook documents the mapping and exercises the dispatch seam.
#
# B2 (tsp-1dl.2) — kernel topology + the source/build contract (see docs/KERNEL-SOURCE-STRATEGY.md):
#   - Repos: a133 -> kernel-sunxi-4.9 (branch device/a133); a523 -> kernel-sunxi-5.15 (device/a523).
#     SPLIT per (family, kernel-line); device=branch within a line. GPU stays per-IP.
#   - SOURCE TRANSPORT: bare-mirror-per-host + `git worktree` (NEVER `git clone --reference`).
#   - BUILD INPUT: a `git archive` of the platform.lock SHA COPYied into the build stage —
#     NOT a live clone (air-gap-safe; object provenance is irrelevant to output bytes).
#   - VERMAGIC GUARD (load-bearing): we run MODVERSIONS=n, so vermagic is the ONLY .ko load
#     gate — an archive-build version drift = a SILENT GPU-KM load failure, not just a repro
#     blemish. The build MUST hard-assert: CONFIG_LOCALVERSION_AUTO=n; a stamped LOCALVERSION
#     (empty or .scmversion from the lock SHA); the GPU KM built against the SAME-tree
#     Module.symvers; no git submodules; pinned KBUILD_BUILD_{TIMESTAMP,USER,HOST} + SOURCE_DATE_EPOCH.
#   B4 (tsp-1dl.4): build here INSIDE the multistage container from the platform.lock SHA, and
#     ENFORCE the asserts above (this skeleton only documents + emits them as warnings).
set -euo pipefail
echo "[sunxi/build_kernel] device=$PF_DEVICE_ID repo=$PF_KERNEL_REPO ref=$PF_KERNEL_REF"
echo "[sunxi/build_kernel]   defconfig=$PF_KERNEL_DEFCONFIG dtb=$PF_KERNEL_DTB toolchain=${PF_TOOLCHAIN_CC:-?}"

# pf_kernel_assert_repro_guards <kernel-source-dir>
# B2 contract, enforced in B4. Emits WARN today (M-1 builds outside the container); becomes a
# hard FAIL once the build runs here. Checks the vermagic/archive-build invariants above.
pf_kernel_assert_repro_guards() {
  local src="${1:-}" rc=0
  [ -n "$src" ] && [ -d "$src" ] || { echo "[sunxi/build_kernel] guard: no source dir (M-1 skeleton) — skipped"; return 0; }
  if grep -Eq '^CONFIG_LOCALVERSION_AUTO=y' "$src/.config" 2>/dev/null; then
    echo "[sunxi/build_kernel] WARN: CONFIG_LOCALVERSION_AUTO=y -> archive-build vermagic drift -> SILENT .ko load failure"; rc=1; fi
  if git -C "$src" submodule status 2>/dev/null | grep -q .; then
    echo "[sunxi/build_kernel] WARN: git submodules present -> non-deterministic archive build"; rc=1; fi
  for v in SOURCE_DATE_EPOCH KBUILD_BUILD_TIMESTAMP KBUILD_BUILD_USER KBUILD_BUILD_HOST; do
    [ -n "${!v:-}" ] || { echo "[sunxi/build_kernel] WARN: $v unset -> non-reproducible kernel build"; rc=1; }
  done
  [ "$rc" -eq 0 ] && echo "[sunxi/build_kernel] guard: vermagic/repro invariants OK"
  return 0   # M-1: never fail the dispatch seam; B4 flips this to `return $rc`.
}
pf_kernel_assert_repro_guards "${PF_KERNEL_SRC_DIR:-}"
echo "[sunxi/build_kernel] M-1: kernel produced outside the container (legacy); see B2/B4 above."
