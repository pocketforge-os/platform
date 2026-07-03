#!/usr/bin/env bash
# core/pf-build.sh — the SoC-AGNOSTIC `pf build` dispatcher.
#
# Reads a device profile, validates it, resolves the family, and produces the artifact.
# The core owns everything BETWEEN the family hooks (validate, resolve lock SHAs, fetch,
# rootfs, reproducibility-finalize, SHA emit); the family owns everything INSIDE the hooks.
# The core contains ZERO family vocabulary (ci/core-purity-check.sh enforces this).
#
#   pf build --device <id> --artifact {os-image|containers} --target {ci-dell|dev-modelmaker}
#            [--dry-run|--no-dry-run] [--stage-only] [--bead <id>] [--image-repo <path>]
#
# --stage-only materializes the pinned source contexts (git archive of each platform.lock
# SHA) and stops — the first half of a real build, and a standalone CI/debug step.
#
# B4.0 (tsp-1dl.4.1): the os-image path constructs a MULTISTAGE `docker build` of
# image/build/Dockerfile.pf from the platform.lock-pinned SHAs (never a branch tip), with
# bead-id-keyed output/cache/source dirs. Source repos are delivered as named build CONTEXTS
# (a `git archive` of each lock SHA — NEVER a clone in the build; docs/KERNEL-SOURCE-STRATEGY.md
# §3). The multistage docker build is now the SOLE os-image path; the legacy host-orchestrated
# `make build-image` build was retired (tsp-1dl.4.5, code removed tsp-7xe). The M-1 hook-dispatch
# seam is still reachable via PF_ENGINE=hooks as a dispatch demo. The per-stage builds
# (kernel/GPU/SDL/rootfs/assemble) land in tsp-1dl.4.2..4.5; --dry-run previews the exact command.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=core/lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

DEVICE="" ARTIFACT="os-image" TARGET="dev-modelmaker" BEAD="${PF_BEAD:-adhoc}"
PF_DRY_RUN="${PF_DRY_RUN:-1}"
PF_IMAGE_REPO="${PF_IMAGE_REPO:-$HOME/image}"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --device)     DEVICE="$2"; shift 2 ;;
        --artifact)   ARTIFACT="$2"; shift 2 ;;
        --target)     TARGET="$2"; shift 2 ;;
        --bead)       BEAD="$2"; shift 2 ;;
        --image-repo) PF_IMAGE_REPO="$2"; shift 2 ;;
        --dry-run)    PF_DRY_RUN=1; shift ;;
        --no-dry-run) PF_DRY_RUN=0; shift ;;
        --stage-only) PF_STAGE_ONLY=1; shift ;;
        -h|--help)    grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) pf_die "unknown arg: $1" ;;
    esac
done
[ -n "$DEVICE" ] || pf_die "--device <id> is required (see: pf list)"
case "$ARTIFACT" in os-image|containers) ;; *) pf_die "--artifact must be os-image|containers" ;; esac
case "$TARGET"   in ci-dell|dev-modelmaker) ;; *) pf_die "--target must be ci-dell|dev-modelmaker" ;; esac

pf_log "build device=$DEVICE artifact=$ARTIFACT target=$TARGET bead=$BEAD dry_run=$PF_DRY_RUN"
pf_validate "$DEVICE"
pf_load_env "$DEVICE"

# Bead-id-keyed dirs (infra-013 concurrency: two builds never collide).
PF_OUT_DIR="${PF_OUT_DIR:-/tmp/pf-build/$BEAD/$DEVICE}"
mkdir -p "$PF_OUT_DIR"
export PF_OUT_DIR PF_DRY_RUN PF_IMAGE_REPO PF_PLATFORM_DIR PF_BEAD="$BEAD"

FAM_DIR="$(pf_family_dir "$PF_FAMILY")"
[ -d "$FAM_DIR" ] || pf_die "family plugin missing: $FAM_DIR"

run_hook() {
    local hook="$1"; shift
    local path="$FAM_DIR/$hook"
    [ -f "$path" ] || pf_die "family '$PF_FAMILY' missing hook $hook"
    pf_log "hook ${PF_FAMILY}/$hook"
    bash "$path" "$@"
}

# pf_find_git_source <repo> <mirror_dir> — print a usable --git-dir for <repo>, else return 1.
# Search order: a bare mirror (mirror_dir/<repo>.git or $HOME/<repo>.git) then a checkout
# ($HOME/<repo>/.git). Bare-mirror-per-host is the transport of record (docs/KERNEL-SOURCE-
# STRATEGY.md §2); a checkout is the fallback for a dev box.
pf_find_git_source() {
    local repo="$1" mirror_dir="$2" c
    for c in "$mirror_dir/$repo.git" "$HOME/$repo.git" "$HOME/$repo/.git"; do
        [ -d "$c" ] && git --git-dir="$c" rev-parse --git-dir >/dev/null 2>&1 && { printf '%s\n' "$c"; return 0; }
    done
    return 1
}

# pf_commit_epoch <repo> <sha> <mirror_dir> — print the committer epoch of <sha> resolved from
# any local git source for <repo> (checkout OR bare mirror), else print nothing. Deterministic
# (a function of the pinned SHA), so it is a valid SOURCE_DATE_EPOCH; never falls back to now().
pf_commit_epoch() {
    local repo="$1" sha="$2" mirror_dir="$3" gitdir
    [ -n "$repo" ] && [ -n "$sha" ] || return 0
    gitdir="$(pf_find_git_source "$repo" "$mirror_dir")" || return 0
    git --git-dir="$gitdir" show -s --format=%ct "${sha}^{commit}" 2>/dev/null || true
}

# pf_stage_sources <src_dir> <buildargs-text>
# Materialize each source repo as a `git archive` of its platform.lock SHA under
# <src_dir>/<logical>/ (the named build contexts the Dockerfile COPYs from). NEVER a clone
# inside the build — the archive of a content-addressed SHA is byte-identical regardless of
# transport, and needs no live remote (docs/KERNEL-SOURCE-STRATEGY.md §3). The SHA is pinned
# by platform.lock; if it is missing from the local source we do a targeted fetch. Set
# PF_STAGE_ALLOW_MISSING=1 to warn+skip a repo with no local source (partial/dev staging)
# instead of failing.
pf_stage_sources() {
    local src_dir="$1" ba="$2"
    local mirror_dir="${PF_MIRROR_DIR:-$HOME/wt/.mirrors}"
    v() { sed -n "s/^$1=//p" <<< "$ba"; }
    # logical-context-dir | repo | sha  (order matches the --build-context args below)
    local -a specs=(
        "image|image|$(v PF_IMAGE_SHA)"
        "kernel|$(v PF_KERNEL_REPO)|$(v PF_KERNEL_SHA)"
        "gpu|$(v PF_GPU_REPO)|$(v PF_GPU_SHA)"
        "libsdl3-sunxifb|libsdl3-sunxifb|$(v PF_LIBSDL3_SHA)"
        "blobs|blobs|$(v PF_BLOBS_SHA)"
        "vendor-manifest|vendor-manifest|$(v PF_VENDOR_MANIFEST_SHA)"
        "uboot|$(v PF_UBOOT_REPO)|$(v PF_UBOOT_SHA)"
        "tfa|$(v PF_TFA_REPO)|$(v PF_TFA_SHA)"
    )
    local spec logical repo sha gitdir dest n
    for spec in "${specs[@]}"; do
        IFS='|' read -r logical repo sha <<< "$spec"
        # A device that does not use this source (e.g. no source bootchain) still gets an
        # EMPTY context dir: the --build-context args below are unconditional, and the
        # device-gated Dockerfile stages COPY from the empty context harmlessly.
        [ -n "$repo" ] && [ "$repo" != "none" ] || { pf_log "stage: skip $logical (no repo — empty context)"; rm -rf "$src_dir/$logical"; mkdir -p "$src_dir/$logical"; continue; }
        [ -n "$sha" ] || pf_die "stage: no platform.lock SHA for $repo ($logical) — run \`pf lock\`"
        if ! gitdir="$(pf_find_git_source "$repo" "$mirror_dir")"; then
            if [ "${PF_STAGE_ALLOW_MISSING:-0}" = 1 ]; then
                pf_log "stage: WARN no local git source for $repo — skipping ($logical) [PF_STAGE_ALLOW_MISSING=1]"; continue
            fi
            pf_die "stage: no local git source for $repo — provision a bare mirror at $mirror_dir/$repo.git (\`git clone --bare <url>\`) or a checkout at \$HOME/$repo"
        fi
        if ! git --git-dir="$gitdir" cat-file -e "${sha}^{commit}" 2>/dev/null; then
            pf_log "stage: $repo missing $sha in $gitdir — targeted fetch"
            git --git-dir="$gitdir" fetch -q origin "$sha" 2>/dev/null \
                || git --git-dir="$gitdir" fetch -q origin 2>/dev/null || true
            git --git-dir="$gitdir" cat-file -e "${sha}^{commit}" 2>/dev/null \
                || pf_die "stage: SHA $sha absent from $repo after fetch — is platform.lock stale for this repo?"
        fi
        dest="$src_dir/$logical"; rm -rf "$dest"; mkdir -p "$dest"
        git --git-dir="$gitdir" archive --format=tar "$sha" | tar -x -C "$dest"
        n="$(find "$dest" -type f | wc -l)"
        pf_log "stage: $logical <- $repo@${sha:0:12}  ($n files, src=$gitdir)"
    done
}

# pf_os_image_dockerbuild — construct the multistage os-image `docker build` (B4.0).
# Create-if-missing the docker-container buildx builder that grants the security.insecure
# entitlement (the rootfs + assemble stages run privileged debootstrap/image-assembly steps that
# need SYS_ADMIN/mount). Every build host (modelmaker, Dell CI) converges to the same named
# builder. See the tsp-buildkit-insecure-mmdebstrap memory.
#
# The builder ALSO needs the insecure-registry buildkitd config so it can pull the owned build
# container from the NAS registry (container.pin -> 10.0.32.86:5555, plain HTTP) — without it a
# pull fails with "server gave HTTP response to HTTPS client". The config lives at
# $PF_BUILDKITD_CONFIG (default ~/.pf-buildkit/buildkitd.toml); it is passed via --buildkitd-config
# when present. A builder created BEFORE a registry was added to that config holds a stale snapshot
# in its running buildkitd, so when the builder already exists we verify every insecure-registry
# host the config declares is actually live and recreate the builder if it is behind (self-heal for
# config drift; a no-op once in sync).
pf_ensure_insecure_builder() {
    local builder="$1"
    local cfg="${PF_BUILDKITD_CONFIG:-$HOME/.pf-buildkit/buildkitd.toml}"
    local -a create=( docker buildx create --name "$builder" --driver docker-container
        --driver-opt network=host
        --buildkitd-flags '--allow-insecure-entitlement security.insecure --allow-insecure-entitlement network.host' )
    [ -f "$cfg" ] && create+=( --buildkitd-config "$cfg" )
    create+=( --bootstrap )

    if docker buildx inspect "$builder" >/dev/null 2>&1; then
        # Builder exists — self-heal if its running buildkitd is missing an insecure registry
        # the config now declares (only when we can actually read the running config; never
        # destroy a builder we cannot verify).
        if [ -f "$cfg" ]; then
            local node="buildx_buildkit_${builder}0" running h stale=0
            running="$(docker exec "$node" cat /etc/buildkit/buildkitd.toml 2>/dev/null || true)"
            if [ -n "$running" ]; then
                for h in $(grep -oE '\[registry\."[^"]+"\]' "$cfg" | sed -E 's/.*"([^"]+)".*/\1/'); do
                    printf '%s\n' "$running" | grep -qF "\"$h\"" || stale=1
                done
                if [ "$stale" = 1 ]; then
                    pf_log "buildx builder '$builder' buildkitd config is stale (missing an insecure registry) — recreating"
                    docker buildx rm "$builder" >/dev/null 2>&1 || true
                    "${create[@]}" >/dev/null || pf_die "failed to recreate buildx builder '$builder'"
                fi
            fi
        fi
        return 0
    fi
    pf_log "creating docker-container buildx builder '$builder' (security.insecure${cfg:+; buildkitd config $cfg})"
    "${create[@]}" >/dev/null || pf_die "failed to create buildx builder '$builder'"
}

pf_os_image_dockerbuild() {
    # Lock-pinned build-arg surface (the ONE place that reads profile+lock).
    local ba; ba="$("$PF_PY" "$PF_PLATFORM_DIR/core/profile.py" buildargs "$DEVICE")" \
        || pf_die "profile.py buildargs failed for $DEVICE"
    local lock_state missing
    lock_state="$(printf '%s\n' "$ba" | sed -n 's/^PF_LOCK_STATE=//p')"
    missing="$(printf '%s\n' "$ba" | sed -n 's/^PF_LOCK_MISSING_SHAS=//p')"
    case "$lock_state" in
        unseeded) pf_die "platform.lock is UNSEEDED — seed it first (\`pf lock --interim\`; tsp-1dl.1.1)" ;;
        interim)  pf_log "platform.lock is INTERIM-seeded (dev-only) — OK for a dev build; a RELEASE build needs the authoritative seed (post-B2)" ;;
    esac
    [ -z "$missing" ] || pf_die "platform.lock missing SHAs for $DEVICE: $missing — re-seed (\`pf lock\`)"

    local cache_dir="/tmp/pf-build/$BEAD/cache" src_dir="/tmp/pf-build/$BEAD/src"

    # --stage-only: materialize the pinned source contexts and stop (CI/debug; also the
    # first half of a real build). Needs neither the Dockerfile nor the container digest.
    if [ "${PF_STAGE_ONLY:-0}" = 1 ]; then
        pf_log "stage-only: materializing source contexts for $DEVICE under $src_dir/"
        pf_stage_sources "$src_dir" "$ba"
        pf_log "stage-only: done ($src_dir/)"
        return 0
    fi

    local dockerfile="$PF_IMAGE_REPO/build/Dockerfile.pf"
    [ -f "$dockerfile" ] || pf_die "missing $dockerfile — B4.0 multistage Dockerfile (build it in the image worktree)"
    local pin_file="$PF_IMAGE_REPO/container.pin"
    local container
    if [ -n "${PF_CONTAINER_OVERRIDE:-}" ]; then
        # DEV escape hatch: the docker-container builder can only pull the owned build container
        # from a registry, and container.pin may point at a not-yet-registry-hosted digest. A dev
        # can point at a locally-reachable registry ref (e.g. localhost:5000/pocketforge/build@...).
        # CI/release always resolve the committed container.pin (no override).
        container="$PF_CONTAINER_OVERRIDE"
        pf_log "PF_CONTAINER_OVERRIDE set — using $container (dev; NOT the committed container.pin)"
    else
        [ -f "$pin_file" ] || pf_die "missing $pin_file (owned build-container digest)"
        container="$(grep -v '^[[:space:]]*#' "$pin_file" | grep -v '^[[:space:]]*$' | head -1 | tr -d '[:space:]')"
    fi
    local snap="20260601T000000Z"
    [ -f "$PF_IMAGE_REPO/snapshot-date.txt" ] && snap="$(tr -d '[:space:]' < "$PF_IMAGE_REPO/snapshot-date.txt")"

    # Reproducibility epochs — pinned commit times, resolved deterministically from the
    # pinned SHA (never wall-clock). The IMAGE epoch stamps rootfs/assemble; the KERNEL epoch
    # (tsp-1dl.4.2) stamps the kernel stage so the Image is byte-stable from the kernel SHA
    # alone (component reproducibility), independent of image-repo churn. Both resolve via
    # any local git source (checkout OR bare mirror) so a .git-less build host still works.
    local mirror_dir="${PF_MIRROR_DIR:-$HOME/wt/.mirrors}"
    local image_sha kernel_repo kernel_sha sde="" k_sde=""
    image_sha="$(printf '%s\n' "$ba" | sed -n 's/^PF_IMAGE_SHA=//p')"
    kernel_repo="$(printf '%s\n' "$ba" | sed -n 's/^PF_KERNEL_REPO=//p')"
    kernel_sha="$(printf '%s\n' "$ba" | sed -n 's/^PF_KERNEL_SHA=//p')"
    sde="$(pf_commit_epoch image "$image_sha" "$mirror_dir")"
    k_sde="$(pf_commit_epoch "$kernel_repo" "$kernel_sha" "$mirror_dir")"
    # The BOOTCHAIN epoch (tsp-jet.1) pins the bootchain stage to the u-boot commit time,
    # same component-reproducibility rationale as the kernel epoch. Empty for a device
    # with no source bootchain (the stage no-ops there).
    local uboot_repo uboot_sha bc_sde=""
    uboot_repo="$(printf '%s\n' "$ba" | sed -n 's/^PF_UBOOT_REPO=//p')"
    uboot_sha="$(printf '%s\n' "$ba" | sed -n 's/^PF_UBOOT_SHA=//p')"
    bc_sde="$(pf_commit_epoch "$uboot_repo" "$uboot_sha" "$mirror_dir")"

    # The rootfs stage does a privileged debootstrap (real chroot/mount) and the assemble stage
    # builds the disk image — both need SYS_ADMIN, which BuildKit grants ONLY under
    # `RUN --security=insecure` on a builder that allows the security.insecure entitlement. The
    # DEFAULT docker builder refuses it (no dockerd reconfig here), so we use a dedicated
    # docker-container buildx builder created with the entitlement. Driver choice does not change
    # output bytes. See the tsp-buildkit-insecure-mmdebstrap memory.
    local builder="${PF_BUILDX_BUILDER:-pf-insecure}"

    local -a cmd=( docker buildx build
        --builder "$builder"
        --allow security.insecure
        --file "$dockerfile"
        --target export
        --build-arg "PF_CONTAINER=$container"
        --build-arg "APT_SNAPSHOT_DATE=$snap" )
    [ -n "$sde" ]    && cmd+=( --build-arg "SOURCE_DATE_EPOCH=$sde" )
    [ -n "$k_sde" ]  && cmd+=( --build-arg "PF_KERNEL_SOURCE_DATE_EPOCH=$k_sde" )
    [ -n "$bc_sde" ] && cmd+=( --build-arg "PF_BOOTCHAIN_SOURCE_DATE_EPOCH=$bc_sde" )
    # Optional transparent apt cache proxy (e.g. the NAS apt-cacher-ng at http://10.0.32.86:3142).
    # Fetch transport only — apt verifies every .deb vs the signed snapshot index, so it never
    # changes output bytes (R1 / G-reproducible safe). Opt-in via the PF_APT_PROXY env; a CI host
    # points it at its own cache (or leaves it unset for direct snapshot).
    [ -n "${PF_APT_PROXY:-}" ] && cmd+=( --build-arg "PF_APT_PROXY=$PF_APT_PROXY" )
    # Hermetic blob-fetch (B3 / tsp-1dl.3): PF_FETCH_MODE=fallback selects the git-clone-blobs path
    # (merge-1 safety); default hermetic (the FETCH stage's ARG default). PF_CAR_SHA256 is the
    # vendor-originals.car rot-detection gate (hermetic only) — from platform.lock [car].sha256
    # (agent-docqueue re-pins at merge) or the env for a dev verify. Both opt-in; unset = FETCH defaults.
    [ -n "${PF_FETCH_MODE:-}" ] && cmd+=( --build-arg "PF_FETCH_MODE=$PF_FETCH_MODE" )
    [ -n "${PF_CAR_SHA256:-}" ] && cmd+=( --build-arg "PF_CAR_SHA256=$PF_CAR_SHA256" )
    # WiFi credentials (bd tsp-8ba, interim file source for the tsp-zbg#5 design): the
    # gitignored wifi.txt never enters the lock-ref build contexts, so it reaches the
    # assemble stage only as a BuildKit secret (never an image layer). PF_WIFI_SHA
    # cache-busts the consuming RUN — secret content is excluded from BuildKit's cache
    # key, so a rotated PSK would otherwise reuse the stale cached layer. Opt-in: unset
    # = today's behavior (image ships WiFi-unconfigured).
    if [ -n "${PF_WIFI_SECRET_FILE:-}" ]; then
        [ -r "$PF_WIFI_SECRET_FILE" ] || pf_die "PF_WIFI_SECRET_FILE set but not readable: $PF_WIFI_SECRET_FILE"
        cmd+=( --secret "id=wifi,src=$PF_WIFI_SECRET_FILE"
               --build-arg "PF_WIFI_SHA=$(sha256sum "$PF_WIFI_SECRET_FILE" | cut -d' ' -f1)" )
    fi
    local line
    while IFS= read -r line; do
        case "$line" in PF_LOCK_STATE=*|PF_LOCK_MISSING_SHAS=*|"") continue ;; esac
        cmd+=( --build-arg "$line" )
    done <<< "$ba"
    # Source repos as named build contexts (git archive of the lock SHA; staged by pf_stage_sources).
    cmd+=( --build-context "image-src=$src_dir/image"
           --build-context "kernel-src=$src_dir/kernel"
           --build-context "gpu-src=$src_dir/gpu"
           --build-context "sdl-src=$src_dir/libsdl3-sunxifb"
           --build-context "blobs-src=$src_dir/blobs"
           --build-context "vendor-manifest-src=$src_dir/vendor-manifest"
           --build-context "uboot-src=$src_dir/uboot"
           --build-context "tfa-src=$src_dir/tfa"
           --build-context "blobs-car=${PF_CAR_DIR:-$HOME/.pf-car}" )
    # Local BuildKit cache export (tsp-1dl.4.7): emit ONLY for ci-dell. On a persistent dev host
    # docker's own layer cache already persists between builds for free, so an explicit
    # type=local,mode=max export buys nothing — and mode=max serializes+compresses EVERY intermediate
    # layer of every stage (the ~2.2GB kernel tree), a slow disk-heavy write that has filled
    # modelmaker's / and left BuildKit wedged. CI (fresh workspaces) genuinely benefits from
    # cross-run cache priming, so it keeps the export.
    if [ "$TARGET" = ci-dell ]; then
        cmd+=( --cache-from "type=local,src=$cache_dir"
               --cache-to   "type=local,dest=$cache_dir,mode=max" )
    fi
    cmd+=( --output     "type=local,dest=$PF_OUT_DIR"
           --metadata-file "$PF_OUT_DIR/build-metadata.json"
           "$PF_IMAGE_REPO/build" )

    if [ "${PF_DRY_RUN:-1}" = 1 ]; then
        pf_log "DRY-RUN os-image multistage build (device=$DEVICE bead=$BEAD lock=$lock_state). Command:"
        printf '%q ' "${cmd[@]}"; printf '\n'
        pf_log "source contexts (git archive of the lock SHA) stage under $src_dir/ — materialized by tsp-1dl.4.2+."
        return 0
    fi
    pf_stage_sources "$src_dir" "$ba"
    [ "$TARGET" = ci-dell ] && mkdir -p "$cache_dir"
    pf_ensure_insecure_builder "$builder"
    pf_log "EXEC os-image multistage build"
    "${cmd[@]}"
}

if [ "$ARTIFACT" = "os-image" ]; then
    if [ "${PF_ENGINE:-docker}" = "hooks" ]; then
        # M-1 seam demo: dispatch the family hooks (DRY). Kept for the seam test only —
        # the real os-image build is the multistage docker path below (PF_ENGINE=docker).
        pf_log "engine=hooks (M-1 seam demo): core fetch blob groups [$PF_BLOB_GROUPS] (B3 fetch-by-CID — stub)"
        pf_log "engine=hooks: core build_rootfs (mmdebstrap — seam demo)"
        run_hook build-kernel.sh
        run_hook build-bootchain.sh
        run_hook assemble-image.sh
        pf_log "engine=hooks: reproducibility_finalize + emit (B4/B6)"
    else
        pf_os_image_dockerbuild
    fi
else
    pf_log "core: container-image path (mmdebstrap->tar->OCI) is B5 (tsp-1dl.5) — not in B1/B4"
fi
pf_log "build dispatch complete (device=$DEVICE artifact=$ARTIFACT)."
