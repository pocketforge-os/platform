#!/usr/bin/env bash
# regression/build/epoch-test.sh — pins the stale-mirror SOURCE_DATE_EPOCH fix (tsp-hbpd).
#
# THE BUG THIS PINS. pf_commit_epoch resolved a pinned sha from the local git source WITHOUT
# fetching and printed nothing when the sha wasn't local yet, while pf_stage_sources' targeted
# fetch ran separately and later — so the FIRST build after any platform.lock bump on a
# stale-mirror host silently omitted the SOURCE_DATE_EPOCH/PF_KERNEL_SOURCE_DATE_EPOCH
# build-args and died deep in the kernel stage's repro guard ("SOURCE_DATE_EPOCH must be
# set"); the failed run's staging fetch then made a blind retry pass, masking the bug as
# flakiness. The fix: pf_commit_epoch fetch-recovers via the shared pf_ensure_commit ladder,
# and pf_require_epoch makes a pinned-but-unresolvable epoch a HARD, NAMED orchestration-time
# failure (reason=epoch_unresolvable) instead of a silent omission.
#
# What is proven, against the REAL shipped functions (sed-extracted from core/pf-build.sh so
# the test can never drift from the code):
#   1. Hot path unchanged: a locally-present sha resolves with ZERO fetch attempts.
#   2. THE regression: a sha absent from the mirror (post-lock-bump state) is fetch-recovered
#      and its epoch resolves — pre-fix this printed EMPTY.
#   3. A genuinely unfetchable sha fails LOUDLY via pf_require_epoch with the named
#      reason=epoch_unresolvable error — the silent-omission path is gone.
#   4. Legitimate no-source cases (repo empty / "none" — e.g. a device with no source
#      bootchain) still pass through as empty without failing.
#   5. Structural pin: the epoch call sites use pf_require_epoch and both fetch ladders
#      share pf_ensure_commit.
# Everything runs in a throwaway TMP dir; no committed file or real mirror is touched.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." >/dev/null 2>&1 && pwd)"

# shellcheck source=core/lib/common.sh
. "$ROOT/core/lib/common.sh"

# Extract the shipped functions verbatim (top-level defs terminated by a bare `}`).
extract() { sed -n "/^$1()/,/^}/p" "$ROOT/core/pf-build.sh"; }
eval "$(extract pf_find_git_source; extract pf_ensure_commit; extract pf_commit_epoch; extract pf_require_epoch)"
for f in pf_find_git_source pf_ensure_commit pf_commit_epoch pf_require_epoch; do
    declare -F "$f" >/dev/null || { echo "FAIL: could not extract $f from core/pf-build.sh"; exit 1; }
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
REPO="pf-epoch-testrepo"          # name that cannot collide with a real \$HOME source
MIRRORS="$TMP/mirrors"
UPSTREAM="$TMP/upstream"
mkdir -p "$MIRRORS" "$UPSTREAM"

gitc() { git -c user.email=t@test -c user.name=t "$@"; }

# Upstream repo: commit A at a KNOWN epoch, mirror cloned while A is the tip, then commit B
# (the "lock bump") lands upstream only — the mirror is now stale exactly like a build host
# whose bare mirror predates a platform.lock bump.
EPOCH_A=1700000000
EPOCH_B=1700000100
gitc -C "$UPSTREAM" init -q
echo a > "$UPSTREAM/f"
gitc -C "$UPSTREAM" add f
GIT_AUTHOR_DATE="@$EPOCH_A +0000" GIT_COMMITTER_DATE="@$EPOCH_A +0000" \
    gitc -C "$UPSTREAM" commit -qm A
SHA_A="$(git -C "$UPSTREAM" rev-parse HEAD)"
git -C "$UPSTREAM" config uploadpack.allowAnySHA1InWant true   # allow the targeted sha fetch
git clone -q --bare "$UPSTREAM" "$MIRRORS/$REPO.git"
echo b > "$UPSTREAM/f"
gitc -C "$UPSTREAM" add f
GIT_AUTHOR_DATE="@$EPOCH_B +0000" GIT_COMMITTER_DATE="@$EPOCH_B +0000" \
    gitc -C "$UPSTREAM" commit -qm B
SHA_B="$(git -C "$UPSTREAM" rev-parse HEAD)"

echo "== 1. hot path: locally-present sha resolves with zero fetch attempts =="
out="$(pf_commit_epoch "$REPO" "$SHA_A" "$MIRRORS" 2>"$TMP/err1")"
[ "$out" = "$EPOCH_A" ] || { echo "FAIL: epoch for local sha = '$out', want $EPOCH_A"; exit 1; }
if grep -q "targeted fetch" "$TMP/err1"; then
    echo "FAIL: a fetch was attempted for a locally-present sha (hot path must stay fetch-free)"; exit 1
fi
echo "ok   - local sha resolved ($EPOCH_A), no fetch attempted"

echo "== 2. THE regression: stale-mirror sha (post-lock-bump) is fetch-recovered =="
if git --git-dir="$MIRRORS/$REPO.git" cat-file -e "${SHA_B}^{commit}" 2>/dev/null; then
    echo "FAIL: test bug — SHA_B unexpectedly present in the mirror before the test"; exit 1
fi
out="$(pf_commit_epoch "$REPO" "$SHA_B" "$MIRRORS" 2>"$TMP/err2")"
[ "$out" = "$EPOCH_B" ] || { echo "FAIL: epoch for stale-mirror sha = '$out', want $EPOCH_B (pre-fix behavior was EMPTY)"; exit 1; }
grep -q "targeted fetch" "$TMP/err2" || { echo "FAIL: expected a targeted-fetch log line"; exit 1; }
echo "ok   - missing sha fetched and resolved ($EPOCH_B) — the pre-fix silent-empty path is dead"

echo "== 3. unfetchable sha fails LOUDLY and NAMED via pf_require_epoch =="
git --git-dir="$MIRRORS/$REPO.git" remote set-url origin "$TMP/nonexistent"
BOGUS="$(printf 'deadbeef%.0s' 1 2 3 4 5)"   # 40 hex chars, guaranteed absent
set +e
out="$( pf_require_epoch "$REPO" "$BOGUS" "$MIRRORS" 2>"$TMP/err3" )"
rc=$?
set -e
[ "$rc" -ne 0 ] || { echo "FAIL: pf_require_epoch exited 0 for an unresolvable sha"; exit 1; }
[ -z "$out" ]   || { echo "FAIL: pf_require_epoch printed '$out' for an unresolvable sha"; exit 1; }
grep -q "reason=epoch_unresolvable repo=$REPO sha=$BOGUS" "$TMP/err3" \
    || { echo "FAIL: missing the named reason=epoch_unresolvable error:"; cat "$TMP/err3"; exit 1; }
echo "ok   - hard, named failure at the orchestration layer (reason=epoch_unresolvable)"

echo "== 4. legitimate no-source cases still pass through empty =="
for spec in "|sha-irrelevant" "none|$SHA_A" "$REPO|"; do
    IFS='|' read -r r s <<< "$spec"
    out="$(pf_require_epoch "$r" "$s" "$MIRRORS")" || { echo "FAIL: pf_require_epoch failed for repo='$r' sha='$s'"; exit 1; }
    [ -z "$out" ] || { echo "FAIL: expected empty epoch for repo='$r' sha='$s', got '$out'"; exit 1; }
done
echo "ok   - empty/none repo and empty sha yield empty epoch, exit 0"

echo "== 5. structural pin: call sites + shared fetch ladder =="
grep -Eq 'sde="\$\(pf_require_epoch ' "$ROOT/core/pf-build.sh" \
    || { echo "FAIL: epoch call sites no longer go through pf_require_epoch"; exit 1; }
if grep -Eq '[a-z_]*sde="\$\(pf_commit_epoch ' "$ROOT/core/pf-build.sh"; then
    echo "FAIL: an epoch call site regressed to bare pf_commit_epoch (silent-omission path)"; exit 1
fi
# pf_stage_sources must use the same pf_ensure_commit ladder (single fetch ladder, no drift).
sed -n '/^pf_stage_sources()/,/^}/p' "$ROOT/core/pf-build.sh" | grep -q 'pf_ensure_commit ' \
    || { echo "FAIL: pf_stage_sources no longer shares the pf_ensure_commit fetch ladder"; exit 1; }
echo "ok   - pf_require_epoch at the call sites; pf_ensure_commit shared by staging"

echo "EPOCH STALE-MIRROR GATE OK"
