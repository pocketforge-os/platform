#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENTRY="$ROOT/scripts/pf-ci-buildx"
T="$(mktemp -d "${RUNNER_TEMP:-/tmp}/platform-pf-ci-buildx-test.XXXXXX")"
cleanup_test() {
    find "$T" -mindepth 1 -delete
    rmdir "$T"
}
trap cleanup_test EXIT
mkdir -p "$T/bin" "$T/state"

cat > "$T/bin/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$PF_TEST_STATE/docker.calls"
case "$1 $2" in
    "buildx inspect") [ -e "$PF_TEST_STATE/builder" ] ;;
    "buildx create")
        : > "$PF_TEST_STATE/builder"
        while [ "$#" -gt 0 ]; do
            if [ "$1" = --config ]; then
                cp -- "$2" "$PF_TEST_STATE/effective-config.toml"
                break
            fi
            shift
        done
        [ "${PF_TEST_CREATE_FAIL:-0}" != 1 ] || exit 8
        ;;
    "buildx build")
        if [ "${PF_TEST_BUILD_SIGNAL:-}" = TERM ]; then
            kill -TERM "$PPID"
        fi
        [ "${PF_TEST_BUILD_FAIL:-0}" != 1 ] || exit 7
        # PF_TEST_FAIL_PROXIED=<rc> fails only the builds that carry the apt cache.
        if [ -n "${PF_TEST_FAIL_PROXIED:-}" ] \
            && printf '%s\n' "$*" | grep -q -- '--build-arg http_proxy='; then
            exit "$PF_TEST_FAIL_PROXIED"
        fi
        ;;
    "buildx prune") [ "${PF_TEST_PRUNE_FAIL:-0}" != 1 ] || exit 9 ;;
    "buildx rm")
        if [ "${3:-}" = --force ]; then
            [ "${PF_TEST_FORCE_REMOVE_FAIL:-0}" != 1 ] || exit 11
        else
            [ "${PF_TEST_REMOVE_FAIL:-0}" != 1 ] || exit 10
        fi
        [ ! -e "$PF_TEST_STATE/builder" ] || unlink "$PF_TEST_STATE/builder"
        ;;
    *) exit 97 ;;
esac
SH
chmod +x "$T/bin/docker"

env -i PATH="$T/bin:/usr/bin:/bin" PF_TEST_STATE="$T/state" \
    PF_CI_BUILDX_LOCK="$T/builder.lock" PF_CI_BUILDX_NAMESERVERS=10.0.0.53 \
    RUNNER_TEMP="$T" "$ENTRY" build --load --tag pocketforge-sim:test fixture

grep -qxF 'buildx build --builder pf-ci --label org.pocketforge.cache-owner=pf-build-ci --load --tag pocketforge-sim:test fixture' \
    "$T/state/docker.calls"
grep -qxF 'buildx prune --builder pf-ci --all --force --keep-storage 8gb' \
    "$T/state/docker.calls"
grep -qxF '  nameservers = ["10.0.0.53",]' "$T/state/effective-config.toml"
# shellcheck disable=SC2016 # Assert the literal workflow variable reference.
grep -qF '"$platform_wd/scripts/pf-ci-buildx" build --load' \
    "$ROOT/.github/workflows/sim-descriptor-gate.yml"
if grep -Ev '^[[:space:]]*#' "$ROOT/.github/workflows/sim-descriptor-gate.yml" \
        | grep -Eq '^[[:space:]]*docker build([[:space:]\\]|$)'; then
    echo 'sim descriptor gate still writes the integrated builder' >&2
    exit 1
fi

: > "$T/state/docker.calls"
set +e
env -i PATH="$T/bin:/usr/bin:/bin" PF_TEST_STATE="$T/state" PF_TEST_BUILD_FAIL=1 \
    PF_CI_BUILDX_LOCK="$T/builder.lock" PF_CI_BUILDX_NAMESERVERS=10.0.0.53 \
    RUNNER_TEMP="$T" "$ENTRY" build --load --tag pocketforge-sim:test fixture
rc=$?
set -e
[ "$rc" -eq 7 ]
grep -qxF 'buildx prune --builder pf-ci --all --force --keep-storage 8gb' \
    "$T/state/docker.calls"

run_cleanup_failure_case() {
    local label="$1" expected_rc="$2" expected_builder="$3" rc
    shift 3
    : > "$T/state/docker.calls"
    [ ! -e "$T/state/builder" ] || unlink "$T/state/builder"
    set +e
    env -i PATH="$T/bin:/usr/bin:/bin" PF_TEST_STATE="$T/state" \
        PF_CI_BUILDX_LOCK="$T/builder.lock" PF_CI_BUILDX_NAMESERVERS=10.0.0.53 \
        RUNNER_TEMP="$T" "$@" \
        "$ENTRY" build --load --tag pocketforge-sim:test fixture \
        > "$T/$label.out" 2>&1
    rc=$?
    set -e
    if [ "$rc" -ne "$expected_rc" ]; then
        printf 'FAIL: %s returned %s, expected %s\n' "$label" "$rc" "$expected_rc" >&2
        return 1
    fi
    grep -qxF 'buildx prune --builder pf-ci --all --force --keep-storage 8gb' \
        "$T/state/docker.calls"
    if [ "$expected_builder" = absent ]; then
        test ! -e "$T/state/builder"
    else
        test -e "$T/state/builder"
    fi
    case "$label" in
        cancelled|build-and-prune-failed|prune-failed|fallback-failed)
            grep -qxF 'buildx rm --force pf-ci' "$T/state/docker.calls"
            ;;
        remove-failed)
            grep -qxF 'buildx rm --keep-state pf-ci' "$T/state/docker.calls"
            grep -qxF 'buildx rm --force pf-ci' "$T/state/docker.calls"
            ;;
        create-failed)
            grep -qxF 'buildx rm --keep-state pf-ci' "$T/state/docker.calls"
            ;;
    esac
}

# Every path after named-builder creation starts must attempt both bounding
# operations. The original build/create/signal status wins over cleanup errors.
run_cleanup_failure_case cancelled 143 absent PF_TEST_BUILD_SIGNAL=TERM PF_TEST_PRUNE_FAIL=1
run_cleanup_failure_case create-failed 8 absent PF_TEST_CREATE_FAIL=1
run_cleanup_failure_case build-and-prune-failed 7 absent PF_TEST_BUILD_FAIL=1 PF_TEST_PRUNE_FAIL=1
run_cleanup_failure_case prune-failed 0 absent PF_TEST_PRUNE_FAIL=1
run_cleanup_failure_case remove-failed 0 absent PF_TEST_REMOVE_FAIL=1
run_cleanup_failure_case fallback-failed 11 present PF_TEST_PRUNE_FAIL=1 PF_TEST_FORCE_REMOVE_FAIL=1

: > "$T/state/docker.calls"
exec 8> "$T/busy.lock"
flock -n 8
if env -i PATH="$T/bin:/usr/bin:/bin" PF_TEST_STATE="$T/state" \
    PF_CI_BUILDX_LOCK="$T/busy.lock" PF_CI_BUILDX_NAMESERVERS=10.0.0.53 \
    RUNNER_TEMP="$T" "$ENTRY" build --load fixture > "$T/busy.out" 2>&1; then
    echo 'platform builder accepted an active producer lock' >&2
    exit 1
fi
flock -u 8
grep -q 'reason=builder_busy' "$T/busy.out"
test ! -s "$T/state/docker.calls"

# Transport-only apt cache (tsp-hqm1p.138; contract of pocketforge-automation
# scripts/pf-ci-buildx prepare_apt_cache, tsp-hqm1p.121). sim-suite builds sim's
# image through this entry point, and sim pins its apt sources to
# snapshot.debian.org, whose cold-object 504s fail the job. The entry point
# probes the NAS transport cache with the recipe's pinned indexes and hands it to
# the build as BuildKit's predefined http_proxy build arg only when the probe
# passes; otherwise it builds direct. Nothing else about the build changes.
cat > "$T/fake-proxy.py" <<'PY'
import http.server
import sys

mode, port_file, hits_file = sys.argv[1:4]
seen = set()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        with open(hits_file, "a") as hits:
            hits.write(self.path + "\n")
        first = self.path not in seen
        seen.add(self.path)
        # noindex is the half-dead cache seen live: InRelease is servable, every
        # cold Packages object times out (acng "504 Gateway Timeout"). flaky is
        # snapshot's cold-object behaviour: the first fetch of an object 504s while
        # the backend fills, later fetches succeed.
        ok = (
            mode == "ok"
            or (mode == "noindex" and self.path.endswith("/InRelease"))
            or (mode == "flaky" and not first)
        )
        body = b"index\n" if ok else b"No healthy backends"
        self.send_response(200 if ok else (503 if mode == "broken" else 504))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Server(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass  # curl drops its keep-alive connection between probes; not an error


server = Server(("127.0.0.1", 0), Handler)
with open(port_file, "w") as port:
    port.write(str(server.server_address[1]))
server.serve_forever()
PY
proxy_pids=
start_proxy() {
    local mode=$1
    : > "$T/state/$mode.hits"
    python3 "$T/fake-proxy.py" "$mode" "$T/state/$mode.port" "$T/state/$mode.hits" &
    proxy_pids="$proxy_pids $!"
    for _ in $(seq 100); do
        [ -s "$T/state/$mode.port" ] && return
        sleep 0.1
    done
    echo "fake $mode proxy did not start" >&2
    exit 1
}
stop_proxies() {
    local pid
    for pid in $proxy_pids; do
        kill "$pid" 2>/dev/null || true
    done
}
trap 'stop_proxies; cleanup_test' EXIT
for mode in ok broken noindex flaky; do start_proxy "$mode"; done
ok_url="http://127.0.0.1:$(cat "$T/state/ok.port")"
broken_url="http://127.0.0.1:$(cat "$T/state/broken.port")"
noindex_url="http://127.0.0.1:$(cat "$T/state/noindex.port")"
flaky_url="http://127.0.0.1:$(cat "$T/state/flaky.port")"
snap=http://snapshot.debian.org/archive/debian/20260901T000000Z
secsnap=http://snapshot.debian.org/archive/debian-security/20260901T000000Z

# sim's recipe shape: the pin is an ARG default, the sources are printf formats
# (three per line, repeated per base stage), and no SHELL or env -i wrapper sits
# between BuildKit's http_proxy and apt.
mkdir "$T/ctx"
cat > "$T/ctx/Dockerfile" <<'EOF'
FROM debian:bookworm AS toolchain
ARG SNAPSHOT_TIMESTAMP=20260901T000000Z
RUN set -eux; \
    printf 'deb http://snapshot.debian.org/archive/debian/%s/ bookworm main\ndeb http://snapshot.debian.org/archive/debian-security/%s/ bookworm-security main\ndeb http://snapshot.debian.org/archive/debian/%s/ bookworm-updates main\n' \
      "${SNAPSHOT_TIMESTAMP}" "${SNAPSHOT_TIMESTAMP}" "${SNAPSHOT_TIMESTAMP}" > /etc/apt/sources.list
RUN apt-get update
FROM debian:bookworm AS runtime
ARG SNAPSHOT_TIMESTAMP
RUN set -eux; \
    printf 'deb http://snapshot.debian.org/archive/debian/%s/ bookworm main\ndeb http://snapshot.debian.org/archive/debian-security/%s/ bookworm-security main\ndeb http://snapshot.debian.org/archive/debian/%s/ bookworm-updates main\n' \
      "${SNAPSHOT_TIMESTAMP}" "${SNAPSHOT_TIMESTAMP}" "${SNAPSHOT_TIMESTAMP}" > /etc/apt/sources.list
EOF
mkdir "$T/ctx-nosource"
printf 'FROM scratch\nRUN true\n' > "$T/ctx-nosource/Dockerfile"
# A literal pin, as automation's recipes write it, goes through the same probe.
printf 'FROM scratch\nRUN echo "deb http://snapshot.debian.org/archive/debian/20260901T000000Z bookworm main" > /etc/apt/sources.list\n' \
    > "$T/literal.Containerfile"

# sim-suite's call shape: context last, recipe found at <context>/Dockerfile.
run_build() {
    local url=$1
    shift
    : > "$T/state/docker.calls"
    (
        cd "$T/ctx"
        env -i PATH="$T/bin:/usr/bin:/bin" PF_TEST_STATE="$T/state" \
            PF_CI_BUILDX_LOCK="$T/builder.lock" PF_CI_BUILDX_NAMESERVERS=10.0.0.53 \
            RUNNER_TEMP="$T" PF_CI_APT_CACHE_URL="$url" \
            PF_CI_APT_CACHE_PROBE_RETRY_SLEEP=0 \
            ${RUN_BUILD_ENV:+"$RUN_BUILD_ENV"} \
            "$ENTRY" build "$@" 2>"$T/state/stderr"
    )
}
label='--label org.pocketforge.cache-owner=pf-build-ci'
sim_args=(--load --build-arg PLATFORM_REPO=https://example.test/platform.git -t pocketforge-sim:test .)
direct_call="buildx build --builder pf-ci $label --load --build-arg PLATFORM_REPO=https://example.test/platform.git -t pocketforge-sim:test ."
proxied_call() {
    printf 'buildx build --builder pf-ci %s --build-arg http_proxy=%s --load --build-arg PLATFORM_REPO=https://example.test/platform.git -t pocketforge-sim:test .' \
        "$label" "$1"
}

# Reachable: the pinned indexes of every source arrive through the cache, then
# the build carries the predefined http_proxy build arg and nothing else new.
: > "$T/state/ok.hits"
run_build "$ok_url" "${sim_args[@]}"
grep -qxF "$(proxied_call "$ok_url")" "$T/state/docker.calls"
for probed in \
    "$snap/dists/bookworm/InRelease" \
    "$snap/dists/bookworm/main/binary-amd64/Packages.xz" \
    "$secsnap/dists/bookworm-security/InRelease" \
    "$secsnap/dists/bookworm-security/main/binary-amd64/Packages.xz" \
    "$snap/dists/bookworm-updates/InRelease" \
    "$snap/dists/bookworm-updates/main/binary-amd64/Packages.xz"; do
    grep -qxF "$probed" "$T/state/ok.hits"
done
# Two base stages name the same sources; each object is fetched once.
[ "$(wc -l < "$T/state/ok.hits")" -eq 6 ]
grep -qxF "pf_ci_buildx=apt_cache state=used url=$ok_url" "$T/state/stderr"
# Transport only: the cache URL appears exactly once, as the predefined build
# arg (which stays out of image history and layer cache keys), never in the
# recipe, a label or a second build argument.
[ "$(grep -o "$ok_url" "$T/state/docker.calls" | wc -l)" -eq 1 ]
if grep -q "$ok_url" "$T/ctx/Dockerfile"; then
    echo 'the cache URL was written into the recipe' >&2
    exit 1
fi

# The recipe may be named: --file=, -f and --file all resolve it, and a build-arg
# pin override moves the probed objects with it.
for form in "--file=$T/ctx/Dockerfile" "-f $T/ctx/Dockerfile" "--file $T/ctx/Dockerfile"; do
    : > "$T/state/ok.hits"
    # shellcheck disable=SC2086  # the -f form is deliberately two words
    run_build "$ok_url" --load $form -t pocketforge-sim:test "$T/ctx-nosource"
    grep -qF -- "--build-arg http_proxy=$ok_url" "$T/state/docker.calls"
    grep -qxF "$snap/dists/bookworm/InRelease" "$T/state/ok.hits"
done
for pin in "--build-arg SNAPSHOT_TIMESTAMP=20260915T000000Z" "--build-arg=SNAPSHOT_TIMESTAMP=20260915T000000Z"; do
    : > "$T/state/ok.hits"
    # shellcheck disable=SC2086  # the pin forms are deliberately word-split
    run_build "$ok_url" --load $pin -t pocketforge-sim:test .
    grep -qxF "http://snapshot.debian.org/archive/debian/20260915T000000Z/dists/bookworm/InRelease" "$T/state/ok.hits"
    if grep -q '20260901T000000Z' "$T/state/ok.hits"; then
        echo 'the recipe default was probed despite a SNAPSHOT_TIMESTAMP build arg' >&2
        exit 1
    fi
done
: > "$T/state/ok.hits"
run_build "$ok_url" --load --file "$T/literal.Containerfile" -t pocketforge-sim:test "$T/ctx-nosource"
grep -qxF "$snap/dists/bookworm/main/binary-amd64/Packages.xz" "$T/state/ok.hits"
grep -qF -- "--build-arg http_proxy=$ok_url" "$T/state/docker.calls"

# Unreachable: a cache that answers but cannot serve the pinned index (acng up,
# router or upstream dead), or does not answer at all, must not break the build.
# It goes direct, no proxy argument, and the log names the state.
run_build "$broken_url" "${sim_args[@]}"
grep -qxF "$direct_call" "$T/state/docker.calls"
grep -qxF "pf_ci_buildx=apt_cache state=unreachable fallback=direct url=$broken_url attempts=3 object=debian/20260901T000000Z/dists/bookworm/InRelease" "$T/state/stderr"
run_build http://127.0.0.1:1 "${sim_args[@]}"
grep -qxF "$direct_call" "$T/state/docker.calls"
grep -qxF 'pf_ci_buildx=apt_cache state=unreachable fallback=direct url=http://127.0.0.1:1 attempts=3 object=debian/20260901T000000Z/dists/bookworm/InRelease' "$T/state/stderr"
if grep -q 'http_proxy' "$T/state/docker.calls"; then
    echo 'an unreachable cache still got a proxy argument' >&2
    exit 1
fi

# The state seen on the live cache tier: InRelease served, every cold Packages
# object 504. Probing InRelease alone would trust it and the build would burn its
# retries; the binary index probe sends it direct instead, naming the object.
run_build "$noindex_url" "${sim_args[@]}"
grep -qxF "$direct_call" "$T/state/docker.calls"
grep -qxF "pf_ci_buildx=apt_cache state=unreachable fallback=direct url=$noindex_url attempts=3 object=debian/20260901T000000Z/dists/bookworm/main/binary-amd64/Packages.xz" "$T/state/stderr"
grep -qxF "$snap/dists/bookworm/main/binary-amd64/Packages.xz" "$T/state/noindex.hits"

# snapshot.debian.org's cold object: the first fetch 504s while the backend
# fills, the next succeeds. One miss must not send a healthy cache direct.
run_build "$flaky_url" "${sim_args[@]}"
grep -qxF "$(proxied_call "$flaky_url")" "$T/state/docker.calls"
grep -qxF "pf_ci_buildx=apt_cache state=used url=$flaky_url" "$T/state/stderr"
[ "$(wc -l < "$T/state/flaky.hits")" -eq 12 ]

# A cache that passes the probe but cannot serve the build (a cold pool object,
# a dead router) must never turn a build that would pass direct into a failure:
# the wrapper rebuilds once without it, and the direct result is what is seen.
RUN_BUILD_ENV=PF_TEST_FAIL_PROXIED=3
run_build "$ok_url" "${sim_args[@]}"
unset RUN_BUILD_ENV
[ "$(grep -c '^buildx build ' "$T/state/docker.calls")" -eq 2 ]
grep -qxF "$(proxied_call "$ok_url")" "$T/state/docker.calls"
grep -qxF "$direct_call" "$T/state/docker.calls"
grep -qxF 'pf_ci_buildx=apt_cache state=build_failed rc=3 fallback=direct' "$T/state/stderr"
grep -qxF 'buildx prune --builder pf-ci --all --force --keep-storage 8gb' "$T/state/docker.calls"
rc=0
RUN_BUILD_ENV=PF_TEST_BUILD_FAIL=1
run_build "$ok_url" "${sim_args[@]}" || rc=$?
unset RUN_BUILD_ENV
[ "$rc" -eq 7 ]
[ "$(grep -c '^buildx build ' "$T/state/docker.calls")" -eq 2 ]
# No cache used: a failing build is not retried.
rc=0
RUN_BUILD_ENV=PF_TEST_BUILD_FAIL=1
run_build "$broken_url" "${sim_args[@]}" || rc=$?
unset RUN_BUILD_ENV
[ "$rc" -eq 7 ]
[ "$(grep -c '^buildx build ' "$T/state/docker.calls")" -eq 1 ]
# A build killed by a signal (a cancelled job) is not rebuilt either.
rc=0
RUN_BUILD_ENV=PF_TEST_FAIL_PROXIED=137
run_build "$ok_url" "${sim_args[@]}" || rc=$?
unset RUN_BUILD_ENV
[ "$rc" -eq 137 ]
[ "$(grep -c '^buildx build ' "$T/state/docker.calls")" -eq 1 ]

# The probed index follows the build platform; an unsupported one is not probed.
: > "$T/state/ok.hits"
run_build "$ok_url" --platform linux/arm64 "${sim_args[@]}"
grep -qxF "$secsnap/dists/bookworm-security/main/binary-arm64/Packages.xz" "$T/state/ok.hits"
if grep -q 'binary-amd64' "$T/state/ok.hits"; then
    echo 'arm64 build probed an amd64 index' >&2
    exit 1
fi
grep -qF -- "--build-arg http_proxy=$ok_url" "$T/state/docker.calls"
run_build "$ok_url" --platform=linux/riscv64 "${sim_args[@]}"
grep -qxF 'pf_ci_buildx=apt_cache state=off reason=unsupported_platform' "$T/state/stderr"
if grep -q 'http_proxy' "$T/state/docker.calls"; then
    echo 'an unsupported platform still got a proxy argument' >&2
    exit 1
fi

# Disabled, no recipe, or no pinned snapshot source: no proxy argument, no probe,
# and the log still says why.
hits_before=$(wc -l < "$T/state/ok.hits")
run_build "$ok_url" --load -t pocketforge-sim:test "$T/ctx-nosource"
grep -qxF 'pf_ci_buildx=apt_cache state=off reason=no_snapshot_source' "$T/state/stderr"
if grep -q 'http_proxy' "$T/state/docker.calls"; then
    echo 'a recipe with nothing to probe still got a proxy argument' >&2
    exit 1
fi
run_build "$ok_url" --load -t pocketforge-sim:test fixture
grep -qxF 'pf_ci_buildx=apt_cache state=off reason=no_recipe' "$T/state/stderr"
run_build '' "${sim_args[@]}"
grep -qxF "$direct_call" "$T/state/docker.calls"
grep -qxF 'pf_ci_buildx=apt_cache state=off reason=disabled' "$T/state/stderr"
[ "$(wc -l < "$T/state/ok.hits")" -eq "$hits_before" ]

rc=0
run_build 'http://127.0.0.1:1/x;touch-injected' "${sim_args[@]}" || rc=$?
[ "$rc" -eq 2 ]
grep -qxF 'pf_ci_buildx=refused reason=apt_cache_url_invalid' "$T/state/stderr"
[ ! -s "$T/state/docker.calls" ]

# The shipped default is the NAS cache tier; sim-suite sets nothing to reach it.
grep -qF 'PF_CI_APT_CACHE_URL-http://10.0.32.86:3142' "$ENTRY"

python3 - "$ROOT/buildkit/pf-ci-buildkitd.toml" <<'PY'
import sys, tomllib
policy = tomllib.load(open(sys.argv[1], "rb"))["worker"]["oci"]
assert policy == {"gc": True, "reservedSpace": "2GB", "maxUsedSpace": "8GB", "minFreeSpace": "64GB"}
PY

printf 'platform_pf_ci_buildx_test=PASS builder=pf-ci keep_storage=8gb\n'
