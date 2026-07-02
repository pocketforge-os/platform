# Kernel source strategy (transport, build-input, reproducibility, fork-tracking)

B2 / `tsp-1dl.2`. Design source: `mission-control/.planning/infra/infra-015` (kernel-repo
large-fleet management) + the owner's 2026-06-25 SPLIT decision. This is the in-repo record
so a fresh clone has the rationale without the (gitignored) planning docs.

## 1. Repo topology (owner decision, 2026-06-25)

Kernel is **SPLIT per (family, kernel-line)**, device = branch *within* a line:

| repo | branch | device | base | upstream tracking |
|---|---|---|---|---|
| `kernel-sunxi-4.9`  | `device/a133` | A133 / sun50iw10 | 4.9.191 (CrealityTech import, squashed root) | none — 4.9 is upstream-EOL; root commit is the vendor-import provenance pin; we own all backports |
| `kernel-sunxi-5.15` | `device/a523` | A523 / sun55iw3  | 5.15.154 (AvaotaSBC import) | `upstream` branch = the AvaotaSBC base; `git am` the owned series onto each new GregKH 5.15.x tag |

Why split, not one `kernel-sunxi`: the 4.9 and 5.15 bases share ~zero objects, never merge,
and want independent branch-protection / CI rulesets. The single-repo win is only
CI/ruleset consolidation; the split (infra-015 §B named fallback) gives cleaner isolation
of two never-merging bases. GPU stays **per-IP** (`gpu-km-tsp` PowerVR / `gpu-km-tsp-a523`
Mali — share no code). Bootchain target is one `bootchain-sunxi` (deferred; see DECISIONS §3).

The owned delta is tiny on each line (measured 2026-06-25): a133 = 17 commits over a
squashed import root; a523 = 12 owned commits over a real AvaotaSBC merge-base
(`a464bc4fe`). Cite as a dated command, not a frozen number:
`git rev-list <import-base>..device/<id>`.

## 2. Source transport: bare-mirror + worktrees (NOT `--reference`)

One fully-hydrated **bare mirror per repo per build host**; one `git worktree` per bead off it.

- Layout: `/var/lib/pf-mirror/<repo>.git` (bare `--mirror`), refreshed out-of-band
  (`git remote update` on a timer) — never on the critical build path.
- `pf-wt` (pocketforge-automation) adds the worktree off the mirror; it shares the mirror's
  object store (verified: the pack is shared, the private worktree dir is KB-scale), so a
  per-bead kernel worktree costs the working tree only — zero history duplication.
- **Do NOT use `git clone --reference`.** Worktrees already share `.git/objects`, so
  `--reference` solves a non-problem and adds a corruption class (`objects/info/alternates`
  dangles if the mirror is gc'd/pruned/moved; `repack` without `--local` silently un-shares;
  submodules inherit the hazard). Keep `--reference` only as the escape hatch for a host that
  cannot host a mirror, and `--dissociate` immediately (it then becomes a full clone).
- This SUPERSEDES infra-014 §5(b) (which made `--reference` primary). See infra-015 §A.

## 3. Build input: a pinned source artifact, not a live clone

The multistage `docker build` consumes a content-addressed `git archive` of the
**`platform.lock` SHA**, COPYied into the build stage — NOT `git clone` inside the build.

- git is content-addressed: a commit SHA cryptographically pins every reachable byte, so
  however the objects arrived, the checkout is byte-identical. Object provenance never
  affects output bytes — so clone strategy (§2) is a pure dev/CI convenience, orthogonal to
  reproducibility (Canonical buildd / Yocto `DL_DIR`+`SRCREV` lesson, infra-015 §D).
- Air-gap safety is the deciding property: a `git archive` of a local mirror has the complete
  verified object set — nothing to fetch — so the cross-host bit-for-bit compare runs with no
  live remote. This is why partial/shallow clone is rejected for the build input.
- `platform.lock` pins exact SHAs, never branch tips (Yocto AUTOREV trap). A profile's
  `ref = "device/a523"` is for humans + `pf lock`; the build uses the `.lock` SHA.

## 4. Reproducibility / vermagic guards (LOAD-BEARING)

We build modules with `CONFIG_MODVERSIONS=n`, so **vermagic is the ONLY `.ko` load gate**.
An archive-build version string that drifts from a clone build = a **silent** GPU-KM load
failure (`pvrsrvkm`/`mali_kbase` refuses to load), not merely a repro blemish. The build
hard-asserts these (WARN in the M-1 skeleton; **tsp-1dl.4.2** flipped them to hard FAIL in
`families/sunxi/build-kernel.sh` and re-asserts them inline in `image/build/Dockerfile.pf`'s
`kernel` stage — keep the two in lockstep):

1. **A stamped empty `.scmversion`** — this is the *definitive* transport-independence anchor.
   `scripts/setlocalversion` reads `.scmversion` first and, if present, uses ONLY its content
   and skips the scm probe entirely — so the version string is identical regardless of
   `CONFIG_LOCALVERSION_AUTO`, whether `.git` is present, or whether the tree is a clone or an
   archive. The `kernel` stage writes `printf '' > .scmversion` before configuring; the build
   HARD-FAILS if it is missing. (`.scmversion` derived from the lock SHA is an alternative, but
   empty keeps the release string exactly the defconfig's.)
2. `CONFIG_LOCALVERSION_AUTO=n` — **recommended, not required.** With (1) in force, AUTO is
   moot; a WARN (not a FAIL) fires if a defconfig leaves it at the Kconfig default `y`. Pinning
   `=n` in the defconfig is cleaner belt-and-suspenders. VERIFIED tsp-1dl.4.2: with `.scmversion`
   stamped, `make kernelrelease` == `4.9.191` (a133) / `5.15.154` (a523) across archive, clone,
   and even a naive clone with no `.scmversion` — these owned repos carry no reachable tags and
   the checkout is clean, so no `+`/`-g<sha>` suffix arises in practice. a133's defconfig pins
   `=n`; a523's leaves it default-`y` (a minor B2 cleanliness item, not a repro bug given (1)).
3. The **GPU KM built against the same-tree `Module.symvers`** (same archive, same build).
4. **No git submodules** (archive omits them → divergence); **no `.git`** in the build tree
   (the input must be a `git archive`, not a clone).
5. Pinned `KBUILD_BUILD_TIMESTAMP`, `KBUILD_BUILD_USER`, `KBUILD_BUILD_HOST`, and
   `SOURCE_DATE_EPOCH` (already proven bit-for-bit; `kernel-substrate-ownership.md` §3.2). The
   kernel `SOURCE_DATE_EPOCH` is pinned to the KERNEL commit time (resolved from the lock SHA by
   `core/pf-build.sh`), giving the Image component reproducibility independent of image-repo churn.

The kernel repro bar (component artifacts: `Image`, the GPU `.ko`, DTBs) is aligned with the
image repro bar (B6). NOTE: vermagic (the load gate) is transport-independent as above; full
Image *byte* equality additionally requires build-path normalization (the archive builds at
`/work/kernel`, a dev clone elsewhere) — that whole-image byte-repro item is owned by B6.

## 5. Fork-tracking cadence (A523 only; A133/4.9 is EOL)

The owned delta rides on a recoverable real upstream base, so the cadence is:

1. **Recover the base:** `kernel-sunxi-5.15`'s `upstream` branch = the AvaotaSBC import
   (`a464bc4fe`). (The old slim overlay line had a SQUASHED root with no merge-base and is
   NOT a rebase base — that is why the canonical owned line is the full `src/linux-5.15`
   history, which DOES share a merge-base with upstream.)
2. **Carry the owned delta as a portable series:** `git format-patch upstream..device/a523`
   (the 12 owned commits incl. the tsp-vuo.8 DSI C-code + tsp-vuo.7 DTS).
3. **Reparent onto each new stable tag:** check out the new GregKH 5.15.x tag, `git am` the
   series, **RETEST after each reparent** (kernel.org maintainers' explicit warning) — this
   is a build-and-boot + GPU-`.ko`-load HARDWARE gate, owner-OK required.
4. Merge model (instead of rebase) is the post-GA option if the delta grows or external
   consumers appear; neither is true now. Patchlevel: source base 5.15.154 vs a running
   device kernel #82 5.15.147 — a LABEL distinction, do not blanket-replace.

This cadence is the round-2 RESUME-banner "STOP BEFORE" line: groundwork (repos, transport,
guards, profile rewire) is non-destructive and device-free; the `git am`-onto-tag retest is
the hardware gate handed back to the owner.
