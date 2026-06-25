# pocketforge-os/platform

The **PocketForge build platform**: a shared SoC-agnostic **core** + a thin declarative
**per-device profile** + a **per-SoC-family plugin**, over a manifest-pinned multi-repo
set. One entrypoint — `pf build` — produces, for **any** device, a deterministic,
fully-owned artifact (same SHA on either build host). Adding the Nth device is a
`devices/<id>/profile.toml`, **not** a new pile of hand-copied repos.

> Epic **tsp-1dl** (kickoff: `mission-control/.planning/infra/infra-019-build-platform.md`).
> Architecture: `mission-control/.planning/infra/infra-014`. This repo is B1 (`tsp-1dl.1`).

## The three tiers

```
devices/<id>/profile.toml   declarative DATA — what this device is (no logic)
families/<family>/          per-SoC-family PLUGIN — implements 4 hooks (the only code that
                            knows boot0/SPL/fastboot/...); sunxi + snapdragon(stub) today
core/                       SoC-AGNOSTIC logic — profile parse/merge/validate, the `pf build`
                            dispatcher, the blob-group resolver, the reproducibility harness.
                            Contains ZERO family vocabulary (ci/core-purity-check.sh enforces it).
platform.lock               THE reproducibility anchor: every repo pinned at an exact SHA.
                            Builds use the SHA, never a branch tip.
pf                          the orchestrator entrypoint (build / flash / lock / validate / ...)
```

The **seam** is four hooks the core calls and each family implements:
`build-kernel.sh`, `build-bootchain.sh`, `assemble-image.sh`, `flash.sh`
(see `docs/FAMILY-INTERFACE.md`). The core owns everything *between* the hooks; the
family owns everything *inside* them. That is the whole abstraction.

## Quickstart

```bash
./pf list                                  # device ids
./pf validate --all                        # validate every profile (schema + seam + lock)
./pf resolve a523                          # the merged (profile + family) profile as JSON
./pf build --device a523 --artifact os-image --target dev-modelmaker   # (M-1: dispatch-only, dry)
./pf flash --device a523                   # dispatch the family flash hook (dry by default)
./pf purity-check                          # assert core/ is SoC-agnostic
```

## Status — M-1 skeleton (tsp-1dl.1)

This is the **ungated B1 skeleton**: the registry + `core/` + `families/sunxi/` + the
`pf` dispatcher + the `platform.lock` *schema*. Deliberately NOT done here:

- **`platform.lock` is UNSEEDED** (every `sha = ""`). Real SHA seeding is `tsp-1dl.1.1`,
  gated on A1 (clean owned trees) + B2 (kernel re-home) — both move the SHAs.
- **Family hooks are dispatch placeholders** (dry by default). They map to today's
  legacy `image/` build and name the B2/B4 work; the real per-stage container build is
  B4 (`tsp-1dl.4`). The legacy build is device-specific and not cleanly parameterized —
  exactly what B4 retires.
- **Profiles point at TODAY's repos** (M-1 "describe the current build"); B2 collapses
  the sunxi kernel/gpu/bootchain repos to per-family repos (device = branch).
- **Regression gate** (`pf regression`, `docs/`): the harness + a committed baseline are
  captured here; enforcement (pf build reproduces the legacy artifact bit-for-bit) is B4.

See `docs/DECISIONS.md` for the architecture decisions + rejected alternatives, and the
infra-019 kickoff for the full B1..B10 plan.
