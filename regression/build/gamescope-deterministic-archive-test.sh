#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/a/sub" "$tmp/b/sub" "$tmp/store-a" "$tmp/store-b" "$tmp/store-b-lock"
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
archiver=${ARCHIVER:-"$root/core/gamescope-deterministic-archive.py"}
python3 "$archiver" "${args[@]/SOURCE/$tmp/a}" --store "$tmp/store-a"
python3 "$archiver" "${args[@]/SOURCE/$tmp/b}" --store "$tmp/store-b"
archive_a=$(find "$tmp/store-a" -name '*.tar' -print -quit)
archive_b=$(find "$tmp/store-b" -name '*.tar' -print -quit)
test "$(basename "$archive_a")" = "$(basename "$archive_b")"
test -L "$tmp/a/link"
test -L "$tmp/b/link"
# The fixture includes a source symlink; reject tar's type-column marker (lrwx...).
test -z "$(LC_ALL=C tar -tvf "$archive_a" | grep -E '^l' || true)"
test -f "$archive_a.json"
python3 "$archiver" "${args[@]/SOURCE/$tmp/a}" --store "$tmp/store-b-lock" \
    --lock-sha256 "$(sha different-lock)"
archive_lock=$(find "$tmp/store-b-lock" -name '*.tar' -print -quit)
test "$(basename "$archive_a")" != "$(basename "$archive_lock")"
echo 'PASS: Gamescope deterministic publication is byte-identical and symlink-free'
