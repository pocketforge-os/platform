#!/usr/bin/env bash
# Fail in platform CI when the declared Gamescope series drifts from the pin that
# platform.lock resolves. Build 10 shipped exactly that drift: the lock moved to
# d62ee165 while devices/a133-open-7x-gpu/profile.toml still declared Build 9's
# 37-id table, so core/stage-gamescope-source.py refused the real image build
# with "Gamescope patch identities/order do not match the admitted series" and
# nothing on this side of the build caught it first.
#
# gamescope-series-witness.json is a committed regeneration record, not a
# recompute: recomputing needs the gamescope objects, and this suite is
# documented as seconds-long and side-effect-free (no network, no docker). The
# witness ties together the three things that must move atomically on a pin move
# - the head platform.lock resolves (read back through core/profile.py, never
# from the lock text), the id table the profile declares, and the digests derived
# from that exact series. Its own limits are stated in the PR that added it: a
# wrongly generated witness passes here and is still caught at build time, where
# stage-gamescope-source.py recomputes the series from the mirror.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd "$HERE/../.." >/dev/null 2>&1 && pwd)"
WITNESS="$HERE/gamescope-series-witness.json"
PROFILE="${PF_WITNESS_PROFILE:-$ROOT/devices/a133-open-7x-gpu/profile.toml}"
TMP="$(mktemp -d "${RUNNER_TEMP:-/tmp}/gamescope-series-witness.XXXXXX")"
trap 'find "$TMP" -mindepth 1 -delete; rmdir "$TMP"' EXIT

locked_head="$(cd "$ROOT" && python3 core/profile.py buildargs a133-open-7x-gpu |
    awk -F= '$1 == "PF_GAMESCOPE_SHA" { print $2 }')"
if [ -z "$locked_head" ]; then
    printf 'gamescope_series_witness=FAIL reason=locked_head_unreadable\n' >&2
    exit 1
fi

check() { # <witness> <profile> <locked-head>
    python3 -B - "$1" "$2" "$3" <<'PY'
import hashlib, json, pathlib, sys, tomllib

def fail(reason: str) -> None:
    print(f"gamescope_series_witness=FAIL reason={reason}")
    sys.exit(1)

witness = json.loads(pathlib.Path(sys.argv[1]).read_text())
profile = tomllib.loads(pathlib.Path(sys.argv[2]).read_text())["gamescope"]
head = sys.argv[3]
ids = list(profile["required_patch_ids"])
if witness["integrated_head"] != head:
    fail(f"head_drift witness={witness['integrated_head']} locked={head}")
if witness["upstream_base"] != profile["upstream_base"]:
    fail(f"upstream_base_drift declared={profile['upstream_base']}")
if len(ids) != witness["patch_count"]:
    fail(f"patch_count_drift declared={len(ids)} witness={witness['patch_count']}")
joined = hashlib.sha256(" ".join(ids).encode()).hexdigest()
if joined != witness["patch_ids_sha256"]:
    fail(f"patch_ids_drift declared_sha256={joined} witness={witness['patch_ids_sha256']}")
for key in ("patch_series_sha256", "source_tree_sha256",
            "dependency_manifest_sha256", "license_sha256"):
    if profile[key] != witness[key]:
        fail(f"{key}_drift declared={profile[key]} witness={witness[key]}")
print(f"gamescope_series_witness=PASS head={head} patch_count={len(ids)} "
      f"patch_ids_sha256={joined} patch_series_sha256={profile['patch_series_sha256']} "
      f"source_tree_sha256={profile['source_tree_sha256']}")
PY
}

mutate_ids() { # <mode: drop|corrupt> <out-profile>
    python3 -B - "$1" "$PROFILE" "$2" <<'PY'
import pathlib, re, sys
mode, source, target = sys.argv[1], pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
lines = source.read_text().splitlines(keepends=True)
hits = [i for i, line in enumerate(lines)
        if re.fullmatch(r'  "[0-9a-f]{40}",?', line.rstrip("\n"))]
if len(hits) < 2:
    raise SystemExit(f"unexpected id table shape hits={len(hits)}")
if mode == "drop":
    del lines[hits[-1]]
elif mode == "corrupt":
    index = hits[-1]
    lines[index] = lines[index].replace("54a1c8af", "54a1c8a0") \
        if "54a1c8af" in lines[index] else re.sub(r"[0-9a-f]", "0", lines[index], count=1)
else:
    raise SystemExit(f"unknown mode {mode}")
target.write_text("".join(lines))
PY
}

expect_pass() { # <label>
    local out
    if ! out="$(check "$WITNESS" "$PROFILE" "$locked_head")"; then
        printf 'positive control (%s) failed unexpectedly: %s\n' "$1" "${out:0:300}" >&2
        exit 1
    fi
    case "$out" in
        gamescope_series_witness=PASS*) printf '%s\n' "$out" ;;
        *) printf 'positive control (%s) printed: %s\n' "$1" "$out" >&2; exit 1 ;;
    esac
}

expect_reason() { # <expected-reason-prefix> <witness> <profile> <label>
    local out rc=0
    out="$(check "$2" "$3" "$locked_head")" || rc=$?
    if [ "$rc" -eq 0 ]; then
        printf 'negative control (%s) passed when it must fail\n' "$4" >&2
        exit 1
    fi
    case "$out" in
        "gamescope_series_witness=FAIL reason=$1"*) printf 'negative control (%s) refused as designed: %s\n' "$4" "$out" ;;
        *) printf 'negative control (%s) refused with the wrong reason: %s\n' "$4" "$out" >&2; exit 1 ;;
    esac
}

expect_pass "committed tree"

# Build 10's exact drift: the lock moved on, the declared table did not.
python3 -B -c 'import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text())
value["integrated_head"] = "0" * 40
pathlib.Path(sys.argv[2]).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")' \
    "$WITNESS" "$TMP/witness-stale-head.json"
expect_reason "head_drift" "$TMP/witness-stale-head.json" "$PROFILE" "lock moved, table not regenerated"

mutate_ids drop "$TMP/profile-short.toml"
expect_reason "patch_count_drift" "$WITNESS" "$TMP/profile-short.toml" "declared table lost an id"

mutate_ids corrupt "$TMP/profile-corrupt.toml"
expect_reason "patch_ids_drift" "$WITNESS" "$TMP/profile-corrupt.toml" "declared id altered"

python3 -B -c 'import pathlib, sys
text = pathlib.Path(sys.argv[1]).read_text()
old = "8efb6b69d787e9054def5b9e08e2332e14249e69465de80dfcd91a951bb878ca"
assert text.count(old) == 1, text.count(old)
pathlib.Path(sys.argv[2]).write_text(text.replace(old, "0" * 64))' \
    "$PROFILE" "$TMP/profile-series.toml"
expect_reason "patch_series_sha256_drift" "$WITNESS" "$TMP/profile-series.toml" "series digest stale"

echo "PASS: the declared Gamescope series matches the pinned head and its witness"
