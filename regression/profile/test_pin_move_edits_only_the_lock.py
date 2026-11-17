"""tsp-hqm1p.182.339: a pin advance edits platform.lock only.

Copies the tracked tree to a temp dir, advances every guarded pin (every non-image lock repo) there the way
mission-control `scripts/g16/pf-pin` does (rewrite the [[repos]] `sha`, append a
`# <tag>: <new8> = <old8> + ...` lineage line above it, and move every [profile_pins]
value that equalled the old pin), then runs every other regression/profile suite in the
copy. A suite that hard-codes a pin, or a golden that hashes one, fails here instead of
on the first real pin PR (platform#493 went red on exactly that).
"""
import hashlib
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SELF = pathlib.Path(__file__).name
# tsp-hqm1p.182.352: every guarded repo, not only the kernels (the set test_no_literal_lock_pins.py enforces).
_guard = importlib.util.spec_from_file_location("no_literal_lock_pins", pathlib.Path(__file__).with_name("test_no_literal_lock_pins.py"))
_mod = importlib.util.module_from_spec(_guard)
_guard.loader.exec_module(_mod)
GUARDED_REPOS = tuple(sorted(_mod.GUARDED_REPOS))


def advance(text: str, repo: str, new: str, tag: str) -> str:
    """Move one [[repos]] pin and the profile pins that equalled it."""
    block = re.compile(
        r'(^name\s*=\s*"' + re.escape(repo) + r'"[^\n]*\n(?:(?!\[\[repos\]\]).*\n)*?)'
        r'(sha\s*=\s*")([0-9a-f]{40})(")',
        re.M,
    )
    m = block.search(text)
    if m is None:
        raise ValueError(f"{repo}: no [[repos]] sha line")
    old = m.group(3)
    lineage = f"# {tag}: {new[:8]} = {old[:8]} + simulated advance only.\n"
    text = text[: m.start(2)] + lineage + m.group(2) + new + m.group(4) + text[m.end(4):]
    return re.sub(r'^(\w+\s*=\s*")' + old + '"', lambda k: k.group(1) + new + '"', text, flags=re.M)


def tracked(root: pathlib.Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
    ).stdout.decode()
    return [p for p in out.split("\0") if p and (root / p).is_file()]


class PinMoveEditsOnlyTheLock(unittest.TestCase):
    def test_advance_rewrites_repo_and_equal_profile_pins_only(self):
        old, new = "a" * 40, "b" * 40
        text = (
            '[profile_pins.x]\nkernel = "' + old + '"\n[profile_pins.y]\nkernel = "' + "c" * 40 + '"\n'
            '[[repos]]\nname = "kernel-sunxi-7.x"\nurl = "u"\n# t: aaaaaaaa = 99999999 + k.\n'
            'sha  = "' + old + '"\n[[repos]]\nname = "image"\nsha = "' + "d" * 40 + '"\n'
        )
        got = advance(text, "kernel-sunxi-7.x", new, "sim")
        lock = tomllib.loads(got)
        self.assertEqual(lock["profile_pins"]["x"]["kernel"], new)
        self.assertEqual(lock["profile_pins"]["y"]["kernel"], "c" * 40)
        self.assertEqual([r["sha"] for r in lock["repos"]], [new, "d" * 40])
        self.assertIn("# sim: bbbbbbbb = aaaaaaaa + simulated advance only.\nsha  =", got)

    def test_profile_suites_pass_after_a_lock_only_advance_of_every_guarded_pin(self):
        with tempfile.TemporaryDirectory(prefix="pf-pin-move-") as tmp:
            copy = pathlib.Path(tmp)
            for rel in tracked(ROOT):
                (copy / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, copy / rel)
            subprocess.run(["git", "init", "-q", str(copy)], check=True)
            subprocess.run(["git", "-C", str(copy), "add", "-A"], check=True)
            lock_path = copy / "platform.lock"
            text = lock_path.read_text()
            lock = tomllib.loads(text)
            names = {r["name"] for r in lock["repos"]}
            for repo in GUARDED_REPOS:
                if repo not in names:
                    continue
                old = next(r["sha"] for r in lock["repos"] if r["name"] == repo)
                text = advance(text, repo, hashlib.sha1(old.encode()).hexdigest(), "sim")
            lock_path.write_text(text)
            failures = []
            env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
            for suite in sorted((copy / "regression" / "profile").glob("test_*.py")):
                if suite.name == SELF:
                    continue
                run = subprocess.run(
                    [sys.executable, "-B", str(suite)],
                    cwd=copy,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if run.returncode != 0:
                    tail = "\n".join(run.stderr.splitlines()[-15:])
                    failures.append(f"{suite.name}:\n{tail}")
            self.assertEqual(failures, [], "\n\n".join(failures))


if __name__ == "__main__":
    unittest.main()
