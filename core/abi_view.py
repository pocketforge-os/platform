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
  abi_view.py check [--baseline REV | --baseline-file PATH]
                                       # also enforce frozen-version transitions
"""
import sys, os, json, subprocess

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


class VersionPolicyError(ValueError):
    """A malformed snapshot or forbidden Platform ABI transition."""


def _family_index(view, label):
    families = view.get("families")
    if not isinstance(families, list):
        raise VersionPolicyError(f"{label} snapshot has no families list")
    indexed = {}
    for family in families:
        if not isinstance(family, dict) or not isinstance(family.get("id"), str) or not family["id"]:
            raise VersionPolicyError(f"{label} snapshot has a family with an invalid id")
        if family["id"] in indexed:
            raise VersionPolicyError(f"{label} snapshot has duplicate family id '{family['id']}'")
        indexed[family["id"]] = family
    return indexed


def _platform_version(family, label):
    value = family.get("platform_version")
    # bool is an int subclass, but is not a valid release counter.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise VersionPolicyError(f"{label} family '{family.get('id')}' has malformed platform_version {value!r}")
    text = str(value)
    if not text.isascii() or not text.isdigit() or int(text) < 1:
        raise VersionPolicyError(f"{label} family '{family.get('id')}' has invalid platform_version {value!r}; expected a positive integer")
    return int(text)


def frozen_set(family):
    """Complete resolved identities of the three frozen ABI substrate components."""
    def fields(component, names):
        value = family.get(component)
        if not isinstance(value, dict):
            raise VersionPolicyError(f"family '{family.get('id')}' has malformed {component} identity")
        return tuple(value.get(name) for name in names)
    return (
        fields("kernel", ("repo", "ref", "sha")),
        fields("gpu_km", ("repo", "ref", "sha")),
        fields("sdl", ("status", "repo", "backend", "sha")),
    )


def validate_version_transition(baseline, current):
    """Return every forbidden transition between two committed ABI snapshots.

    Lock state is global in schema v1. Per-family state is intentionally deferred until
    the schema has an authoritative place for it.
    """
    old_state = baseline.get("lock_state")
    new_state = current.get("lock_state")
    if old_state not in ("interim", "authoritative"):
        raise VersionPolicyError(f"baseline snapshot has unsupported lock_state {old_state!r}")
    if new_state not in ("interim", "authoritative"):
        raise VersionPolicyError(f"current snapshot has unsupported lock_state {new_state!r}")
    old_by_id = _family_index(baseline, "baseline")
    new_by_id = _family_index(current, "current")
    missing = sorted(set(old_by_id) - set(new_by_id))
    errors = [{"reason": "baseline_family_missing", "family": family_id}
              for family_id in missing]
    if old_state == "authoritative" and new_state == "interim":
        errors.append({"reason": "authoritative_lock_downgrade", "family": "*"})

    for family_id, new in sorted(new_by_id.items()):
        new_version = _platform_version(new, "current")
        old = old_by_id.get(family_id)
        if old is None:
            frozen_set(new)  # validate the first frozen identity too
            continue
        old_version = _platform_version(old, "baseline")
        old_set, new_set = frozen_set(old), frozen_set(new)
        if new_version < old_version:
            errors.append({"reason": "platform_version_decreased", "family": family_id,
                           "old_version": old_version, "new_version": new_version,
                           "old_set": old_set, "new_set": new_set})
            continue
        freeze_event = new_state == "authoritative" and (
            old_state == "interim" or old_set != new_set)
        if freeze_event and new_version <= old_version:
            errors.append({"reason": "frozen_set_moved_without_version_bump",
                           "family": family_id, "old_state": old_state,
                           "new_state": new_state, "old_version": old_version,
                           "new_version": new_version, "old_set": old_set,
                           "new_set": new_set})
    return errors


def _load_baseline(revision=None, path=None):
    try:
        if path:
            with open(path) as fh:
                return json.load(fh)
        result = subprocess.run(
            ["git", "-C", ROOT, "show", f"{revision}:abi/platform-abi.json"],
            check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return json.loads(result.stdout)
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        source = path or f"{revision}:abi/platform-abi.json"
        raise VersionPolicyError(f"cannot read baseline snapshot '{source}': {exc}") from exc


def _print_policy_errors(errors):
    sys.stderr.write("[pf abi] ERROR: frozen Platform ABI version policy failed\n")
    for error in errors:
        reason, family = error["reason"], error["family"]
        sys.stderr.write(f"reason={reason} family={family}\n")
        if "old_state" in error:
            sys.stderr.write(f"lock_state={error['old_state']} -> {error['new_state']}\n")
        if "old_set" in error:
            sys.stderr.write(f"frozen_set={json.dumps(error['old_set'])} -> {json.dumps(error['new_set'])}\n")
        if "old_version" in error:
            sys.stderr.write(f"platform_version={error['old_version']} -> {error['new_version']}\n")
        if reason == "baseline_family_missing":
            sys.stderr.write(f"next=restore or explicitly migrate baseline family '{family}'\n")
        elif reason == "authoritative_lock_downgrade":
            sys.stderr.write("next=keep lock_state authoritative; per-family lock state is deferred schema evolution\n")
        elif reason == "platform_version_decreased":
            sys.stderr.write(f"next=restore {family} platform_version >= {error['old_version']}\n")
        else:
            sys.stderr.write(f"next=increment {family} platform_version in abi/families.toml and run `pf abi generate`\n")


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
        baseline_revision = baseline_file = None
        args = argv[1:]
        if args:
            if len(args) != 2 or args[0] not in ("--baseline", "--baseline-file"):
                sys.stderr.write("check: use --baseline <git-object> or --baseline-file <path>\n"); return 2
            if args[0] == "--baseline":
                baseline_revision = args[1]
            else:
                baseline_file = args[1]
        if not os.path.isfile(SNAPSHOT):
            die(f"no committed snapshot at {os.path.relpath(SNAPSHOT, ROOT)} — run `pf abi generate`")
        live = derive_view()
        with open(SNAPSHOT) as fh:
            committed = json.load(fh)
        if committed != live:
            sys.stderr.write(
                "DRIFT: abi/platform-abi.json does NOT match the live platform.lock join.\n"
                "The substrate SHAs (or the family registry) moved without the view being re-frozen.\n"
                "Re-freeze with `pf abi generate` and BUMP the affected family's platform-version if\n"
                "the resolved {kernel,gpu,sdl} SHA-set changed (a new SHA-set IS a new Platform ABI).\n"
                "next=run `pf abi generate`, then satisfy the baseline version policy\n\n")
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
        if baseline_revision or baseline_file:
            try:
                baseline = _load_baseline(baseline_revision, baseline_file)
                errors = validate_version_transition(baseline, committed)
            except VersionPolicyError as exc:
                die(str(exc) + "\nnext=fetch/provide the baseline and rerun `pf abi check`")
            if errors:
                _print_policy_errors(errors)
                return 1
        print(f"ABI VIEW OK — {os.path.relpath(SNAPSHOT, ROOT)} matches the live "
              f"platform.lock join ({len(live['families'])} families, "
              f"lock_state={live['lock_state']})")
        return 0

    sys.stderr.write(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
