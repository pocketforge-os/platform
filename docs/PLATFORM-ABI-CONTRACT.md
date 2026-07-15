# Named per-SoC-family Platform ABI contract (E8 / `tsp-ziac.1`)

> The **family axis** of the substrate. `platform.lock` pins repos at exact SHAs; this contract
> gives apps a **stable, named, versioned** handle onto a coherent `{kernel, GPU, SDL}` SHA-set
> per SoC family — the thing an app pins in `app.toml` `[runtime].family` + `platform-version`.
> It is a **derived view over `platform.lock`**, not a second source of truth.

## 1. Why per-family (not per-device)

The two starter devices are **divergent SoCs, not variants** — different kernel line, different
GPU IP, different SDL backend ⇒ a **different binary build**. So the *binary ABI target* is
**family-level**, while the *capability descriptor* stays **device-level**
(`devices/<id>/capabilities.toml`). One app source → **one build per family** it supports; the
capability facade hides the within-family device delta. (E2 `runtime/docs/RUNTIME-SDK-SPLIT.md`
§2, R-D.)

## 2. The families (`abi/families.toml`)

| family id | alias (E2 draft) | device | kernel | GPU | SDL backend | reproducible |
|---|---|---|---|---|---|---|
| `pocketforge/a133-powervr` | `pocketforge/sun50i-a133` | a133 | `kernel-sunxi-4.9` | `gpu-km-tsp` (PowerVR) | `libsdl3-sunxifb` (fbdev) — **owned, pinned** | **yes** (`tsp-1dl.4.5`, `tsp-cv7.6.1`) |
| `pocketforge/a523-mali` | `pocketforge/sun55i-a523` | a523 | `kernel-sunxi-5.15` | `gpu-km-tsp-a523` (Mali) | `kmsdrm` target — **NOT yet an owned fork** | **no** (`tsp-jet`, `tsp-iby`) |

**Naming (E8 reconciliation).** The canonical ids are **GPU-IP-bearing**. E2's
`RUNTIME-SDK-SPLIT.md` §2 first drafted SoC-only ids and explicitly said *"When E8 is filed,
confirm it adopts this schema rather than inventing its own."* E8 adopts the **schema** (the
`family`/`abi` vocabulary) verbatim and reconciles the **ids** to the GPU-IP form — the
SDL-backend split (PowerVR fbdev vs Mali kmsdrm) is the ABI-relevant divergence, so naming the
GPU IP is the honest key. The SoC-only ids remain **accepted aliases** (an app that pinned the
E2 draft name still resolves).

## 3. The derived view (`abi/platform-abi.json`, `core/abi_view.py`)

`core/abi_view.py` JOINs three sources — the family registry (`abi/families.toml`), the device
profile's kernel/GPU repo names (`devices/<id>/profile.toml`, via `core/profile.py`), and the
SHAs (`platform.lock`) — and resolves each family to its exact `{kernel, gpu_km, sdl}`
`{repo, ref, sha}` set. `abi/platform-abi.json` is the **committed frozen snapshot** of that
join.

```sh
pf abi list                       # canonical family ids
pf abi resolve pocketforge/a523-mali   # one family's resolved SHA-set (JSON; aliases resolve too)
pf abi view                       # the whole live-resolved view
pf abi generate                   # (re)freeze abi/platform-abi.json from the live sources
pf abi check                      # re-derive + diff vs the snapshot; exit 1 on drift
```

**Anti-drift guarantee.** The view **cannot silently diverge** from the lock because it is
*derived* from it — a family that named a repo the lock does not carry is a hard error, not a
stale row. `pf abi check` is the gate: it fails if the substrate SHAs (or the registry) moved
without the snapshot being re-frozen. A moved `{kernel,gpu,sdl}` SHA-set **is a new Platform
ABI**, so re-freezing (`pf abi generate`) must be paired with a **`platform-version` bump** for
the affected family. Proven end-to-end by `regression/abi/drift-test.sh`.

**Enforced in CI (required, not documentary).** `pf abi check` runs on every PR via
[`.github/workflows/abi-drift.yml`](../.github/workflows/abi-drift.yml) (job `pf-abi-drift`) and
is wired as a **required status check** on the default branch. A `platform.lock` bump that skips
`pf abi generate` therefore **cannot merge** — the gate goes RED until the view is re-frozen.
This closes the enforcement hole that let `platform#42` drift the a133 view (`tsp-ziac.7`): the
guarantee above is now mechanized, not just documented.

**Lock state is surfaced.** The view carries `lock_state` (`interim` / `authoritative` /
`unseeded`) straight from `platform.lock`. Today it is **`interim`** — the SHAs are dev-tips, not
a frozen release seed (`tsp-1dl.1.1`). An `interim`-pinned ABI is **DEV-ONLY**; a released app
pins an `authoritative` platform-version. Never advertise an interim view as a frozen release.

## 4. Freeze / deprecation policy (per family)

`platform-version` is the frozen-release counter **per family** (independent across families — a
kernel bump on a523 does not touch a133's version). The contract is **semver-of-the-substrate**,
layered on top of E2's `abi` contract version (the `libpocketforge`/PFW1 version in
`STABILITY.md`, currently `1`):

- **`abi` (the API/wire contract, E2-owned):** the frozen C-ABI + PFW1 wire. Changes by E2's
  `STABILITY.md` rules (additive = minor, no basename change; breaking = soname/`WIRE_VERSION`
  bump). An app pins `abi = "1"` and runs on **any** platform-version of its family that offers
  abi 1 — the "survives the runtime fork" property.
- **`platform-version` (the SHA-set freeze, E8-owned, this doc):**
  - **A new frozen SHA-set ⇒ a new `platform-version`.** Bump the family's `platform_version` in
    `abi/families.toml` and re-run `pf abi generate` in the SAME change that moves the lock
    (`pf abi check` enforces it). Both versions may be offered concurrently.
  - **Additive within a version:** none — a platform-version is an exact SHA-set, immutable once
    frozen (authoritative). Any substrate change is a new version.
  - **Deprecation:** a superseded `platform-version` is retired by announcing the replacement +
    the earliest release that may drop it, keeping it resolvable for the current major, and
    dropping it only at the next `abi` major. (Mirrors `STABILITY.md` §3 deprecation discipline
    for the ABI, applied to the substrate freeze.)
  - **A new family** (a third SoC) is a new `[[family]]` entry + a device profile — **zero core
    change** (the family axis composes exactly like the device axis; `ci/core-purity-check.sh`
    keeps `core/` family-agnostic).

## 5. Provenance caveat — stated per family, not papered over

Per [`.claude/rules/provenance.md`](../../mission-control/.claude/rules/provenance.md) (own the
source, don't ship blackboxes) and the honest refinement of the epic's conservative blanket
caveat:

- **`pocketforge/a133-powervr` — SHA-pinned AND reproducible-from-clean.** The a133 image builds
  hermetically from committed refs via `pf build` (`tsp-1dl.4.5` closed; cross-host bit-identical
  `tsp-cv7.6.1` closed). Its `{kernel, gpu_km, sdl}` set is fully owned + pinned.
- **`pocketforge/a523-mali` — SHA-pinned, NOT yet reproducible.** Kernel + GPU-KM are pinned in
  the lock, but the a523 image build is not yet hermetic (`tsp-jet`, open) and blob→IPFS
  distribution is pending (`tsp-iby`, open). Its **SDL backend is not yet an owned fork** — a523
  ships no `libsdl3-sunxifb` today (that lib links the PowerVR UM ⇒ a133-only; the Mali/kmsdrm
  SDL is future work). The view records this as `sdl.status = "not-owned"`, not a phantom SHA.
- **No bit-for-bit *app* claim.** This contract freezes the *interface* and pins the *substrate*;
  it does not claim a reproducible app build (that is `.3`'s packaging path).

## 6. Relationship to the app descriptor + the two validators

An app pins the family in the canonical `app.toml` `[runtime]` table (schema:
`abi/app.schema.json`; full reconciliation:
[`infra-107.1`](../../mission-control/.planning/infra/infra-107.1-platform-abi-and-app-descriptor.md)).
Validation is split by **what each consumer can see** (one descriptor, two validators):

- **`core/appmanifest.py` (this repo, static, package-time)** owns the checks that need the lock:
  **unknown family**, **out-of-lock `platform-version`**, **unsupported `abi`**, plus `use=[]`
  token well-formedness. `pf app-validate <app.toml>`.
- **`runtime/crates/pf-broker/src/manifest.rs` (E2, cooperative, on-device, launch-time)** owns
  the authoritative capability semantics it alone can see: the `KNOWN_CAPS` universe + the
  **descriptor-backed dangling** check + the **family-MATCH** against the running Platform.

Neither re-implements the other's domain (unknown-family/out-of-lock are impossible on-device;
dangling-use is impossible off-device without the descriptor + cap universe). Rationale recorded
in `tsp-ziac.1`.
