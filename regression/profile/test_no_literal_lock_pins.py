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
they name a past advance, not the current pin. Widening GUARDED_REPOS is the follow-up
for the remaining source repos (their tests still carry literals today).
"""
import pathlib
import re
import subprocess
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCK = ROOT / "platform.lock"
GUARDED_REPOS = frozenset(
    {"kernel-sunxi-4.9", "kernel-sunxi-5.15", "kernel-sunxi-6.x", "kernel-sunxi-7.x"}
)
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


def literal_hits(pins: dict[str, str], files: list[pathlib.Path], root: pathlib.Path) -> list[str]:
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
                        hits.append(f"{rel}:{lineno}: {run} is the current {sites}")
    return hits


class NoLiteralLockPins(unittest.TestCase):
    def test_guard_has_pins_to_check(self):
        pins = guarded_pins(tomllib.loads(LOCK.read_text()))
        self.assertIn("repos.kernel-sunxi-7.x.sha", " ".join(pins.values()))

    def test_no_test_or_doc_carries_a_current_guarded_pin(self):
        pins = guarded_pins(tomllib.loads(LOCK.read_text()))
        hits = literal_hits(pins, scanned_files(ROOT), ROOT)
        self.assertEqual(
            hits,
            [],
            "read the pin from platform.lock (profile.load_lock()) or name the lock "
            "entry instead of copying its SHA:\n" + "\n".join(hits),
        )

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
