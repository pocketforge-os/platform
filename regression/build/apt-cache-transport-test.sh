#!/usr/bin/env bash
# Unit-test pf_apt_cache_buildargs (tsp-hqm1p.135): the transport-only route of every
# apt-running Dockerfile.pf stage through the apt cache.
#
# `pf build` used to hand the cache to the image build as `--build-arg PF_APT_PROXY=...`,
# which only the rootfs stage consumed; every other stage (wpa, sdl, cloud-init, gpu-um,
# steamlink-ffmpeg59, debuginfo, ...) ran apt-get straight against snapshot.debian.org and
# failed whenever it was down. BuildKit's PREDEFINED `http_proxy` build-arg reaches every
# RUN without an ARG line, is excluded from the layer cache key and from `docker history`,
# and is honoured by apt. So the cache is now ALSO handed over as `http_proxy`, and only
# when PF_APT_PROXY is set: unset stays direct and the argv stays byte-identical.
#
# Contract under test:
#   * unset/empty PF_APT_PROXY -> no build args at all (direct, argv unchanged);
#   * set -> exactly PF_APT_PROXY=<url> (kept for the Dockerfile stages that still read
#     it, e.g. the injected Gamescope dependency stage) and http_proxy=<url> (the
#     predefined arg); never a second proxy variable that apt or curl would honour for
#     https, and never any other line;
#   * the value is passed through verbatim (no rewriting);
#   * pf_os_image_dockerbuild splices that output into the buildx argv via --build-arg
#     and no longer builds its own bare PF_APT_PROXY pair.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/core/pf-build.sh"

# Extract the shipped function and drive it directly (same pattern as the other tests).
extract() { sed -n "/^$1()/,/^}/p" "$BUILD"; }
body="$(extract pf_apt_cache_buildargs)"
if [ -z "$body" ]; then
    echo 'FAIL: core/pf-build.sh has no pf_apt_cache_buildargs (apt stages other than rootfs cannot use the cache)' >&2
    exit 1
fi
eval "$body"

URL=http://10.0.32.86:3142

# --- 1. unset -> nothing ----------------------------------------------------------------
unset PF_APT_PROXY
test -z "$(pf_apt_cache_buildargs)"
echo 'ok 1 - unset PF_APT_PROXY adds no build args (direct)'

# --- 2. empty -> nothing ----------------------------------------------------------------
export PF_APT_PROXY=''
test -z "$(pf_apt_cache_buildargs)"
echo 'ok 2 - empty PF_APT_PROXY adds no build args (direct)'

# --- 3. set -> exactly the two args, verbatim -------------------------------------------
export PF_APT_PROXY="$URL"
got="$(pf_apt_cache_buildargs)"
want="$(printf 'PF_APT_PROXY=%s\nhttp_proxy=%s' "$URL" "$URL")"
if [ "$got" != "$want" ]; then
    printf 'FAIL: unexpected build args\n--- got\n%s\n--- want\n%s\n' "$got" "$want" >&2
    exit 1
fi
echo 'ok 3 - set PF_APT_PROXY yields PF_APT_PROXY and the predefined http_proxy, verbatim'

# --- 4. no https proxy, no uppercase variants, no persisted config ----------------------
if grep -Eq '^(https_proxy|HTTPS_PROXY|all_proxy|ALL_PROXY|ftp_proxy|FTP_PROXY|no_proxy|NO_PROXY|HTTP_PROXY)=' <<<"$got"; then
    echo 'FAIL: only http_proxy may route apt; https/all/ftp proxies would capture the https fetches' >&2
    exit 1
fi
echo 'ok 4 - the https fetches (rustup, crates, pip, ffmpeg source) stay direct'

# --- 5. the argv assembly consumes the helper -------------------------------------------
dockerbuild="$(extract pf_os_image_dockerbuild)"
grep -Fq 'pf_apt_cache_buildargs' <<<"$dockerbuild" \
    || { echo 'FAIL: pf_os_image_dockerbuild does not splice pf_apt_cache_buildargs into the buildx argv' >&2; exit 1; }
if grep -Eq 'cmd\+=\( --build-arg "PF_APT_PROXY=' <<<"$dockerbuild"; then
    echo 'FAIL: pf_os_image_dockerbuild still builds its own bare PF_APT_PROXY build-arg' >&2
    exit 1
fi
echo 'ok 5 - the buildx argv takes its apt cache args from pf_apt_cache_buildargs'

# --- 6. replaying the splice yields an argv with and without the cache ------------------
splice() {
    local -a cmd=( docker buildx build )
    local line
    while IFS= read -r line; do
        [ -z "$line" ] || cmd+=( --build-arg "$line" )
    done < <(pf_apt_cache_buildargs)
    printf '%s\n' "${cmd[*]}"
}
export PF_APT_PROXY="$URL"
test "$(splice)" = "docker buildx build --build-arg PF_APT_PROXY=$URL --build-arg http_proxy=$URL"
unset PF_APT_PROXY
test "$(splice)" = 'docker buildx build'
echo 'ok 6 - the argv is unchanged when the cache is off'

echo 'PASS: pf build hands the apt cache to every stage as http_proxy only when PF_APT_PROXY is set'
