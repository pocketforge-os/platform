#!/usr/bin/env python3
"""core/abi_view.py — the NAMED per-SoC-family Platform ABI view (E8 / tsp-ziac.1).

A DERIVED, versioned VIEW over the flat `platform.lock`. `platform.lock` pins repos at
exact SHAs; `devices/<id>/profile.toml` maps a device to its kernel/GPU repos; `abi/families.toml`
adds the stable NAMED family id + SDL-backend mapping + platform-version + provenance posture.
This module JOINS the three and resolves each `[[family]]` to its exact
`{kernel-sunxi-* SHA, gpu-km-* SHA, SDL3-backend SHA}` set — the ABI contract an app pins via
`app.toml` `[runtime].family` + `platform-version`.

The view CANNOT diverge from the lock because it is DERIVED from it (single source of truth =
device profiles + platform.lock + families.toml). `generate` writes the frozen snapshot
`abi/platform-abi.json`; `check` re-derives it live and diffs against the committed snapshot —
so a substrate SHA that moved without the view being re-frozen (and its `platform-version`
bumped) FAILS the gate. That is the anti-drift guarantee this bead's acceptance requires.

Usage:
  abi_view.py list                     # canonical family ids (one per line)
  abi_view.py resolve <family-id>      # the live-resolved SHA-set for one family (JSON)
  abi_view.py view                     # the whole live-resolved view (JSON)
  abi_view.py generate                 # (re)write abi/platform-abi.json from live sources
  abi_view.py check                    # re-derive + diff vs the committed snapshot; exit 1 on drift
"""
import sys, os, json

try:
    import tomllib  # py3.11+
    def _load(p):
        with open(p, "rb") as f:
            return tomllib.load(f)
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
        def _load(p):
            with open(p, "rb") as f:
                return tomllib.load(f)
    except ModuleNotFoundError:
        sys.stderr.write("FATAL: need Python 3.11+ (tomllib) or the 'tomli' package.\n")
        sys.exit(3)

# Reuse the ONE profile/lock resolver — do not re-parse the lock a second way.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile as profile_mod  # noqa: E402  (core/profile.py)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILIES = os.path.join(ROOT, "abi", "families.toml")
SNAPSHOT = os.path.join(ROOT, "abi", "platform-abi.json")


def die(msg):
    sys.stderr.write(f"[pf abi] ERROR: {msg}\n"); sys.exit(1)


def load_families():
    if not os.path.isfile(FAMILIES):
        die(f"family registry missing: {FAMILIES}")
    data = _load(FAMILIES)
    fams = data.get("family", [])
    if not fams:
        die("family registry has no [[family]] entries")
    return data.get("platform_abi_schema", 1), fams


def _repo_pin(lock, name):
    """(ref, sha) for a repo name in platform.lock, or (None, None) if absent."""
    r = lock["repos"].get(name or "", {}) or {}
    return r.get("ref"), (r.get("sha") or "")


def resolve_family(fam, lock):
    """Resolve one [[family]] entry to its exact {kernel, gpu_km, sdl} SHA-set.

    kernel/gpu repo NAMES come from the device profile (single source of truth); their SHAs
    from platform.lock; the SDL mapping + family metadata from the registry. A registry that
    names a repo the lock does not carry is a hard error (a view that references a phantom
    repo would be a silent drift — refuse it)."""
    dev_id = fam["device"]
    merged, _family = profile_mod.resolve(dev_id)
    krepo = (merged.get("kernel", {}) or {}).get("repo")
    grepo = (merged.get("gpu", {}) or {}).get("repo")
    kref, ksha = _repo_pin(lock, krepo)
    gref, gsha = _repo_pin(lock, grepo)

    for label, repo, sha in (("kernel", krepo, ksha), ("gpu_km", grepo, gsha)):
        if not repo:
            die(f"family '{fam['id']}': device '{dev_id}' profile has no {label} repo")
        if repo not in lock["repos"]:
            die(f"family '{fam['id']}': {label} repo '{repo}' is not in platform.lock")

    # SDL is per-family (registry), NOT per-device — a133 owns libsdl3-sunxifb; a523 does not
    # ship an owned sunxifb SDL yet (Mali; see families.toml). Represent the gap honestly.
    sdl_repo = fam.get("sdl_repo") or ""
    if sdl_repo:
        if sdl_repo not in lock["repos"]:
            die(f"family '{fam['id']}': sdl repo '{sdl_repo}' is not in platform.lock")
        _sref, ssha = _repo_pin(lock, sdl_repo)
        sdl = {"status": "owned", "repo": sdl_repo, "backend": fam.get("sdl_backend", ""), "sha": ssha}
    else:
        sdl = {"status": "not-owned", "repo": None, "backend": fam.get("sdl_backend", ""),
               "sha": None, "note": f"no owned SDL fork yet ({fam.get('provenance_ref', '')})"}

    return {
        "id": fam["id"],
        "alias": fam.get("alias", []),
        "device": dev_id,
        "gpu_ip": fam.get("gpu_ip", ""),
        "platform_version": str(fam.get("platform_version", "")),
        "reproducible": bool(fam.get("reproducible", False)),
        "provenance_ref": fam.get("provenance_ref", ""),
        "kernel": {"repo": krepo, "ref": kref, "sha": ksha},
        "gpu_km": {"repo": grepo, "ref": gref, "sha": gsha},
        "sdl": sdl,
    }


def derive_view():
    """The whole live-resolved view (deterministic ordering)."""
    schema, fams = load_families()
    lock = profile_mod.load_lock()
    lock_state = "authoritative" if lock["seeded"] else ("interim" if lock.get("interim") else "unseeded")
    families = [resolve_family(f, lock) for f in fams]
    families.sort(key=lambda x: x["id"])
    return {
        "platform_abi_schema": schema,
        "lock_state": lock_state,   # interim SHAs are DEV-ONLY (not a frozen release) — surface it
        "families": families,
    }


def find_family(view_or_fams, family_id):
    """Match a family id against the canonical id OR any alias."""
    fams = view_or_fams["families"] if isinstance(view_or_fams, dict) else view_or_fams
    fid = family_id.strip()
    for f in fams:
        if f["id"] == fid or fid in (f.get("alias") or []):
            return f
    return None


def _dump(obj):
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def main(argv):
    if not argv:
        sys.stderr.write(__doc__); return 2
    cmd = argv[0]

    if cmd == "list":
        _schema, fams = load_families()
        for f in sorted(fams, key=lambda x: x["id"]):
            print(f["id"])
        return 0

    if cmd == "view":
        sys.stdout.write(_dump(derive_view()))
        return 0

    if cmd == "resolve":
        if len(argv) < 2:
            sys.stderr.write("resolve: give a family id\n"); return 2
        view = derive_view()
        f = find_family(view, argv[1])
        if not f:
            die(f"unknown family '{argv[1]}' (known: {', '.join(x['id'] for x in view['families'])})")
        sys.stdout.write(_dump(f))
        return 0

    if cmd == "generate":
        view = derive_view()
        with open(SNAPSHOT, "w") as fh:
            fh.write(_dump(view))
        sys.stderr.write(f"[pf abi] wrote {os.path.relpath(SNAPSHOT, ROOT)} "
                         f"({len(view['families'])} families, lock_state={view['lock_state']})\n")
        return 0

    if cmd == "check":
        if not os.path.isfile(SNAPSHOT):
            die(f"no committed snapshot at {os.path.relpath(SNAPSHOT, ROOT)} — run `pf abi generate`")
        live = derive_view()
        with open(SNAPSHOT) as fh:
            committed = json.load(fh)
        if committed == live:
            print(f"ABI VIEW OK — {os.path.relpath(SNAPSHOT, ROOT)} matches the live "
                  f"platform.lock join ({len(live['families'])} families, "
                  f"lock_state={live['lock_state']})")
            return 0
        sys.stderr.write(
            "DRIFT: abi/platform-abi.json does NOT match the live platform.lock join.\n"
            "The substrate SHAs (or the family registry) moved without the view being re-frozen.\n"
            "Re-freeze with `pf abi generate` and BUMP the affected family's platform-version if\n"
            "the resolved {kernel,gpu,sdl} SHA-set changed (a new SHA-set IS a new Platform ABI).\n\n")
        # Show the first differing family for a fast diagnosis.
        cby = {f["id"]: f for f in committed.get("families", [])}
        for lf in live["families"]:
            if cby.get(lf["id"]) != lf:
                sys.stderr.write(f"first drift in family '{lf['id']}':\n")
                sys.stderr.write(f"  committed: {json.dumps(cby.get(lf['id']), sort_keys=True)}\n")
                sys.stderr.write(f"  live:      {json.dumps(lf, sort_keys=True)}\n")
                break
        if live.get("lock_state") != committed.get("lock_state"):
            sys.stderr.write(f"lock_state changed: {committed.get('lock_state')} -> {live.get('lock_state')}\n")
        return 1

    sys.stderr.write(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
