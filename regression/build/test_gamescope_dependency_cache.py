#!/usr/bin/env python3
"""Regression coverage for the deterministic Gamescope dependency cache."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / "core" / "gamescope-dependency-cache.py"
FIELDS = (
    "schema", "edge_id", "parent_id", "project_id", "path", "kind",
    "upstream_url", "upstream_revision", "declared_url", "locator_revision",
    "pf_url", "pf_revision", "tree_oid", "content_sha256", "license_path",
    "license_sha256", "selectors", "tests", "patch_status",
    "transform_receipt", "fork_history_proof", "fork_pin_ref",
)


def run(*command: object, cwd: Path | None = None,
        check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(value) for value in command], cwd=cwd, check=False,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(map(str, command))}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DependencyCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="gamescope-cache-test.")
        self.root = Path(self.temporary.name)
        self.mirrors_a = self.root / "mirrors-a"
        self.mirrors_b = self.root / "mirrors-b"
        self.mirrors_a.mkdir()
        self.mirrors_b.mkdir()
        self.histories: dict[str, list[str]] = {}
        for project in ("drm", "seatd", "v4l-utils"):
            self.histories[project] = self.make_project(project)
        self.rows = self.make_rows()
        self.gamescope, self.head, self.manifest_sha = self.make_gamescope(self.rows)
        shutil.copytree(self.gamescope, self.mirrors_a / "gamescope.git")
        shutil.copytree(self.gamescope, self.mirrors_b / "gamescope.git")
        self.platform_lock = self.root / "platform.lock"
        self.platform_lock.write_text(
            "lockfile_version = 1\n"
            "[[repos]]\n"
            "name = \"gamescope\"\n"
            "url = \"https://github.com/pocketforge-os/gamescope.git\"\n"
            f"sha = \"{self.head}\"\n",
            encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_project(self, project: str) -> list[str]:
        work = self.root / f"work-{project}"
        work.mkdir()
        run("git", "init", "-q", work)
        run("git", "config", "user.name", "PocketForge test", cwd=work)
        run("git", "config", "user.email", "test@example.invalid", cwd=work)
        (work / "LICENSE").write_text(f"licence for {project}\n", encoding="utf-8")
        revisions = []
        for index in range(4):
            payload = (f"{project}:{index}:" + "same-prefix-" * 4096 + "\n")
            (work / "payload").write_text(payload, encoding="utf-8")
            run("git", "add", ".", cwd=work)
            run("git", "commit", "-qm", f"revision {index}", cwd=work)
            revisions.append(run("git", "rev-parse", "HEAD", cwd=work).stdout.strip())
        url = f"https://github.com/pocketforge-os/{project}.git"
        for label, mirror_root, window, depth in (
                ("a", self.mirrors_a, "32", "32"),
                ("b", self.mirrors_b, "1", "1")):
            mirror = mirror_root / f"{project}.git"
            run("git", "clone", "--bare", "-q", work, mirror)
            run("git", f"--git-dir={mirror}", "remote", "set-url", "origin", url)
            keep_unreachable = []
            if label == "b":
                extra = self.root / f"unreachable-{project}"
                extra.write_text(f"unreachable source-pack input for {project}\n")
                extra_oid = run(
                    "git", f"--git-dir={mirror}", "hash-object", "-w", extra
                ).stdout.strip()
                run("git", f"--git-dir={mirror}", "update-ref",
                    "refs/uncontrolled/extra", extra_oid)
            run("git", f"--git-dir={mirror}", "repack", "-a", "-d", "-f", "-F",
                "--no-write-bitmap-index", *keep_unreachable,
                f"--window={window}", f"--depth={depth}", "--threads=1")
            if label == "b":
                run("git", f"--git-dir={mirror}", "update-ref", "-d",
                    "refs/uncontrolled/extra")
            self.assertEqual(
                run("git", f"--git-dir={mirror}", "config", "--get",
                    "remote.origin.url").stdout.strip(), url, label)
        return revisions

    def make_rows(self) -> list[dict[str, str]]:
        rows = []
        specifications = (
            ("drm-one", "drm", 0, 1, 2),
            ("drm-two", "drm", 1, 2, 3),
            ("seatd", "seatd", 0, 1, 2),
            ("v4l-utils", "v4l-utils", 0, 1, 2),
        )
        for edge_id, project, upstream, locator, pin in specifications:
            revisions = self.histories[project]
            mirror = self.mirrors_a / f"{project}.git"
            pf_revision = revisions[pin]
            tree = run("git", f"--git-dir={mirror}", "rev-parse",
                       f"{pf_revision}^{{tree}}").stdout.strip()
            licence = run("git", f"--git-dir={mirror}", "show",
                          f"{pf_revision}:LICENSE").stdout.encode()
            url = f"https://github.com/pocketforge-os/{project}.git"
            rows.append({
                "schema": "1", "edge_id": edge_id, "parent_id": "gamescope",
                "project_id": project, "path": f"subprojects/{edge_id}",
                "kind": "wrap-git", "upstream_url": url,
                "upstream_revision": revisions[upstream], "declared_url": url,
                "locator_revision": revisions[locator], "pf_url": url,
                "pf_revision": pf_revision, "tree_oid": tree,
                "content_sha256": "-", "license_path": "LICENSE",
                "license_sha256": hashlib.sha256(licence).hexdigest(),
                "selectors": "native,aarch64", "tests": "fixture",
                "patch_status": "patched", "transform_receipt": "-",
                "fork_history_proof": "refs-sha256:" + "1" * 64,
                "fork_pin_ref": "refs/heads/pocketforge",
            })
        return rows

    def manifest_bytes(self, rows: list[dict[str, str]]) -> bytes:
        stream = io.StringIO(newline="")
        stream.write("# gamescope-source-closure-v1\n")
        writer = csv.DictWriter(stream, fieldnames=FIELDS, dialect="excel-tab",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue().encode()

    def make_gamescope(self, rows: list[dict[str, str]]) -> tuple[Path, str, str]:
        work = self.root / f"gamescope-work-{len(list(self.root.glob('gamescope-work-*')))}"
        (work / ".github").mkdir(parents=True)
        manifest = work / ".github" / "pocketforge-source-closure.tsv"
        manifest.write_bytes(self.manifest_bytes(rows))
        run("git", "init", "-q", work)
        run("git", "config", "user.name", "PocketForge test", cwd=work)
        run("git", "config", "user.email", "test@example.invalid", cwd=work)
        run("git", "add", ".", cwd=work)
        run("git", "commit", "-qm", "manifest", cwd=work)
        head = run("git", "rev-parse", "HEAD", cwd=work).stdout.strip()
        bare = self.root / f"gamescope-{head}.git"
        run("git", "clone", "--bare", "-q", work, bare)
        run("git", f"--git-dir={bare}", "remote", "set-url", "origin",
            "https://github.com/pocketforge-os/gamescope.git")
        return bare, head, hashlib.sha256(manifest.read_bytes()).hexdigest()

    def produce(self, label: str, mirrors: Path | None = None, *,
                gamescope: Path | None = None, head: str | None = None,
                manifest_sha: str | None = None,
                platform_lock: Path | None = None,
                check: bool = True) -> subprocess.CompletedProcess[str]:
        target = self.root / label
        target.mkdir()
        selected_head = head or self.head
        if platform_lock is None and selected_head != self.head:
            platform_lock = target / "platform.lock"
            platform_lock.write_text(
                "[[repos]]\n"
                "name = \"gamescope\"\n"
                "url = \"https://github.com/pocketforge-os/gamescope.git\"\n"
                f"sha = \"{selected_head}\"\n",
                encoding="utf-8")
        return run(
            "python3", PRODUCER,
            "--gamescope-git-dir", gamescope or self.gamescope,
            "--gamescope-head", selected_head,
            "--manifest-sha256", manifest_sha or self.manifest_sha,
            "--mirror-root", mirrors or self.mirrors_a,
            "--platform-lock", platform_lock or self.platform_lock,
            "--output-root", target / "cache-root",
            "--archive", target / "gamescope-dependency-cache.tar",
            check=check,
        )

    def test_two_pack_layouts_produce_one_complete_safe_cache(self) -> None:
        # RED property: equal admitted objects in all three known repositories
        # have distinct source pack identities before canonicalization.
        for project in ("drm", "seatd", "v4l-utils"):
            packs_a = sorted(path.name for path in
                             (self.mirrors_a / f"{project}.git/objects/pack").glob("*.pack"))
            packs_b = sorted(path.name for path in
                             (self.mirrors_b / f"{project}.git/objects/pack").glob("*.pack"))
            self.assertNotEqual(packs_a, packs_b, project)

        self.produce("one", self.mirrors_a)
        self.produce("two", self.mirrors_b)
        one = self.root / "one"
        two = self.root / "two"
        for relative in (
                "gamescope-dependency-cache.tar",
                "gamescope-dependency-cache.tar.manifest.json",
                "gamescope-dependency-cache.tar.receipt.json"):
            self.assertEqual((one / relative).read_bytes(), (two / relative).read_bytes())

        manifest = json.loads(
            (one / "gamescope-dependency-cache.tar.manifest.json").read_text())
        receipt = json.loads(
            (one / "gamescope-dependency-cache.tar.receipt.json").read_text())
        self.assertEqual(manifest["schema"], "pocketforge.gamescope-dependency-cache/v1")
        self.assertEqual(receipt["schema"], "pocketforge.gamescope-dependency-cache-receipt/v1")
        self.assertEqual(manifest["revision_ref_count"], 12)
        self.assertEqual(manifest["repository_count"], 3)
        self.assertNotIn("pocketforge.gamescope-deterministic-publication/v1",
                         json.dumps(manifest))
        identity = json.loads(
            (one / "cache-root/.pf-gamescope-dependency-cache.json").read_text())
        self.assertEqual(identity["schema"], manifest["schema"])
        self.assertEqual(identity["platform_lock_sha256"],
                         manifest["platform_lock_sha256"])
        actual_files = {}
        output_root = one / "cache-root"
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                actual_files[path.relative_to(output_root).as_posix()] = {
                    "mode": f"{path.stat().st_mode & 0o777:04o}",
                    "sha256": sha256(path), "size": path.stat().st_size,
                }
        self.assertEqual(manifest["files"], [
            {"path": path, **values} for path, values in actual_files.items()
        ])

        for project in ("drm", "seatd", "v4l-utils"):
            repo = output_root / self.manifest_sha / "repos" / f"{project}.git"
            refs = run("git", f"--git-dir={repo}", "for-each-ref",
                       "--format=%(refname) %(objectname)",
                       "refs/pocketforge/cache-v1").stdout.splitlines()
            expected = 6 if project == "drm" else 3
            self.assertEqual(len(refs), expected)
            self.assertEqual(run("git", f"--git-dir={repo}", "fsck", "--full",
                                 "--strict").stdout, "")

        archive = one / "gamescope-dependency-cache.tar"
        with tarfile.open(archive, "r:") as stream:
            names = [member.name for member in stream]
            self.assertEqual(names, sorted(names))
            self.assertEqual(len(names), len(set(names)))
            for member in stream.getmembers():
                self.assertTrue(member.isdir() or member.isfile(), member.name)
                self.assertFalse(member.name.startswith("/"), member.name)
                self.assertNotIn("..", Path(member.name).parts)
                self.assertEqual((member.uid, member.gid, member.mtime), (0, 0, 0))

    def test_missing_and_wrong_pins_fail_closed(self) -> None:
        missing_rows = [dict(row) for row in self.rows]
        missing_rows[0]["pf_revision"] = "f" * 40
        missing_gamescope, missing_head, missing_sha = self.make_gamescope(missing_rows)
        result = self.produce(
            "missing", gamescope=missing_gamescope, head=missing_head,
            manifest_sha=missing_sha, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"missing governed mirror object: drm@{'f' * 40}", result.stderr)

        wrong_rows = [dict(row) for row in self.rows]
        wrong_rows[0]["tree_oid"] = "0" * 40
        wrong_gamescope, wrong_head, wrong_sha = self.make_gamescope(wrong_rows)
        result = self.produce(
            "wrong", gamescope=wrong_gamescope, head=wrong_head,
            manifest_sha=wrong_sha, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tree pin mismatch: drm-one", result.stderr)

        wrong_lock = self.root / "wrong-platform.lock"
        wrong_lock.write_text(
            "[[repos]]\n"
            "name = \"gamescope\"\n"
            "url = \"https://github.com/pocketforge-os/gamescope.git\"\n"
            f"sha = \"{'0' * 40}\"\n",
            encoding="utf-8")
        result = self.produce(
            "wrong-lock", platform_lock=wrong_lock, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("platform.lock Gamescope pin mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
