#!/usr/bin/env bash
# Unit-test pf_image_candidate_override (tsp-hqm1p.17.13): the dev-only, non-hermetic
# image-repo candidate override that rewrites the image SHA in the build-arg surface so
# `pf build --variant dev` with PF_IMAGE_SHA=<candidate> actually stages the candidate
# instead of silently archiving the platform.lock pin.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/core/pf-build.sh"

# Extract the shipped function and drive it directly (same pattern as gpu-um-staging-test).
extract() { sed -n "/^$1()/,/^}/p" "$BUILD"; }
eval "$(extract pf_image_candidate_override)"

LOCK_PIN=1111111111111111111111111111111111111111
CAND=2222222222222222222222222222222222222222
sample_ba() { printf 'PF_KERNEL_SHA=deadbeef\nPF_IMAGE_SHA=%s\nPF_GPU_MODEL=open\n' "$LOCK_PIN"; }

# pf_log captures to LOG; pf_die prints + exits (fatal, as in a real build).
LOG=""
pf_log() { LOG="$LOG$*"$'\n'; }
pf_die() { printf 'DIE: %s\n' "$*" >&2; exit 3; }

# --- 1. No PF_IMAGE_SHA -> ba untouched, no override log --------------------------------
LOG=""; ba="$(sample_ba)"; VARIANT=dev; unset PF_IMAGE_SHA
pf_image_candidate_override
test "$ba" = "$(sample_ba)"
! grep -q 'NON-HERMETIC CANDIDATE' <<<"$LOG"
echo 'ok 1 - empty PF_IMAGE_SHA is a no-op'

# --- 2. dev + candidate != lock -> image sha flips, ONLY that line changes --------------
LOG=""; ba="$(sample_ba)"; VARIANT=dev; PF_IMAGE_SHA="$CAND"
pf_image_candidate_override
grep -qx "PF_IMAGE_SHA=$CAND" <<<"$ba"
! grep -qx "PF_IMAGE_SHA=$LOCK_PIN" <<<"$ba"
# every non-image line is preserved verbatim
grep -qx 'PF_KERNEL_SHA=deadbeef' <<<"$ba"
grep -qx 'PF_GPU_MODEL=open' <<<"$ba"
test "$(grep -c . <<<"$ba")" -eq 3
grep -q "NON-HERMETIC CANDIDATE: image-src overridden to $CAND" <<<"$LOG"
echo 'ok 2 - dev candidate flips only the image sha and logs the override'

# --- 3. dev + candidate == lock pin -> no override, "matches" log -----------------------
LOG=""; ba="$(sample_ba)"; VARIANT=dev; PF_IMAGE_SHA="$LOCK_PIN"
pf_image_candidate_override
test "$ba" = "$(sample_ba)"
grep -q 'matches the platform.lock image pin' <<<"$LOG"
! grep -q 'NON-HERMETIC CANDIDATE' <<<"$LOG"
echo 'ok 3 - candidate equal to the lock pin is a hermetic no-op'

# --- 4. dev + malformed sha -> fatal ----------------------------------------------------
for bad in short 22222222222222222222222222222222222222 222222222222222222222222222222222222222g 2222222222222222222222222222222222222222X; do
    rc=0
    ( ba="$(sample_ba)"; VARIANT=dev; PF_IMAGE_SHA="$bad"; \
      pf_log() { :; }; pf_die() { printf 'DIE: %s\n' "$*" >&2; exit 3; }; \
      eval "$(extract pf_image_candidate_override)"; \
      pf_image_candidate_override ) 2>/tmp/ico.$$ || rc=$?
    test "$rc" -eq 3
    grep -q 'must be exactly 40 lowercase hex' /tmp/ico.$$
done
rm -f /tmp/ico.$$
echo 'ok 4 - malformed candidate sha is fatal'

# --- 5. release variant + valid candidate -> fatal (dev-only) ---------------------------
rc=0
( ba="$(sample_ba)"; VARIANT=release; PF_IMAGE_SHA="$CAND"; \
  pf_log() { :; }; pf_die() { printf 'DIE: %s\n' "$*" >&2; exit 3; }; \
  eval "$(extract pf_image_candidate_override)"; \
  pf_image_candidate_override ) 2>/tmp/ico.$$ || rc=$?
test "$rc" -eq 3
grep -q 'candidate override is dev-only' /tmp/ico.$$
rm -f /tmp/ico.$$
echo 'ok 5 - release variant refuses the override'

echo 'PASS: pf_image_candidate_override is dev-only, hex-validated, and surgical'
