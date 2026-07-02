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
#     blemish. The build hard-asserts: a stamped empty .scmversion (the DEFINITIVE transport-
#     independence anchor — short-circuits setlocalversion regardless of AUTO/.git); MODVERSIONS
#     not =y; no git submodules; no .git in the build tree; pinned KBUILD_BUILD_{TIMESTAMP,USER,
#     HOST} + SOURCE_DATE_EPOCH. CONFIG_LOCALVERSION_AUTO=n is recommended-not-required (WARN)
#     given .scmversion. GPU KM builds against the SAME-tree Module.symvers. (See §4.)
#   B4 (tsp-1dl.4): the real build runs INSIDE the multistage container from the platform.lock
#     SHA (image/build/Dockerfile.pf `kernel` stage, which re-asserts these invariants inline
#     against the archive tree — keep the two in lockstep). pf_kernel_assert_repro_guards()
#     below is now a HARD FAIL (tsp-1dl.4.2 flipped it from WARN); it also fronts the M-1
#     hooks-engine dispatch seam.
set -euo pipefail
echo "[sunxi/build_kernel] device=$PF_DEVICE_ID repo=$PF_KERNEL_REPO ref=$PF_KERNEL_REF"
echo "[sunxi/build_kernel]   defconfig=$PF_KERNEL_DEFCONFIG dtb=$PF_KERNEL_DTB toolchain=${PF_TOOLCHAIN_CC:-?}"

# pf_kernel_assert_repro_guards <kernel-source-dir>
# B2 contract, HARD-ENFORCED (tsp-1dl.4.2 flipped WARN -> FAIL). Checks the vermagic/repro
# invariants that make an archive build == a clone build; returns non-zero on any violation.
# Only the universally-valid asserts live here (they hold for a checkout OR an archive tree);
# the archive-specific ".git must be absent" check lives in the Dockerfile `kernel` stage.
# The .config check is skipped until a source tree with a materialized .config exists (the
# pure M-1 dispatch-seam demo has neither) — an unconfigured/absent tree is "nothing to
# assert", not a failure.
pf_kernel_assert_repro_guards() {
  local src="${1:-}" rc=0
  if [ -z "$src" ] || [ ! -d "$src" ]; then
    echo "[sunxi/build_kernel] guard: no source dir (M-1 dispatch-seam) — nothing to assert"; return 0
  fi
  if [ -f "$src/.config" ]; then
    # The definitive transport-independence anchor is the empty .scmversion the build stamps
    # (it short-circuits scripts/setlocalversion regardless of AUTO/.git — verified a133+a523,
    # tsp-1dl.4.2). So LOCALVERSION_AUTO=y is a WARN, not a FAIL: recommended-not-required
    # (KERNEL-SOURCE-STRATEGY.md §4). MODVERSIONS=y IS a hard fail (changes the .ko load gate).
    if grep -Eq '^CONFIG_LOCALVERSION_AUTO=y' "$src/.config"; then
      echo "[sunxi/build_kernel] GUARD WARN: CONFIG_LOCALVERSION_AUTO=y (defconfig does not pin =n); .scmversion neutralizes the drift, but pinning =n is cleaner"
    fi
    if grep -Eq '^CONFIG_MODVERSIONS=y' "$src/.config"; then
      echo "[sunxi/build_kernel] GUARD FAIL: CONFIG_MODVERSIONS=y -> vermagic is not the sole .ko load gate (contract assumes n)"; rc=1
    fi
  fi
  if [ -f "$src/.gitmodules" ] || git -C "$src" submodule status 2>/dev/null | grep -q .; then
    echo "[sunxi/build_kernel] GUARD FAIL: git submodules present -> archive omits them -> non-deterministic build"; rc=1
  fi
  for v in SOURCE_DATE_EPOCH KBUILD_BUILD_TIMESTAMP KBUILD_BUILD_USER KBUILD_BUILD_HOST; do
    [ -n "${!v:-}" ] || { echo "[sunxi/build_kernel] GUARD FAIL: $v unset -> non-reproducible kernel build"; rc=1; }
  done
  [ "$rc" -eq 0 ] && echo "[sunxi/build_kernel] guard: vermagic/repro invariants OK"
  return "$rc"   # HARD FAIL (tsp-1dl.4.2): any violated invariant fails the build.
}
pf_kernel_assert_repro_guards "${PF_KERNEL_SRC_DIR:-}"
echo "[sunxi/build_kernel] M-1: kernel produced outside the container (legacy); see B2/B4 above."
