#!/usr/bin/env python3
"""Build a deterministic bare-repository Gamescope dependency cache."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import signal
import stat
import subprocess
import tarfile
import tempfile
import threading
import tomllib


HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_ID = re.compile(r"[A-Za-z0-9._-]+")
PF_URL = re.compile(r"https://github\.com/pocketforge-os/[A-Za-z0-9._-]+(?:\.git)?")
GAMESCOPE_URL = "https://github.com/pocketforge-os/gamescope.git"
MANIFEST_PATH = ".github/pocketforge-source-closure.tsv"
MANIFEST_FIELDS = (
    "schema", "edge_id", "parent_id", "project_id", "path", "kind",
    "upstream_url", "upstream_revision", "declared_url", "locator_revision",
    "pf_url", "pf_revision", "tree_oid", "content_sha256", "license_path",
    "license_sha256", "selectors", "tests", "patch_status",
    "transform_receipt", "fork_history_proof", "fork_pin_ref",
)
REVISION_ROLES = ("upstream_revision", "locator_revision", "pf_revision")
TRANSACTION_SCHEMA = "pocketforge.gamescope-dependency-cache-transaction/v1"
TRANSACTION_TOKEN = re.compile(r"[0-9a-f]{32}")


class CacheError(RuntimeError):
    pass


class PublicationInterrupted(CacheError):
    pass


def run(*command: object, input_text: str | None = None,
        check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(value) for value in command], input=input_text, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise CacheError(f"{' '.join(str(value) for value in command)} failed: {detail}")
    return result


def git_bytes(git_dir: Path, *arguments: str, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", f"--git-dir={git_dir}", *arguments],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
    )
    if check and result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise CacheError(
            f"git --git-dir={git_dir} {' '.join(arguments)} failed: {detail}")
    return result.stdout


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def require_bare_mirror(path: Path, expected_url: str, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise CacheError(f"missing governed mirror: {label} ({path})")
    actual_url = run(
        "git", f"--git-dir={path}", "config", "--get", "remote.origin.url",
        check=False).stdout.strip()
    if actual_url != expected_url:
        raise CacheError(
            f"governed mirror URL mismatch: {label} "
            f"(actual={actual_url or '-'}, expected={expected_url})")


def has_commit(git_dir: Path, revision: str) -> bool:
    return run(
        "git", f"--git-dir={git_dir}", "cat-file", "-e",
        f"{revision}^{{commit}}", check=False).returncode == 0


def safe_relative(value: str, field: str, edge_id: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise CacheError(f"unsafe {field}: {edge_id}")


def parse_manifest(raw: bytes) -> list[dict[str, str]]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise CacheError(f"dependency manifest is not UTF-8: {error}") from error
    if not lines or lines[0] != "# gamescope-source-closure-v1":
        raise CacheError("Gamescope dependency manifest schema marker mismatch")
    reader = csv.DictReader(io.StringIO("\n".join(lines[1:])), dialect="excel-tab")
    if tuple(reader.fieldnames or ()) != MANIFEST_FIELDS:
        raise CacheError("Gamescope dependency manifest header mismatch")
    rows = list(reader)
    if not rows:
        raise CacheError("Gamescope dependency manifest is empty")
    seen_edges: set[str] = set()
    project_urls: dict[str, str] = {}
    for row in rows:
        edge_id = row["edge_id"]
        project = row["project_id"]
        if SAFE_ID.fullmatch(edge_id) is None or edge_id in seen_edges:
            raise CacheError(f"unsafe or duplicate dependency edge: {edge_id}")
        if SAFE_ID.fullmatch(project) is None:
            raise CacheError(f"unsafe dependency project: {edge_id}")
        safe_relative(row["path"], "dependency path", edge_id)
        safe_relative(row["license_path"], "licence path", edge_id)
        for field in (*REVISION_ROLES, "tree_oid"):
            if HEX40.fullmatch(row[field]) is None:
                raise CacheError(f"mutable {field}: {edge_id}")
        if HEX64.fullmatch(row["license_sha256"]) is None:
            raise CacheError(f"invalid licence digest: {edge_id}")
        if PF_URL.fullmatch(row["pf_url"]) is None:
            raise CacheError(f"non-PocketForge repository URL: {edge_id}")
        previous = project_urls.setdefault(project, row["pf_url"])
        if previous != row["pf_url"]:
            raise CacheError(f"inconsistent repository URL: {project}")
        seen_edges.add(edge_id)
    return rows


def read_manifest(gamescope: Path, head: str, expected_sha256: str) -> bytes:
    if HEX40.fullmatch(head) is None:
        raise CacheError("Gamescope head must be a full lowercase SHA-1")
    if HEX64.fullmatch(expected_sha256) is None:
        raise CacheError("manifest SHA256 must be a full lowercase digest")
    if not has_commit(gamescope, head):
        raise CacheError(f"missing governed Gamescope object: {head}")
    raw = git_bytes(gamescope, "show", f"{head}:{MANIFEST_PATH}")
    actual = digest_bytes(raw)
    if actual != expected_sha256:
        raise CacheError(
            "Gamescope dependency manifest digest mismatch "
            f"(actual={actual}, expected={expected_sha256})")
    return raw


def validate_platform_lock(path: Path, gamescope_head: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise CacheError(f"platform.lock is not a regular file: {path}")
    raw = path.read_bytes()
    try:
        lock = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CacheError(f"platform.lock is not valid TOML: {error}") from error
    repos = lock.get("repos")
    if not isinstance(repos, list):
        raise CacheError("platform.lock repos must be an array")
    gamescope = [repo for repo in repos
                 if isinstance(repo, dict) and repo.get("name") == "gamescope"]
    if len(gamescope) != 1:
        raise CacheError("platform.lock must contain exactly one Gamescope repository")
    if gamescope[0].get("url") != GAMESCOPE_URL:
        raise CacheError("platform.lock Gamescope URL mismatch")
    if gamescope[0].get("sha") != gamescope_head:
        raise CacheError("platform.lock Gamescope pin mismatch")
    return digest_bytes(raw)


def validate_inputs(rows: list[dict[str, str]], mirror_root: Path) -> dict[str, dict[str, object]]:
    projects: dict[str, dict[str, object]] = {}
    for row in rows:
        project = row["project_id"]
        values = projects.setdefault(project, {
            "url": row["pf_url"], "revisions": set(), "pins": set(), "refs": [],
        })
        for role in REVISION_ROLES:
            revision = row[role]
            values["revisions"].add(revision)  # type: ignore[union-attr]
            values["refs"].append({  # type: ignore[union-attr]
                "edge_id": row["edge_id"], "role": role,
                "ref": f"refs/pocketforge/cache-v1/{row['edge_id']}/{role}",
                "revision": revision,
            })
        values["pins"].add(row["pf_revision"])  # type: ignore[union-attr]

    for project, values in sorted(projects.items()):
        mirror = mirror_root / f"{project}.git"
        require_bare_mirror(mirror, str(values["url"]), project)
        for revision in sorted(values["revisions"]):  # type: ignore[arg-type]
            if not has_commit(mirror, revision):
                raise CacheError(f"missing governed mirror object: {project}@{revision}")

    for row in rows:
        mirror = mirror_root / f"{row['project_id']}.git"
        actual_tree = git_bytes(
            mirror, "rev-parse", f"{row['pf_revision']}^{{tree}}").decode().strip()
        if actual_tree != row["tree_oid"]:
            raise CacheError(f"tree pin mismatch: {row['edge_id']}")
        licence = git_bytes(
            mirror, "show", f"{row['pf_revision']}:{row['license_path']}")
        if digest_bytes(licence) != row["license_sha256"]:
            raise CacheError(f"licence digest mismatch: {row['edge_id']}")
    return projects


def canonical_repository(source: Path, destination: Path,
                         refs: list[dict[str, str]]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run("git", "init", "--bare", "--quiet", "--template=", destination)
    revisions = sorted({item["revision"] for item in refs})
    run(
        "git", "-c", "protocol.file.allow=always", f"--git-dir={destination}",
        "fetch", "--quiet", "--no-tags", "--no-write-fetch-head",
        "--no-recurse-submodules", source, *revisions,
    )
    update_lines = "".join(
        f"update {item['ref']} {item['revision']}\n"
        for item in sorted(refs, key=lambda value: value["ref"]))
    run("git", f"--git-dir={destination}", "update-ref", "--stdin",
        input_text=update_lines)
    run("git", f"--git-dir={destination}", "pack-refs", "--all", "--prune")
    first_revision = min(
        refs, key=lambda item: item["ref"])["revision"]
    (destination / "HEAD").write_text(f"{first_revision}\n", encoding="ascii")
    run(
        "git", "-c", "core.compression=9", "-c", "pack.compression=9",
        "-c", "pack.threads=1", "-c", "gc.writeCommitGraph=false",
        f"--git-dir={destination}", "repack", "-a", "-d", "-f", "-F",
        "--no-write-bitmap-index", "--no-write-midx", "--window=10",
        "--depth=50", "--threads=1",
    )
    run("git", f"--git-dir={destination}", "prune-packed")
    (destination / "config").write_text(
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        "\tfilemode = true\n"
        "\tbare = true\n"
        "\tlogallrefupdates = false\n",
        encoding="ascii",
    )
    description = destination / "description"
    if description.exists():
        description.unlink()

    actual_refs = run(
        "git", f"--git-dir={destination}", "for-each-ref",
        "--format=%(refname) %(objectname)", "refs/pocketforge/cache-v1",
    ).stdout.splitlines()
    expected_refs = [
        f"{item['ref']} {item['revision']}"
        for item in sorted(refs, key=lambda value: value["ref"])
    ]
    if actual_refs != expected_refs:
        raise CacheError(f"canonical reference mismatch: {destination.name}")
    fsck = run(
        "git", f"--git-dir={destination}", "fsck", "--full", "--strict",
        check=False)
    if fsck.returncode != 0 or fsck.stdout or fsck.stderr:
        detail = (fsck.stdout + fsck.stderr).strip()
        raise CacheError(f"Git reachability check failed: {destination.name}: {detail}")
    packs = sorted((destination / "objects" / "pack").glob("*"))
    suffixes = sorted(path.suffix for path in packs)
    if suffixes not in ([".idx", ".pack"], [".idx", ".pack", ".rev"]):
        raise CacheError(f"non-canonical pack set: {destination.name}")


def normalize_and_list_files(root: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise CacheError(f"cache output contains a symlink: {relative}")
        if stat.S_ISDIR(info.st_mode):
            path.chmod(0o755)
            continue
        if not stat.S_ISREG(info.st_mode):
            raise CacheError(f"cache output contains a special file: {relative}")
        path.chmod(0o644)
        files.append({
            "path": relative, "mode": "0644", "size": path.stat().st_size,
            "sha256": digest_file(path),
        })
    return files


def write_archive(root: Path, destination: Path) -> None:
    entries = sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix())
    with tarfile.open(destination, "w", format=tarfile.USTAR_FORMAT) as archive:
        for path in [root, *entries]:
            relative = path.relative_to(root).as_posix() if path != root else ""
            name = "gamescope-dependency-cache"
            if relative:
                name += f"/{relative}"
            if name.startswith("/") or ".." in PurePosixPath(name).parts:
                raise CacheError(f"unsafe archive member: {name}")
            info = archive.gettarinfo(str(path), arcname=name)
            if not (info.isdir() or info.isfile()):
                raise CacheError(f"unsafe archive member type: {name}")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            info.mode = 0o755 if info.isdir() else 0o644
            if info.isfile():
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
            else:
                archive.addfile(info)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def output_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "output_root": args.output_root.absolute(),
        "archive": args.archive.absolute(),
        "manifest": Path(f"{args.archive}.manifest.json").absolute(),
        "receipt": Path(f"{args.archive}.receipt.json").absolute(),
    }


def transaction_journal(archive: Path) -> Path:
    return archive.with_name(
        f".{archive.name}.gamescope-dependency-cache.transaction.json")


def transaction_stage(path: Path, token: str) -> Path:
    return path.with_name(f".{path.name}.gamescope-cache-{token}.staged")


def transaction_identity(args: argparse.Namespace,
                         targets: dict[str, Path]) -> dict[str, object]:
    return {
        "schema": TRANSACTION_SCHEMA,
        "gamescope_head": args.gamescope_head,
        "manifest_sha256": args.manifest_sha256,
        "targets": {name: str(path) for name, path in targets.items()},
    }


def path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def remove_transaction_path(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        raise CacheError(f"transaction path became a symlink: {path}")
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise CacheError(f"transaction directory has wrong type: {path}")
        shutil.rmtree(path)
    else:
        if not stat.S_ISREG(info.st_mode):
            raise CacheError(f"transaction file has wrong type: {path}")
        path.unlink()


def rollback_publication(targets: dict[str, Path], token: str,
                         journal: Path) -> None:
    failures = []
    ordered = (
        (targets["output_root"], True),
        (targets["receipt"], False),
        (targets["manifest"], False),
        (targets["archive"], False),
        (transaction_stage(targets["output_root"], token), True),
        (transaction_stage(targets["receipt"], token), False),
        (transaction_stage(targets["manifest"], token), False),
        (transaction_stage(targets["archive"], token), False),
        (Path(f"{journal}.tmp"), False),
    )
    for path, directory in ordered:
        try:
            remove_transaction_path(path, directory=directory)
        except (CacheError, OSError) as error:
            failures.append(str(error))
    if failures:
        raise CacheError("publication rollback incomplete: " + "; ".join(failures))
    if path_exists(journal):
        remove_transaction_path(journal, directory=False)
    for parent in {path.parent for path, _ in ordered} | {journal.parent}:
        fsync_directory(parent)


def recover_publication(args: argparse.Namespace) -> None:
    targets = output_paths(args)
    journal = transaction_journal(targets["archive"])
    journal_tmp = Path(f"{journal}.tmp")
    if path_exists(journal_tmp):
        remove_transaction_path(journal_tmp, directory=False)
        fsync_directory(journal.parent)
    if not path_exists(journal):
        return
    if journal.is_symlink() or not journal.is_file():
        raise CacheError(f"unsafe publication transaction journal: {journal}")
    try:
        record = json.loads(journal.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CacheError(f"invalid publication transaction journal: {error}") from error
    token = record.get("token") if isinstance(record, dict) else None
    expected = transaction_identity(args, targets)
    if (not isinstance(record, dict)
            or TRANSACTION_TOKEN.fullmatch(str(token)) is None
            or {key: value for key, value in record.items() if key != "token"} != expected):
        raise CacheError(f"publication transaction identity mismatch: {journal}")
    for target in targets.values():
        target.parent.mkdir(parents=True, exist_ok=True)
    rollback_publication(targets, str(token), journal)


def write_transaction_journal(journal: Path, record: dict[str, object]) -> None:
    temporary = Path(f"{journal}.tmp")
    payload = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, journal)
    fsync_directory(journal.parent)


def stage_file(source: Path, destination: Path,
               copy_file: Callable[[Path, Path], object]) -> None:
    copy_file(source, destination)
    destination.chmod(0o644)
    with destination.open("rb") as stream:
        os.fsync(stream.fileno())
    fsync_directory(destination.parent)


def publish_outputs(
        args: argparse.Namespace, cache_root: Path, archive_tmp: Path,
        manifest_tmp: Path, receipt_tmp: Path,
        publication_hook: Callable[[str], None] | None = None,
        copy_file: Callable[[Path, Path], object] = shutil.copyfile) -> None:
    targets = output_paths(args)
    if len(set(targets.values())) != len(targets):
        raise CacheError("cache output paths must be distinct")
    for path in targets.values():
        if path_exists(path):
            raise CacheError(f"refusing pre-existing output: {path}")

    token = secrets.token_hex(16)
    journal = transaction_journal(targets["archive"])
    stages = {name: transaction_stage(path, token) for name, path in targets.items()}
    for path in (journal, Path(f"{journal}.tmp"), *stages.values()):
        if path_exists(path):
            raise CacheError(f"refusing pre-existing transaction path: {path}")

    record = {**transaction_identity(args, targets), "token": token}
    hook = publication_hook or (lambda _boundary: None)
    previous_sigterm = None
    handler_installed = threading.current_thread() is threading.main_thread()
    if handler_installed:
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def interrupt(_signum: int, _frame: object) -> None:
            raise PublicationInterrupted("publication interrupted by SIGTERM")

        signal.signal(signal.SIGTERM, interrupt)
    try:
        write_transaction_journal(journal, record)
        os.replace(cache_root, stages["output_root"])
        fsync_directory(stages["output_root"].parent)
        for name, source in (
                ("archive", archive_tmp),
                ("manifest", manifest_tmp),
                ("receipt", receipt_tmp)):
            stage_file(source, stages[name], copy_file)

        # The cache root is the commit marker: it becomes visible only after all
        # validating sidecars have reached their final names.
        for name in ("archive", "manifest", "receipt", "output_root"):
            os.replace(stages[name], targets[name])
            fsync_directory(targets[name].parent)
            hook(f"after_{name}")
        journal.unlink()
        fsync_directory(journal.parent)
    except BaseException as error:
        if handler_installed:
            signal.signal(signal.SIGTERM, previous_sigterm)
            handler_installed = False
        try:
            rollback_publication(targets, token, journal)
        except (CacheError, OSError) as rollback_error:
            raise CacheError(
                f"publication failed and rollback requires retry recovery: {rollback_error}"
            ) from error
        raise
    finally:
        if handler_installed:
            signal.signal(signal.SIGTERM, previous_sigterm)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gamescope-git-dir", type=Path, required=True)
    parser.add_argument("--gamescope-head", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--mirror-root", type=Path, required=True)
    parser.add_argument("--platform-lock", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    return parser.parse_args()


def build(args: argparse.Namespace,
          publication_hook: Callable[[str], None] | None = None,
          copy_file: Callable[[Path, Path], object] = shutil.copyfile) -> None:
    recover_publication(args)
    targets = output_paths(args)
    for path in targets.values():
        if path_exists(path):
            raise CacheError(f"refusing pre-existing output: {path}")
    require_bare_mirror(args.gamescope_git_dir, GAMESCOPE_URL, "gamescope")
    platform_lock_sha256 = validate_platform_lock(
        args.platform_lock, args.gamescope_head)
    raw_manifest = read_manifest(
        args.gamescope_git_dir, args.gamescope_head, args.manifest_sha256)
    rows = parse_manifest(raw_manifest)
    projects = validate_inputs(rows, args.mirror_root)

    args.output_root.parent.mkdir(parents=True, exist_ok=True)
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
            prefix=".gamescope-dependency-cache.", dir=args.output_root.parent) as temporary:
        temporary_root = Path(temporary)
        cache_root = temporary_root / "cache-root"
        cache = cache_root / args.manifest_sha256
        repos = cache / "repos"
        repos.mkdir(parents=True)
        repository_records = []
        for project, values in sorted(projects.items()):
            refs = sorted(values["refs"], key=lambda value: value["ref"])  # type: ignore[arg-type]
            canonical_repository(
                args.mirror_root / f"{project}.git", repos / f"{project}.git", refs)
            repository_records.append({
                "project_id": project, "pf_url": values["url"], "refs": refs,
            })

        project_pin_count = len({(row["project_id"], row["pf_revision"]) for row in rows})
        revision_ref_count = sum(len(record["refs"]) for record in repository_records)
        admission = {
            "schema": "gamescope-source-admission-v1",
            "gamescope_head": args.gamescope_head,
            "manifest_sha256": args.manifest_sha256,
            "projects": [
                {
                    "project_id": project,
                    "pf_url": values["url"],
                    "pins": sorted(values["pins"]),  # type: ignore[arg-type]
                }
                for project, values in sorted(projects.items())
            ],
            "validated_edges": len(rows),
            "verified_project_pins": project_pin_count,
        }
        (cache / "admission-receipt.json").write_text(
            json.dumps(admission, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        cache_identity = {
            "schema": "pocketforge.gamescope-dependency-cache/v1",
            "artifact_type": "gamescope-dependency-cache",
            "gamescope_source_url": GAMESCOPE_URL,
            "gamescope_head": args.gamescope_head,
            "dependency_manifest_path": MANIFEST_PATH,
            "dependency_manifest_sha256": args.manifest_sha256,
            "platform_lock_sha256": platform_lock_sha256,
            "edge_count": len(rows),
            "repository_count": len(projects),
            "project_pin_count": project_pin_count,
            "revision_ref_count": revision_ref_count,
            "repositories": repository_records,
        }
        (cache_root / ".pf-gamescope-dependency-cache.json").write_text(
            json.dumps(cache_identity, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        files = normalize_and_list_files(cache_root)
        artifact_manifest = {
            "schema": "pocketforge.gamescope-dependency-cache/v1",
            "artifact_type": "gamescope-dependency-cache",
            "gamescope_source_url": GAMESCOPE_URL,
            "gamescope_head": args.gamescope_head,
            "dependency_manifest_path": MANIFEST_PATH,
            "dependency_manifest_sha256": args.manifest_sha256,
            "dependency_manifest_rows": rows,
            "platform_lock_sha256": platform_lock_sha256,
            "edge_count": len(rows),
            "repository_count": len(projects),
            "project_pin_count": project_pin_count,
            "revision_ref_count": revision_ref_count,
            "repositories": repository_records,
            "files": files,
        }
        archive_tmp = temporary_root / "gamescope-dependency-cache.tar"
        write_archive(cache_root, archive_tmp)
        archive_sha256 = digest_file(archive_tmp)
        artifact_manifest["archive_sha256"] = archive_sha256
        manifest_bytes = (
            json.dumps(artifact_manifest, indent=2, sort_keys=True) + "\n").encode()
        receipt = {
            "schema": "pocketforge.gamescope-dependency-cache-receipt/v1",
            "artifact_type": "gamescope-dependency-cache",
            "archive_sha256": archive_sha256,
            "archive_size": archive_tmp.stat().st_size,
            "manifest_sha256": digest_bytes(manifest_bytes),
            "dependency_manifest_sha256": args.manifest_sha256,
            "platform_lock_sha256": platform_lock_sha256,
            "edge_count": len(rows),
            "repository_count": len(projects),
            "project_pin_count": project_pin_count,
            "revision_ref_count": revision_ref_count,
            "file_count": len(files),
        }
        manifest_tmp = temporary_root / "manifest.json"
        receipt_tmp = temporary_root / "receipt.json"
        manifest_tmp.write_bytes(manifest_bytes)
        receipt_tmp.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        publish_outputs(
            args, cache_root, archive_tmp, manifest_tmp, receipt_tmp,
            publication_hook=publication_hook, copy_file=copy_file)

    print(f"schema={artifact_manifest['schema']}")
    print(f"archive_sha256={archive_sha256}")
    print(f"archive_size={args.archive.stat().st_size}")
    print(f"manifest_sha256={digest_bytes(manifest_bytes)}")
    print(f"dependency_manifest_sha256={args.manifest_sha256}")
    print(f"platform_lock_sha256={platform_lock_sha256}")
    print(f"edges={len(rows)}")
    print(f"repositories={len(projects)}")
    print(f"project_pins={project_pin_count}")
    print(f"revision_refs={revision_ref_count}")
    print(f"files={len(files)}")


def main() -> int:
    try:
        build(parse_args())
    except (CacheError, OSError, UnicodeError, ValueError) as error:
        print(f"gamescope-dependency-cache: {error}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
