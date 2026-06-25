#!/usr/bin/env bash
# ci/core-purity-check.sh — assert core/ is SoC-agnostic: it contains ZERO family
# vocabulary. The core owns everything BETWEEN the family hooks; the FAMILIES own all
# SoC/boot/flash vocabulary. If a banned token appears in core/, the seam (§3) leaked
# — fix the seam, not the gate. (infra-014 §3; B8 / tsp-1dl.8 makes this a CI gate +
# extends it to "core/ did NOT change to onboard a new family".)
#
# Add a trailing `# pf-purity-allow` to a line for a rare legitimate mention.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." >/dev/null 2>&1 && pwd)"

# Case-sensitive family vocabulary. Short uppercase tokens are word-bounded so they
# don't match substrings. Extend as new families land (snapdragon already listed).
BANNED='boot0|BL31|dragonsecboot|boot_package|genimage|\bFEL\b|\bSPL\b|fastboot|\bXBL\b|Firehose|\bEDL\b|mkbootimg|extlinux'
fail=0
while IFS= read -r -d '' f; do
    hits="$(grep -nE "$BANNED" "$f" 2>/dev/null | grep -v 'pf-purity-allow' || true)"
    if [ -n "$hits" ]; then
        echo "CORE PURITY VIOLATION in ${f#"$ROOT"/}:"
        printf '%s\n' "$hits" | sed 's/^/  /'
        fail=1
    fi
done < <(find "$ROOT/core" -type f -print0)

if [ "$fail" = 0 ]; then
    echo "core-purity: OK — core/ contains no family vocabulary"
fi
exit "$fail"
