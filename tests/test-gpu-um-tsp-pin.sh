#!/bin/bash
# Test that the gpu-um-tsp pin in platform.lock matches the expected value.
set -euo pipefail
EXPECTED_SHA="6d641070c7725389ab3e3f9db94d20109f5a0962"
LOCK="$(dirname "$0")/../platform.lock"
ACTUAL_SHA=$(awk '
  /^\[\[repos\]\]/ { in_repo = 0 }
  /^name = "gpu-um-tsp"/ { in_repo = 1 }
  in_repo && /^sha  = "/ {
    split($0, parts, "\"")
    print parts[2]
    exit
  }
' "$LOCK")
if [ "$ACTUAL_SHA" = "$EXPECTED_SHA" ]; then
  echo "PASS: gpu-um-tsp pin is $EXPECTED_SHA"
  exit 0
else
  echo "FAIL: gpu-um-tsp pin is ${ACTUAL_SHA:-<missing>}, expected $EXPECTED_SHA"
  exit 1
fi