# Architecture decisions + rejected alternatives

Source: `mission-control/.planning/infra/infra-014` (the design research). This file is
the in-repo record so a fresh clone has the rationale. Decisions are **decisive, not a
menu** — the rejected options are recorded with reasons so we don't relitigate them.

## Decisions

1. **Shared-core + per-device PROFILE + per-SoC-FAMILY plugin, over a manifest-pinned
   multi-repo set.** Every mature multi-board project converges here: Yocto
   (OE-core + `meta-<bsp>` + `machine.conf`), Buildroot (`BR2_EXTERNAL` + `board/` +
   `defconfig`), postmarketOS (core + `deviceinfo` + `linux-<device>`), Armbian
   (core + `families/<f>.conf` + `boards/<b>.conf`), AOSP (platform + `device/` +
   `repo` manifest), NixOS (nixpkgs + `nixos-hardware` + `flake.lock`).

2. **`platform.lock` is THE reproducibility anchor** (AOSP `repo manifest -r` / west /
   vcstool `--exact` / Nix `flake.lock`). Every repo pinned at an exact SHA; the build
   uses the SHA, **never** a branch tip (the Yocto AUTOREV/floating-branch trap). A
   profile's `ref` is for humans + `pf lock`; the byte-deterministic input is the SHA.
   This is what makes "same SHA on Dell vs modelmaker" achievable and makes the
   stale-shared-tree clobber class (tsp-bcx.19) structurally impossible.

3. **One kernel/GPU/bootchain repo per SoC FAMILY; device variants are BRANCHES, not
   repos.** Collapses `kernel-tsp` + `kernel-tsp-a523` → `kernel-sunxi` (branches
   `device/a133`, `device/a523`); same for `gpu-sunxi`, `bootchain-sunxi`. Matches
   Armbian (kernel branch keyed by axis) + AOSP (one tree, many products). The
   upstream-pointing mirror is NOT an owned repo — it is a passive `upstream` branch /
   reference mirror. (Done structurally in B2 / `tsp-1dl.2`.)

4. **Blobs are keyed by GROUP, named in the profile; never a hard-coded CID.** The
   profile lists `[blobs] groups`, the `vendor-manifest` maps group → {path, SHA-256,
   CID}, `platform.lock` pins the manifest SHA. `blobs/` reorganizes by `family/device/`.
   The multistage `fetch` stage pulls only a device's groups' CIDs. (B3 / `tsp-1dl.3`.)

5. **The `[bootchain]` table expresses EITHER a source repo OR a blob group** — because
   the divergence is already in the tree: A523 boots owned U-Boot+TF-A (source); A133
   boots a vendor boot0/`boot_package.fex` set (blob, no mainline U-Boot for sun50iw10).
   This duality makes the A133-vs-A523 split declarative instead of two diverging board
   scripts.

6. **The core contains ZERO family vocabulary**, enforced by `ci/core-purity-check.sh`.
   The core only ever sees `family`, `kernel.repo/ref`, `blobs.groups`, `container.*` —
   all family-neutral. Family vocabulary (boot0, SPL, BL31, genimage, FEL / fastboot,
   XBL, EDL, ...) lives only in `families/<family>/`. This is how postmarketOS keeps its
   core device-agnostic and how the Snapdragon abstraction proof (B8) works.

7. **The build CONTAINER is owned substrate** (committed `image/build/Dockerfile`, CI-built,
   digest-pinned). No apt/pip into a running container; no host/native toolchain. (B4/B7.)

## Rejected alternatives (do not relitigate)

- **Full monorepo (kernels included).** Kernels are 200–320 MB history + 1.3–1.6 GB tree
  *each*; every clone/worktree would carry all families' kernels; branch-protection
  per-component is impossible (one repo = one ruleset, but `image`/`kernel`/`blobs` need
  different gates and `blobs` is private); worktree-per-bead becomes prohibitive. The one
  win (single ref) is delivered better by `platform.lock` over a multi-repo set.
- **Pure polyrepo-per-device-component (status quo).** It *is* the sprawl. Each device
  adds N repos; provenance drifts (one repo pointed at upstream `AvaotaSBC/linux`); branch
  names diverge; no single reproducible pin.
- **Git submodules to pin the set.** Detached-HEAD edits become gc-prunable dangling
  commits; submodule support across linked worktrees is incomplete (breaks the worktree-set
  model); the gitlink floats. A `.lock` manifest gives the same SHA-pinning without nesting
  gitlinks or burdening worktrees.
- **Git subtrees.** Copying a 1.3 GB kernel into a parent bloats every clone and makes
  upstream-tracking awkward. Suits small vendored libs, not kernels.
- **A `repo`/`west` workspace as the *only* unit (no `platform/` core repo).** We still
  want a first-class, branch-protected `platform/` repo for the profiles + family plugins
  + orchestrator. The manifest is one file *inside* it, not a replacement.
- **Per-device kernel repos (not branches).** That is the current duplication; branches
  per device on one family repo keep the family build hook shared. (Fallback to
  per-(family, kernel-line) repos — e.g. `kernel-sunxi-4.9`/`-5.15` — if branch management
  hurts; named, medium-confidence; the single-vs-split check is GATING in B2.)
