#!/usr/bin/env bash
# families/sunxi/assemble-image.sh — sunxi FAMILY hook: assemble_image.
#
# RETIRED SKELETON (tsp-1dl.1 → fully dead post-tsp-jet). This hook is ONLY reached
# via the PF_ENGINE=hooks seam demo (dry/test path); the LIVE os-image build is the
# multistage docker path (pf_os_image_dockerbuild → image/build/Dockerfile.pf,
# PF_ENGINE=docker default), which never calls this hook. BOTH sunxi devices now
# assemble in-container:
#   - a133 legacy assemble retired B4 / tsp-1dl.4.5 (host code removed tsp-7xe).
#   - a523 legacy assemble retired by tsp-jet (A523 migrated onto pf build; the old
#     boards/tsp-s/assemble-sd.sh host flow + pocketforge-automation build-a523-*.sh gone).
# So this hook now exits 2 for every device — a stale seam dispatch fails loud instead
# of resurrecting a legacy host flow. The real assemble is the Dockerfile.pf `assemble` stage.
set -euo pipefail
case "${PF_DEVICE_ID:-}" in
  a133) echo "[sunxi/assemble_image] a133 legacy assemble RETIRED (tsp-7xe) — build via the container multistage (pf build, PF_ENGINE=docker default), not this hook." >&2 ;;
  a523) echo "[sunxi/assemble_image] a523 legacy assemble RETIRED (tsp-jet) — build via the container multistage (pf build, PF_ENGINE=docker default), not this hook." >&2 ;;
  *)    echo "[sunxi/assemble_image] no legacy assemble mapping for device=${PF_DEVICE_ID:-<unset>} — sunxi assembles via pf build (Dockerfile.pf)." >&2 ;;
esac
exit 2
