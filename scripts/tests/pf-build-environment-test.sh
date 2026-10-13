#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d "${RUNNER_TEMP:-/tmp}/pf-build-environment-test.XXXXXX")
trap 'find "$tmp" -mindepth 1 -delete; rmdir "$tmp"' EXIT

TRACEPARENT=00-0123456789abcdef0123456789abcdef-0123456789abcdef-01 \
TRACESTATE=pf-red=1 \
OTEL_SERVICE_NAME=pf-red \
OTEL_EXPORTER_OTLP_HEADERS=secret-red \
GITHUB_RUN_ID=1234 \
RUNNER_TRACKING_ID=runner-red \
CI=true \
BUILDKIT_PROGRESS=rawjson \
BUILDX_METADATA_PROVENANCE=max \
DOCKER_HOST=unix:///run/pf-test-docker.sock \
    "$root/core/lib/pf-build-env" sh -c 'env | LC_ALL=C sort >"$1"' sh "$tmp/environment"

grep -qxF 'DOCKER_HOST=unix:///run/pf-test-docker.sock' "$tmp/environment"
if grep -Eq '^(TRACEPARENT|TRACESTATE|OTEL_|GITHUB_|RUNNER_|CI=|BUILDKIT_|BUILDX_)' \
    "$tmp/environment"; then
    echo 'FAIL: CI or tracing environment crossed the pf build boundary' >&2
    cat "$tmp/environment" >&2
    exit 1
fi

grep -Fq 'core/lib/pf-build-env' "$root/core/pf-build.sh"
echo 'pf-build-environment-test=PASS'
