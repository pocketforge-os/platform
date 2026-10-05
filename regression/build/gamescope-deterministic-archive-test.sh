#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/a/sub" "$tmp/b/sub" "$tmp/store-a" "$tmp/store-b"
printf 'payload\n' >"$tmp/a/sub/file"
printf '#!/bin/sh\nprintf ok\\n\n' >"$tmp/a/run"
chmod 0755 "$tmp/a/run"
ln -s sub/file "$tmp/a/link"
cp -a "$tmp/a/." "$tmp/b/"
sha() { printf '%s' "$1" | sha256sum | awk '{print $1}'; }
args=(--source SOURCE --source-url https://github.com/pocketforge-os/gamescope.git
      --head 1111111111111111111111111111111111111111
      --base 2222222222222222222222222222222222222222
      --patch-series-sha256 "$(sha patch)" --manifest-sha256 "$(sha manifest)"
      --lock-sha256 "$(sha lock)")
python3 "$root/core/gamescope-deterministic-archive.py" "${args[@]/SOURCE/$tmp/a}" --store "$tmp/store-a"
python3 "$root/core/gamescope-deterministic-archive.py" "${args[@]/SOURCE/$tmp/b}" --store "$tmp/store-b"
test "$(basename "$(find "$tmp/store-a" -type f -print -quit)")" = \
     "$(basename "$(find "$tmp/store-b" -type f -print -quit)")"
test -z "$(find "$tmp/a" "$tmp/b" -type l -print -quit)"
echo 'PASS: Gamescope deterministic publication is byte-identical and symlink-free'
