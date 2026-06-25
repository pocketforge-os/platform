# Regression baselines (the R1 same-host legacy-vs-new gate)

`pf regression baseline --device <id> <component-files...>` records the SHA-256 of the
**legacy** build's component artifacts (kernel `Image`, GPU `.ko`(s), rootfs tar, the
whole `.img`) into `regression/<id>.baseline.sha256`. `pf regression check` re-hashes a
fresh `pf build` and asserts bit-identical.

**Why a SEPARATE gate from B6's cross-host SHA:** two hosts can agree on a *wrong*
artifact. This axis proves the NEW `pf build` reproduces the PRE-replan `make build-image`
output on the *same* host, before anything underneath the dispatcher changes.

**Status (B1 / tsp-1dl.1):** the harness exists; baselines are **not yet captured** (that
needs a real legacy build, done as B4 / `tsp-1dl.4` retires the legacy path). To seed one:

```bash
# build the legacy artifact for a523, then:
./pf regression baseline --device a523 \
    /path/to/Image /path/to/mali_kbase.ko /path/to/rootfs.tar /path/to/pocketforge-tsp-s.img
git add regression/a523.baseline.sha256 && commit
# later, after pf build's internals change (B4):
./pf regression check --device a523  <same component paths from the NEW build>
```
