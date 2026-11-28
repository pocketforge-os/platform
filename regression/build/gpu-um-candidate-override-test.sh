#!/usr/bin/env bash
# Unit-test pf_gpu_um_candidate_override (tsp-hqm1p.182.949.6): the dev-only, non-hermetic
# gpu-um-tsp candidate override that rewrites the gpu-um SHA in the build-arg surface so
# `PF_GPU_UM_SHA=<candidate> pf build --variant dev` (e.g. PF_BUILD_STAGE_TARGET=
# component-test-gpu-um) builds the candidate with the image's own gpu-um recipe instead of
# silently building the platform.lock pin. Also tests pf_write_candidate_record, the durable
# $PF_OUT_DIR/candidate-overrides.env record of either candidate override.
# The functions under test are eval'd from core/pf-build.sh, so shellcheck cannot see
# their reads of VARIANT / PF_*_SHA / PF_CANDIDATE_*.
# shellcheck disable=SC2034
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/core/pf-build.sh"

# Extract the shipped functions and drive them directly (same pattern as
# image-candidate-override-test).
extract() { sed -n "/^$1()/,/^}/p" "$BUILD"; }
for fn in pf_gpu_um_candidate_override pf_image_candidate_override pf_write_candidate_record; do
    src="$(extract "$fn")"
    [ -n "$src" ] || { echo "FAIL: core/pf-build.sh has no $fn()" >&2; exit 1; }
    eval "$src"
done

LOCK_PIN=1111111111111111111111111111111111111111
CAND=2222222222222222222222222222222222222222
IMG_PIN=3333333333333333333333333333333333333333
IMG_CAND=4444444444444444444444444444444444444444
sample_ba() {
    printf 'PF_KERNEL_SHA=deadbeef\nPF_IMAGE_SHA=%s\nPF_GPU_MODEL=open\nPF_GPU_UM_REPO=gpu-um-tsp\nPF_GPU_UM_SHA=%s\nPF_GPU_UM_SHA_X=keep\n' \
        "$IMG_PIN" "$LOCK_PIN"
}
reset_candidates() {
    PF_CANDIDATE_IMAGE_SHA=""; PF_CANDIDATE_IMAGE_LOCK_PIN=""
    PF_CANDIDATE_GPU_UM_SHA=""; PF_CANDIDATE_GPU_UM_LOCK_PIN=""
}

# pf_log captures to LOG; pf_die prints + exits (fatal, as in a real build).
LOG=""
pf_log() { LOG="$LOG$*"$'\n'; }
pf_die() { printf 'DIE: %s\n' "$*" >&2; exit 3; }

ERR="$(mktemp)"
TMPD="$(mktemp -d)"
trap 'rm -rf "$ERR" "$TMPD"' EXIT

# expect_die <message-substring> <ba> <variant> <sha>: run the override in a subshell and
# require exit 3 with the named pf_die message.
expect_die() {
    local want="$1" in_ba="$2" in_variant="$3" in_sha="$4" rc=0
    ( ba="$in_ba"; VARIANT="$in_variant"; PF_GPU_UM_SHA="$in_sha"; reset_candidates; \
      pf_log() { :; }; pf_die() { printf 'DIE: %s\n' "$*" >&2; exit 3; }; \
      pf_gpu_um_candidate_override ) 2>"$ERR" || rc=$?
    test "$rc" -eq 3 || { echo "FAIL: expected die ($want), rc=$rc" >&2; exit 1; }
    grep -qF "$want" "$ERR" || { echo "FAIL: missing die message '$want':" >&2; cat "$ERR" >&2; exit 1; }
}

# --- 1. No PF_GPU_UM_SHA -> ba untouched, no override log, no candidate recorded ---------
LOG=""; ba="$(sample_ba)"; VARIANT=dev; reset_candidates; unset PF_GPU_UM_SHA
pf_gpu_um_candidate_override
test "$ba" = "$(sample_ba)"
! grep -q 'NON-HERMETIC CANDIDATE' <<<"$LOG"
test -z "$PF_CANDIDATE_GPU_UM_SHA"
LOG=""; ba="$(sample_ba)"; PF_GPU_UM_SHA=""
pf_gpu_um_candidate_override
test "$ba" = "$(sample_ba)"
test -z "$LOG"
echo 'ok 1 - unset/empty PF_GPU_UM_SHA is a no-op'

# --- 2. dev + candidate != lock -> gpu-um sha flips, ONLY that line changes ---------------
LOG=""; ba="$(sample_ba)"; VARIANT=dev; reset_candidates; PF_GPU_UM_SHA="$CAND"
pf_gpu_um_candidate_override
grep -qx "PF_GPU_UM_SHA=$CAND" <<<"$ba"
! grep -qx "PF_GPU_UM_SHA=$LOCK_PIN" <<<"$ba"
sb="$(sample_ba)"
test "$(grep -c . <<<"$ba")" -eq "$(grep -c . <<<"$sb")"
test "$(grep -c '^PF_GPU_UM_SHA=' <<<"$ba")" -eq 1
diff <(sample_ba | grep -v '^PF_GPU_UM_SHA=') <(printf '%s\n' "$ba" | grep -v '^PF_GPU_UM_SHA=')
grep -qx 'PF_GPU_UM_SHA_X=keep' <<<"$ba"
grep -qx "PF_IMAGE_SHA=$IMG_PIN" <<<"$ba"
grep -qF "!!! NON-HERMETIC CANDIDATE: gpu-um-src overridden to $CAND (lock pin was $LOCK_PIN) — dev validation only, NEVER a release artifact" <<<"$LOG"
test "$PF_CANDIDATE_GPU_UM_SHA" = "$CAND"
test "$PF_CANDIDATE_GPU_UM_LOCK_PIN" = "$LOCK_PIN"
echo 'ok 2 - dev candidate flips only the gpu-um sha and logs the marker'

# --- 3. dev + candidate == lock pin -> no override, "matches" log -------------------------
LOG=""; ba="$(sample_ba)"; VARIANT=dev; reset_candidates; PF_GPU_UM_SHA="$LOCK_PIN"
pf_gpu_um_candidate_override
test "$ba" = "$(sample_ba)"
grep -q 'matches the platform.lock gpu-um pin' <<<"$LOG"
! grep -q 'NON-HERMETIC CANDIDATE' <<<"$LOG"
test -z "$PF_CANDIDATE_GPU_UM_SHA"
echo 'ok 3 - candidate equal to the lock pin is a hermetic no-op'

# --- 4. malformed sha -> fatal ------------------------------------------------------------
for bad in short 22222222222222222222222222222222222222 222222222222222222222222222222222222222g \
           2222222222222222222222222222222222222222X 22222222222222222222222222222222222222AB \
           ' 222222222222222222222222222222222222222' '222222222222222222222222222222222222222'$'\n'; do
    expect_die 'PF_GPU_UM_SHA must be exactly 40 lowercase hex' "$(sample_ba)" dev "$bad"
done
echo 'ok 4 - malformed candidate sha is fatal'

# --- 5. non-dev variant -> fatal (dev-only) -----------------------------------------------
for v in release ci ""; do
    expect_die 'PF_GPU_UM_SHA candidate override is dev-only' "$(sample_ba)" "$v" "$CAND"
done
echo 'ok 5 - non-dev variant refuses the override'

# --- 6. non-open GPU model -> fatal (a ddk/closed profile has no gpu-um) -------------------
expect_die "requires PF_GPU_MODEL=open" "$(sample_ba | sed 's/^PF_GPU_MODEL=open$/PF_GPU_MODEL=ddk/')" dev "$CAND"
expect_die "requires PF_GPU_MODEL=open" "$(sample_ba | grep -v '^PF_GPU_MODEL=')" dev "$CAND"
echo 'ok 6 - non-open GPU model refuses the override'

# --- 7. missing PF_GPU_UM_SHA line in ba -> fatal -----------------------------------------
expect_die "has no PF_GPU_UM_SHA pin" "$(sample_ba | grep -v '^PF_GPU_UM_SHA=')" dev "$CAND"
expect_die "has no PF_GPU_UM_SHA pin" "$(sample_ba | sed 's/^PF_GPU_UM_SHA=.*/PF_GPU_UM_SHA=/')" dev "$CAND"
echo 'ok 7 - missing gpu-um pin refuses the override'

# --- 8. candidate record: absent with no override, stale one removed ----------------------
PF_OUT_DIR="$TMPD/out"; mkdir -p "$PF_OUT_DIR"
reset_candidates
echo 'PF_CANDIDATE_GPU_UM_SHA=stale' >"$PF_OUT_DIR/candidate-overrides.env"
pf_write_candidate_record
test ! -e "$PF_OUT_DIR/candidate-overrides.env"
pf_write_candidate_record
test ! -e "$PF_OUT_DIR/candidate-overrides.env"
echo 'ok 8 - no override writes no record and removes a stale one'

# --- 9. record for the gpu-um override alone -----------------------------------------------
LOG=""; ba="$(sample_ba)"; VARIANT=dev; reset_candidates; unset PF_IMAGE_SHA; PF_GPU_UM_SHA="$CAND"
pf_image_candidate_override
pf_gpu_um_candidate_override
pf_write_candidate_record
diff <(printf 'PF_CANDIDATE_GPU_UM_SHA=%s\nPF_CANDIDATE_GPU_UM_LOCK_PIN=%s\n' "$CAND" "$LOCK_PIN") \
     "$PF_OUT_DIR/candidate-overrides.env"
echo 'ok 9 - gpu-um override writes its record'

# --- 10. record for the image override alone -----------------------------------------------
LOG=""; ba="$(sample_ba)"; VARIANT=dev; reset_candidates; PF_IMAGE_SHA="$IMG_CAND"; unset PF_GPU_UM_SHA
pf_image_candidate_override
pf_gpu_um_candidate_override
pf_write_candidate_record
diff <(printf 'PF_CANDIDATE_IMAGE_SHA=%s\nPF_CANDIDATE_IMAGE_LOCK_PIN=%s\n' "$IMG_CAND" "$IMG_PIN") \
     "$PF_OUT_DIR/candidate-overrides.env"
echo 'ok 10 - image override writes its record'

# --- 11. record for both overrides ---------------------------------------------------------
LOG=""; ba="$(sample_ba)"; VARIANT=dev; reset_candidates; PF_IMAGE_SHA="$IMG_CAND"; PF_GPU_UM_SHA="$CAND"
pf_image_candidate_override
pf_gpu_um_candidate_override
pf_write_candidate_record
diff <(printf 'PF_CANDIDATE_IMAGE_SHA=%s\nPF_CANDIDATE_IMAGE_LOCK_PIN=%s\nPF_CANDIDATE_GPU_UM_SHA=%s\nPF_CANDIDATE_GPU_UM_LOCK_PIN=%s\n' \
        "$IMG_CAND" "$IMG_PIN" "$CAND" "$LOCK_PIN") \
     "$PF_OUT_DIR/candidate-overrides.env"
echo 'ok 11 - both overrides are recorded'

# --- 12. a pin-equal candidate (no override) records nothing --------------------------------
LOG=""; ba="$(sample_ba)"; VARIANT=dev; reset_candidates; PF_IMAGE_SHA="$IMG_PIN"; PF_GPU_UM_SHA="$LOCK_PIN"
pf_image_candidate_override
pf_gpu_um_candidate_override
pf_write_candidate_record
test ! -e "$PF_OUT_DIR/candidate-overrides.env"
echo 'ok 12 - pin-equal candidates record nothing'

# --- 13. wiring: called in the current shell right after the image override, before the
#         stage-only exit, the gpu-um epoch read and the staging; record before staging ------
body="$(extract pf_os_image_dockerbuild)"
ln_of() { grep -nF -- "$1" <<<"$body" | head -n1 | cut -d: -f1; }
img_ln="$(ln_of '    pf_image_candidate_override')"
gum_ln="$(ln_of '    pf_gpu_um_candidate_override')"
stage_only_ln="$(ln_of 'pf_stage_only_sources "$ba"')"
epoch_ln="$(ln_of "gpu_um_sha=\"\$(printf '%s\\n' \"\$ba\"")"
rec_ln="$(ln_of '    pf_write_candidate_record')"
stage_ln="$(ln_of '    pf_stage_sources "$src_dir" "$ba"')"
for n in img_ln gum_ln stage_only_ln epoch_ln rec_ln stage_ln; do
    [ -n "${!n}" ] || { echo "FAIL: pf_os_image_dockerbuild wiring: $n not found" >&2; exit 1; }
done
test "$gum_ln" -eq $((img_ln + 1))
test "$gum_ln" -lt "$stage_only_ln"
test "$gum_ln" -lt "$epoch_ln"
test "$rec_ln" -lt "$stage_ln"
grep -q 'PF_CANDIDATE_GPU_UM_SHA=""' "$BUILD"
echo 'ok 13 - override and record are wired into pf_os_image_dockerbuild'

echo 'PASS: pf_gpu_um_candidate_override is dev-only, open-only, hex-validated, surgical and recorded'
