#!/usr/bin/env python3
"""core/pf_lock.py — `pf lock`: freeze every repo's ref tip into platform.lock.

platform.lock is THE reproducibility anchor (AOSP `repo manifest -r` / west /
vcstool --exact / Nix flake.lock model). `pf build` resolves a profile's `ref`
THROUGH this file to a SHA and builds the SHA, NEVER a branch tip (the Yocto
AUTOREV / floating-branch trap). This is the freezer that writes those SHAs.

Modes (what gets written):
  (default / --dry-run)   PREVIEW: resolve + print, write NOTHING (reviewable).
  --interim               write SHAs, keep seeded=false, set interim_seed=true.
                          DEV-ONLY, NON-AUTHORITATIVE — release builds refused.
                          Permitted NOW (owner decision 2026-07-01) to unblock
                          B4 (tsp-1dl.4) against real SHAs.
  --authoritative         write SHAs, seeded=true, interim_seed=false.
                          GATED: only valid AFTER A1 + the B2 (tsp-1dl.2)
                          hardware retest land (both move kernel SHAs). Requires
                          --i-know-b2-is-done to actually write.

Source of each SHA:
  --source remote     (default) `git ls-remote <url> <ref>` — pins the tip of the
                      DECLARED ref, independent of any local checkout state.
  --source checkouts  `git -C <checkouts>/<name> rev-parse HEAD` — pins whatever
                      is checked out locally (legacy preview behaviour).
  --checkouts DIR     base dir for --source checkouts (default: $HOME).

Usage:
  pf lock [--interim | --authoritative [--i-know-b2-is-done]]
          [--source remote|checkouts] [--checkouts DIR] [--dry-run]
"""
import sys, os, subprocess, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(ROOT, "platform.lock")

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        sys.stderr.write("FATAL: need Python 3.11+ (tomllib) or the 'tomli' package.\n")
        sys.exit(3)


def die(msg):
    sys.stderr.write(f"[pf lock] ERROR: {msg}\n"); sys.exit(1)


def log(msg):
    sys.stderr.write(f"[pf lock] {msg}\n")


def load_repos():
    with open(LOCK, "rb") as f:
        data = tomllib.load(f)
    return data.get("repos", [])


def resolve_remote(url, ref):
    out = subprocess.run(["git", "ls-remote", url, ref], capture_output=True, text=True)
    if out.returncode != 0:
        return None, (out.stderr.strip() or "git ls-remote failed")
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    if not lines:
        return None, f"ref '{ref}' not found"
    return lines[0].split()[0], None


def resolve_checkout(base, name):
    co = os.path.join(base, name)
    if not os.path.isdir(os.path.join(co, ".git")):
        return None, f"no checkout at {co}"
    out = subprocess.run(["git", "-C", co, "rev-parse", "HEAD"], capture_output=True, text=True)
    if out.returncode != 0:
        return None, (out.stderr.strip() or "git rev-parse failed")
    return out.stdout.strip(), None


NAME_RE    = re.compile(r'^\s*name\s*=\s*"(?P<name>[^"]+)"')
SHA_RE     = re.compile(r'^(?P<pre>\s*sha\s*=\s*)"[^"]*".*$')
SEEDED_RE  = re.compile(r'^(?P<pre>\s*seeded\s*=\s*).*$')
INTERIM_RE = re.compile(r'^\s*interim_seed\s*=\s*.*$')


def rewrite(shas, seeded, interim):
    """Line-oriented in-place rewrite so all comments/formatting survive: fill each
    repo block's `sha`, set top-level `seeded`, and upsert `interim_seed`."""
    with open(LOCK, "r") as f:
        lines = f.readlines()
    out, cur = [], None
    for line in lines:
        m = NAME_RE.match(line)
        if m:
            cur = m.group("name")
        sm = SHA_RE.match(line)
        if sm and cur in shas:
            out.append(f'{sm.group("pre")}"{shas[cur]}"\n')  # pin; drop SEED_IN placeholder
            continue
        se = SEEDED_RE.match(line)
        if se:
            out.append(f'{se.group("pre")}{"true" if seeded else "false"}\n')
            out.append(f'interim_seed     = {"true" if interim else "false"}\n')
            continue
        if INTERIM_RE.match(line):
            continue  # drop any prior interim_seed line (re-inserted right after seeded)
        out.append(line)
    with open(LOCK, "w") as f:
        f.writelines(out)


def main(argv):
    mode, source = "preview", "remote"
    checkouts = os.environ.get("HOME", "")
    ack_b2 = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--interim":            mode = "interim"
        elif a == "--authoritative":    mode = "authoritative"
        elif a == "--dry-run":          mode = "preview"
        elif a == "--i-know-b2-is-done": ack_b2 = True
        elif a == "--source":           i += 1; source = argv[i] if i < len(argv) else ""
        elif a == "--checkouts":        i += 1; checkouts = argv[i] if i < len(argv) else ""
        elif a in ("-h", "--help"):     sys.stdout.write(__doc__); return 0
        else:                           die(f"unknown arg: {a}")
        i += 1
    if source not in ("remote", "checkouts"):
        die("--source must be remote|checkouts")

    repos = load_repos()
    if not repos:
        die(f"no [[repos]] blocks in {LOCK}")

    log(f"resolving {len(repos)} repos (source={source}, target={LOCK})")
    resolved, missing = {}, []
    for r in repos:
        name, url, ref = r.get("name"), r.get("url", ""), r.get("ref", "")
        sha, err = resolve_remote(url, ref) if source == "remote" else resolve_checkout(checkouts, name)
        if sha is None:
            missing.append((name, err))
            sys.stderr.write(f"  {name:<20} {ref:<14} MISSING ({err})\n")
        else:
            resolved[name] = sha
            sys.stderr.write(f"  {name:<20} {ref:<14} {sha}\n")
    if missing:
        die("could not resolve: " + ", ".join(f"{n} ({e})" for n, e in missing)
            + " — fix the ref in platform.lock (or the checkout) and re-run.")

    if mode == "preview":
        log("PREVIEW only — nothing written. Re-run with --interim (dev, permitted now) "
            "or --authoritative --i-know-b2-is-done (only after the B2 hardware retest).")
        return 0
    if mode == "authoritative":
        if not ack_b2:
            die("--authoritative pins the RELEASE lock (seeded=true); it is only valid "
                "AFTER A1 + the B2 (tsp-1dl.2) hardware retest, which move the kernel SHAs. "
                "If that has landed, re-run with --i-know-b2-is-done.")
        rewrite(resolved, seeded=True, interim=False)
        log(f"wrote AUTHORITATIVE platform.lock (seeded=true) — {len(resolved)} repos pinned.")
        return 0
    rewrite(resolved, seeded=False, interim=True)
    log(f"wrote INTERIM platform.lock (seeded=false, interim_seed=true, DEV-ONLY) — "
        f"{len(resolved)} repos pinned. Release builds refused; re-seed authoritatively "
        f"after the B2 hardware retest (tsp-1dl.1.1 authoritative half).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
