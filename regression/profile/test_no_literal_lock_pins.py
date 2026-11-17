"""tsp-hqm1p.182.339 guard: no test or doc carries a literal copy of a current lock pin.

platform.lock is the one source of truth for pinned refs. A kernel pin advance must
edit platform.lock only (and `pf-pin` in mission-control scripts/g16 edits nothing
else), so every regression test and doc must read the pinned SHA from the lock or
refer to it by name. Before this guard a kernel advance edited seven files and
platform#493 went CI red on tests that hard-coded the previous SHA.

GUARDED_REPOS is the set of [[repos]] whose pins `pf-pin` may move. Each pin of a
guarded repo, and every [profile_pins] value equal to one, is forbidden as a literal
(the full 40-hex SHA, or a 12+ hex prefix) in any tracked file under regression/ and
docs/ and in any top-level *.md. Short (8-hex) prefixes in history prose stay legal:
they name a past advance, not the current pin. GUARDED_REPOS now names every
platform.lock repo except `image` (tsp-hqm1p.182.348); the literals the non-kernel repos
already carry are recorded in LITERAL_DEBT, which only shrinks.
"""
import pathlib
import re
import subprocess
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCK = ROOT / "platform.lock"
GUARDED_REPOS = frozenset(
    {
        "kernel-sunxi-4.9",
        "kernel-sunxi-5.15",
        "kernel-sunxi-6.x",
        "kernel-sunxi-7.x",
        "pf-cursor-theme",
        "gamescope",
        "gpu-km-tsp",
        "gpu-um-tsp",
        "gpu-km-tsp-a523",
        "u-boot-tsp-a523",
        "tfa-tsp-a523",
        "u-boot-tsp-a133",
        "tfa-tsp-a133",
        "blobs",
        "vendor-manifest",
        "libsdl3-sunxifb",
        "wpa-supplicant-tsp",
        "cloud-init-tsp",
        "runtime",
        "launcher",
        "recovery",
        "sim",
        "pf-hwprobe",
        "poolsuite",
    }
)
# Literal copies that predate widening the guard past the kernels (tsp-hqm1p.182.348): path -> repos whose current pin it
# still copies. pf-pin refuses `hardcoded_site` for these until each file reads platform.lock; this table may only SHRINK
# (test_debt_is_exact fails on a stale entry and test_no_..._guarded_pin on a new copy). `image` is never guarded here:
# its pin stays owner/gpu-16 gated and pf-pin refuses it outright.
LITERAL_DEBT = {
    "docs/A133-OPEN-7X-OWNED-SPL.md": ["gpu-um-tsp", "launcher", "runtime", "tfa-tsp-a133", "u-boot-tsp-a133"],
    "regression/build/cloud-init-staging-test.sh": ["cloud-init-tsp"],
    "regression/build/cursor-theme-staging-test.sh": ["pf-cursor-theme"],
    "regression/build/gamescope-series-witness.json": ["gamescope"],
    "regression/build/gamescope-staging-test.sh": ["gamescope"],
    "regression/lock_mirrors/fixtures/current/Dockerfile.pf": ["gpu-um-tsp", "launcher", "recovery", "runtime"],
    "regression/lock_mirrors/fixtures/current/build-rootfs.sh": ["recovery"],
    "regression/lock_mirrors/test_lock_mirrors.py": ["gamescope", "gpu-um-tsp", "launcher", "libsdl3-sunxifb", "runtime"],
    "regression/profile/test_full_open7_bootchain.py": ["blobs", "gpu-um-tsp", "launcher", "libsdl3-sunxifb", "recovery", "runtime", "tfa-tsp-a133", "u-boot-tsp-a133", "vendor-manifest"],
    "regression/profile/test_open7_noradio_profile.py": ["u-boot-tsp-a133"],
    "regression/profile/test_open7_spl_trace_profile.py": ["u-boot-tsp-a133"],
    "regression/profile/test_profile.py": ["blobs", "gpu-um-tsp", "launcher", "libsdl3-sunxifb", "poolsuite", "recovery", "vendor-manifest"],
}
SHA40 = re.compile(r"\A[0-9a-f]{40}\Z")
HEX_RUN = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{12,40}(?![0-9a-fA-F])")


def guarded_pins(lock: dict) -> dict[str, str]:
    """Map each guarded current pin SHA to the lock site(s) that own it."""
    pins: dict[str, list[str]] = {}
    for repo in lock.get("repos", []):
        sha = repo.get("sha", "")
        if repo.get("name") in GUARDED_REPOS and SHA40.match(sha):
            pins.setdefault(sha, []).append(f"repos.{repo['name']}.sha")
    for device, entries in lock.get("profile_pins", {}).items():
        for key, value in entries.items():
            if isinstance(value, str) and value in pins:
                pins[value].append(f"profile_pins.{device}.{key}")
    return {sha: ", ".join(sites) for sha, sites in pins.items()}


def scanned_files(root: pathlib.Path) -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", "regression", "docs", "*.md"],
        check=True,
        capture_output=True,
    ).stdout
    return [root / p for p in out.decode().split("\0") if p and (root / p).is_file()]


def owners(sites: str) -> set[str]:
    return set(re.findall(r"repos\.(.+?)\.sha", sites))


def literal_hits(pins: dict[str, str], files: list[pathlib.Path], root: pathlib.Path, debt=None) -> list[str]:
    """`debt` (path -> repos) hides recorded copies; None reports every one."""
    hits = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in HEX_RUN.finditer(line):
                run = match.group(0)
                for sha, sites in pins.items():
                    if sha.startswith(run):
                        rel = path.relative_to(root).as_posix()
                        if debt is not None and owners(sites) <= set(debt.get(rel, ())):
                            continue
                        hits.append(f"{rel}:{lineno}: {run} is the current {sites}")
    return hits


class NoLiteralLockPins(unittest.TestCase):
    def test_guard_has_pins_to_check(self):
        pins = guarded_pins(tomllib.loads(LOCK.read_text()))
        self.assertIn("repos.kernel-sunxi-7.x.sha", " ".join(pins.values()))

    def test_no_test_or_doc_carries_a_current_guarded_pin(self):
        pins = guarded_pins(tomllib.loads(LOCK.read_text()))
        hits = literal_hits(pins, scanned_files(ROOT), ROOT, LITERAL_DEBT)
        self.assertEqual(
            hits,
            [],
            "read the pin from platform.lock (profile.load_lock()) or name the lock "
            "entry instead of copying its SHA:\n" + "\n".join(hits),
        )

    def test_debt_is_exact(self):
        pins = guarded_pins(tomllib.loads(LOCK.read_text()))
        seen: dict[str, set[str]] = {}
        for hit in literal_hits(pins, scanned_files(ROOT), ROOT):
            path, _, rest = hit.partition(":")
            seen.setdefault(path, set()).update(owners(rest))
        for path, repos in LITERAL_DEBT.items():
            self.assertTrue(set(repos) <= seen.get(path, set()), f"stale LITERAL_DEBT entry {path} {repos}: delete it")

    def test_every_non_image_lock_repo_is_guarded(self):
        names = {r["name"] for r in tomllib.loads(LOCK.read_text()).get("repos", [])}
        self.assertEqual(GUARDED_REPOS, frozenset(names - {"image"}))

    def test_debt_hides_only_recorded_copies(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        pins = {sha: "repos.runtime.sha"}
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "old.py").write_text(f'X = "{sha}"\n')
            (root / "new.py").write_text(f'X = "{sha}"\n')
            files = sorted(root.iterdir())
            hits = literal_hits(pins, files, root, {"old.py": ["runtime"]})
        self.assertEqual([h.split(":")[0] for h in hits], ["new.py"])

    def test_detector_catches_full_and_prefix_literals(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        lock = {
            "repos": [{"name": "kernel-sunxi-7.x", "sha": sha},
                      {"name": "image", "sha": "f" * 40}],
            "profile_pins": {"dev-x": {"kernel": sha}},
        }
        pins = guarded_pins(lock)
        self.assertEqual(pins, {sha: "repos.kernel-sunxi-7.x.sha, profile_pins.dev-x.kernel"})
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            cases = {
                "full.py": f'X = "{sha}"\n',
                "prefix12.md": f"pin `{sha[:12]}`\n",
                "short8.md": f"history ({sha[:8]}) only\n",
                "longer.md": f"{sha}ff is a different object\n",
                "image.py": f'IMAGE = "{"f" * 40}"\n',
            }
            for name, body in cases.items():
                (root / name).write_text(body)
            hits = literal_hits(pins, sorted(root.iterdir()), root)
        self.assertEqual([h.split(":")[0] for h in hits], ["full.py", "prefix12.md"])


if __name__ == "__main__":
    unittest.main()
