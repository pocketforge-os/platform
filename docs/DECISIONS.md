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

3. **Device variants are BRANCHES, not repos — but the kernel is SPLIT per (family,
   kernel-line), GPU stays per-IP.** (Owner decision, B2 / `tsp-1dl.2`, 2026-06-25.)
   - **Kernel:** two repos — `kernel-sunxi-4.9` (branch `device/a133`, A133/4.9.191) and
     `kernel-sunxi-5.15` (branch `device/a523`, A523/5.15.154) — NOT one `kernel-sunxi`.
     The 4.9 and 5.15 bases share ~zero objects, never merge, and want independent
     branch-protection/CI rulesets; the named-fallback split (infra-015 §B) gives cleaner
     isolation than one repo carrying two unrelated bases. `device=branch` still holds
     *within* a line. `kernel-sunxi-5.15` also carries a passive `upstream` branch (the
     AvaotaSBC import base) for `git am`-onto-GregKH-stable-tag fork-tracking; 4.9 is
     upstream-EOL (no `upstream` branch; its root commit is the vendor-import provenance pin).
   - **GPU:** stays PER-IP — `gpu-km-tsp` (PowerVR/A133) + `gpu-km-tsp-a523` (Mali-G57/A523)
     share zero code, so a `gpu-sunxi` collapse buys nothing. (infra-019 hardened decision;
     supersedes infra-014 §1's per-family GPU sketch.)
   - **Bootchain:** consolidation into a `bootchain-sunxi` repo is DROPPED (decision, 2026-07-01) —
     `u-boot-tsp-a523` + `tfa-tsp-a523` stay SEPARATE (U-Boot & TF-A are unrelated projects; only
     the A523 owns a bootchain, so a merge buys nothing). The profile `[bootchain]` references each
     repo directly; A133 boots a vendor blob group. Bootchain ownership → infra-025.

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
  per device keep the family build hook shared. NOTE: the B2 GATING check resolved (owner,
  2026-06-25) to the per-(family, kernel-line) SPLIT — `kernel-sunxi-4.9` / `kernel-sunxi-5.15`,
  device=branch *within* each line — NOT one `kernel-sunxi` over two unrelated bases. See
  decision 3. So "device=branch" stands; "one repo per family for the kernel" did not.
