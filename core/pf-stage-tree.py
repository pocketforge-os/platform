#!/usr/bin/env python3
"""Own one retained --stage-only source tree per device, without deletion."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "pocketforge.stage-tree/v1"
MANIFEST = ".pf-stage-tree.json"
BUILD_SCHEMA = "pocketforge.build-tree/v1"
BUILD_MANIFEST = ".pf-build-tree.json"
CALLER_SCHEMA = "pocketforge.caller-temporary/v1"
CALLER_MANIFEST = ".pf-caller-temporary.json"
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
BOOT_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class Refusal(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parent_identity() -> tuple[int, str, int]:
    """Return the exact producer shell identity, not this short-lived helper."""
    pid = os.getppid()
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
            encoding="ascii"
        ).strip()
        stat_tail = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").rpartition(") ")[2]
        start_ticks = int(stat_tail.split()[19])
    except (OSError, UnicodeError, ValueError, IndexError) as error:
        raise Refusal("owner_identity_unavailable") from error
    if pid <= 1 or not BOOT_ID.fullmatch(boot_id) or start_ticks <= 0:
        raise Refusal("owner_identity_unavailable")
    return pid, boot_id, start_ticks


def process_start_ticks(pid: int) -> int:
    try:
        stat_tail = Path(f"/proc/{pid}/stat").read_text(
            encoding="ascii"
        ).rpartition(") ")[2]
        return int(stat_tail.split()[19])
    except (OSError, UnicodeError, ValueError, IndexError) as error:
        raise Refusal("owner_not_live") from error


def normal_absolute(raw: str, label: str) -> Path:
    path = Path(raw)
    if not path.is_absolute() or os.path.normpath(raw) != raw:
        raise Refusal(f"invalid_{label}")
    return path


def reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return
        if stat.S_ISLNK(mode):
            raise Refusal("symlink_escape")


def validate_args(args: argparse.Namespace) -> tuple[Path, Path]:
    for value, label in (
        (args.producer, "producer"),
        (args.bead, "bead"),
        (args.device, "device"),
    ):
        if not TOKEN.fullmatch(value):
            raise Refusal(f"invalid_{label}")
    if not SHA256.fullmatch(args.input_sha):
        raise Refusal("invalid_input_sha")
    root = normal_absolute(args.root, "root")
    tree = normal_absolute(args.tree, "tree")
    if root == Path(root.anchor) or tree != root / args.device:
        raise Refusal("namespace_mismatch")
    reject_symlink_components(root)
    reject_symlink_components(tree)
    return root, tree


def validate_build_args(args: argparse.Namespace) -> tuple[Path, Path]:
    for value, label in (
        (args.producer, "producer"),
        (args.bead, "bead"),
        (args.device, "device"),
    ):
        if not TOKEN.fullmatch(value):
            raise Refusal(f"invalid_{label}")
    root = normal_absolute(args.root, "root")
    tree = normal_absolute(args.tree, "tree")
    if root == Path(root.anchor) or tree != root / args.bead / args.device:
        raise Refusal("namespace_mismatch")
    reject_symlink_components(root)
    reject_symlink_components(tree)
    return root, tree


def validate_caller_temporary_args(args: argparse.Namespace) -> tuple[Path, Path]:
    for value, label in (
        (args.producer, "producer"),
        (args.bead, "bead"),
        (args.device, "device"),
    ):
        if not TOKEN.fullmatch(value):
            raise Refusal(f"invalid_{label}")
    root = normal_absolute(args.root, "root")
    tree = normal_absolute(args.tree, "tree")
    if root == Path(root.anchor) or tree == Path(tree.anchor):
        raise Refusal("namespace_mismatch")
    reject_symlink_components(root)
    reject_symlink_components(tree)
    try:
        tree.relative_to(root)
    except ValueError:
        pass
    else:
        raise Refusal("managed_namespace_requires_manifest")
    try:
        root.relative_to(tree)
    except ValueError:
        pass
    else:
        raise Refusal("managed_namespace_requires_manifest")
    return root, tree


def lock_root(root: Path) -> int:
    try:
        mode = os.lstat(root).st_mode
    except FileNotFoundError:
        reject_symlink_components(root.parent)
        if not root.parent.is_dir():
            raise Refusal("root_parent_missing")
        try:
            os.mkdir(root, 0o700)
        except FileExistsError:
            pass
        mode = os.lstat(root).st_mode
    if stat.S_ISLNK(mode):
        raise Refusal("symlink_escape")
    if not stat.S_ISDIR(mode):
        raise Refusal("invalid_root")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as error:
        raise Refusal("invalid_root") from error
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    return descriptor


def lock_existing_root(root: Path) -> int:
    try:
        mode = os.lstat(root).st_mode
    except FileNotFoundError as error:
        raise Refusal("root_missing") from error
    if stat.S_ISLNK(mode):
        raise Refusal("symlink_escape")
    if not stat.S_ISDIR(mode):
        raise Refusal("invalid_root")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as error:
        raise Refusal("invalid_root") from error
    fcntl.flock(descriptor, fcntl.LOCK_SH)
    return descriptor


def lock_existing_tree(tree: Path) -> int:
    try:
        mode = os.lstat(tree).st_mode
    except FileNotFoundError as error:
        raise Refusal("tree_missing") from error
    if stat.S_ISLNK(mode):
        raise Refusal("symlink_escape")
    if not stat.S_ISDIR(mode):
        raise Refusal("invalid_tree")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(tree, flags)
    except OSError as error:
        raise Refusal("invalid_tree") from error
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    return descriptor


def print_bound(args: argparse.Namespace, retained: int) -> None:
    print(
        f"STAGE_TREE_BOUND producer={args.producer} device={args.device} "
        f"max_retained=1 retained={retained}"
    )


def refuse(args: argparse.Namespace, tree: Path, reason: str) -> int:
    print(
        f"STAGE_TREE_REFUSE producer={args.producer} device={args.device} "
        f"path={tree} keep_reason={reason}",
        file=sys.stderr,
    )
    return 1


def refuse_build(args: argparse.Namespace, tree: Path, reason: str) -> int:
    print(
        f"BUILD_TREE_REFUSE producer={args.producer} device={args.device} "
        f"path={tree} keep_reason={reason}",
        file=sys.stderr,
    )
    return 1


def load_manifest(tree: Path) -> dict[str, Any]:
    path = tree / MANIFEST
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as error:
        raise Refusal("legacy_no_manifest") from error
    if stat.S_ISLNK(mode):
        raise Refusal("symlink_escape")
    if not stat.S_ISREG(mode):
        raise Refusal("invalid_manifest")
    try:
        with path.open(encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Refusal("invalid_manifest") from error
    if not isinstance(manifest, dict):
        raise Refusal("invalid_manifest")
    return manifest


def load_build_manifest(tree: Path) -> dict[str, Any]:
    path = tree / BUILD_MANIFEST
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as error:
        raise Refusal("legacy_no_manifest") from error
    if stat.S_ISLNK(mode):
        raise Refusal("symlink_escape")
    if not stat.S_ISREG(mode):
        raise Refusal("invalid_manifest")
    try:
        with path.open(encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Refusal("invalid_manifest") from error
    if not isinstance(manifest, dict):
        raise Refusal("invalid_manifest")
    return manifest


def load_caller_manifest(tree: Path) -> dict[str, Any]:
    path = tree / CALLER_MANIFEST
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as error:
        raise Refusal("caller_temporary_not_empty") from error
    if stat.S_ISLNK(mode):
        raise Refusal("symlink_escape")
    if not stat.S_ISREG(mode):
        raise Refusal("invalid_manifest")
    try:
        with path.open(encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Refusal("invalid_manifest") from error
    if not isinstance(manifest, dict):
        raise Refusal("invalid_manifest")
    return manifest


def safe_relative_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    path = Path(value)
    return (
        not path.is_absolute()
        and bool(path.parts)
        and all(part not in ("", ".", "..") for part in path.parts)
    )


def validate_build_manifest(
    manifest: dict[str, Any], args: argparse.Namespace, tree: Path
) -> None:
    required = {
        "schema",
        "bead",
        "device",
        "host",
        "created_utc",
        "producer",
        "producer_version",
        "state",
        "owner",
        "artifacts",
        "remote_log",
    }
    if not required.issubset(manifest) or manifest.get("schema") != BUILD_SCHEMA:
        raise Refusal("invalid_manifest")
    if (
        manifest.get("bead") != args.bead
        or manifest.get("device") != args.device
        or manifest.get("state") != "running"
    ):
        raise Refusal("manifest_identity_mismatch")
    if (
        not isinstance(manifest.get("host"), str)
        or not manifest["host"]
        or not isinstance(manifest.get("producer"), str)
        or not TOKEN.fullmatch(manifest["producer"])
        or not isinstance(manifest.get("producer_version"), int)
        or manifest["producer_version"] < 0
        or not isinstance(manifest.get("remote_log"), str)
        or not Path(manifest["remote_log"]).is_absolute()
    ):
        raise Refusal("invalid_manifest")
    try:
        dt.datetime.strptime(manifest["created_utc"], "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError) as error:
        raise Refusal("invalid_manifest") from error

    owner = manifest.get("owner")
    if (
        not isinstance(owner, dict)
        or set(owner) != {"pid", "boot_id", "start_ticks"}
        or not isinstance(owner.get("pid"), int)
        or owner["pid"] <= 1
        or not isinstance(owner.get("boot_id"), str)
        or not BOOT_ID.fullmatch(owner["boot_id"])
        or not isinstance(owner.get("start_ticks"), int)
        or owner["start_ticks"] <= 0
    ):
        raise Refusal("invalid_manifest")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise Refusal("invalid_manifest")
    artifact_paths: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {
            "path",
            "sha256",
            "preservation",
        }:
            raise Refusal("invalid_manifest")
        if not safe_relative_path(artifact["path"]):
            raise Refusal("invalid_manifest")
        artifact_paths.append(artifact["path"])
        if artifact["sha256"] is not None and not (
            isinstance(artifact["sha256"], str)
            and SHA256.fullmatch(artifact["sha256"])
        ):
            raise Refusal("invalid_manifest")
        if not isinstance(artifact["preservation"], list):
            raise Refusal("invalid_manifest")
        for record in artifact["preservation"]:
            if (
                not isinstance(record, dict)
                or set(record) != {"kind", "path", "sha256"}
                or record["kind"] != "filesystem"
                or not isinstance(record["path"], str)
                or not Path(record["path"]).is_absolute()
                or not isinstance(record["sha256"], str)
                or not SHA256.fullmatch(record["sha256"])
            ):
                raise Refusal("invalid_manifest")
    if len(artifact_paths) != len(set(artifact_paths)):
        raise Refusal("invalid_manifest")

    try:
        current_boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
            encoding="ascii"
        ).strip()
    except (OSError, UnicodeError) as error:
        raise Refusal("owner_identity_unavailable") from error
    if owner["boot_id"] != current_boot_id:
        raise Refusal("owner_not_live")
    if process_start_ticks(owner["pid"]) != owner["start_ticks"]:
        raise Refusal("owner_not_live")
    if tree.resolve(strict=True) != tree:
        raise Refusal("symlink_escape")


def command_require_build_tree(
    args: argparse.Namespace, root: Path, tree: Path
) -> int:
    descriptor = lock_existing_root(root)
    try:
        reject_symlink_components(tree)
        try:
            mode = os.lstat(tree).st_mode
        except FileNotFoundError as error:
            raise Refusal("tree_missing") from error
        if stat.S_ISLNK(mode):
            raise Refusal("symlink_escape")
        if not stat.S_ISDIR(mode):
            raise Refusal("invalid_tree")
        manifest = load_build_manifest(tree)
        validate_build_manifest(manifest, args, tree)
        print(
            f"BUILD_TREE_OWNERSHIP producer={manifest['producer']} "
            f"device={args.device} bead={args.bead} state=running path={tree}"
        )
        return 0
    finally:
        os.close(descriptor)


def validate_caller_manifest(
    manifest: dict[str, Any], args: argparse.Namespace, root: Path, tree: Path
) -> None:
    if (
        set(manifest)
        != {
            "schema",
            "producer",
            "bead",
            "device",
            "root",
            "tree",
            "state",
            "owner_pid",
            "owner_boot_id",
            "owner_start_ticks",
            "created_utc",
        }
        or manifest.get("schema") != CALLER_SCHEMA
        or manifest.get("producer") != args.producer
        or manifest.get("device") != args.device
        or manifest.get("root") != str(root)
        or manifest.get("tree") != str(tree)
        or manifest.get("state") != "active"
        or not isinstance(manifest.get("bead"), str)
        or not TOKEN.fullmatch(manifest["bead"])
        or not isinstance(manifest.get("owner_pid"), int)
        or manifest["owner_pid"] <= 1
        or not isinstance(manifest.get("owner_boot_id"), str)
        or not BOOT_ID.fullmatch(manifest["owner_boot_id"])
        or not isinstance(manifest.get("owner_start_ticks"), int)
        or manifest["owner_start_ticks"] <= 0
        or not isinstance(manifest.get("created_utc"), str)
        or not manifest["created_utc"]
    ):
        raise Refusal("invalid_manifest")

    try:
        current_boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
            encoding="ascii"
        ).strip()
    except (OSError, UnicodeError) as error:
        raise Refusal("owner_identity_unavailable") from error
    if manifest["owner_boot_id"] != current_boot_id:
        raise Refusal("owner_not_live")
    if process_start_ticks(manifest["owner_pid"]) != manifest["owner_start_ticks"]:
        raise Refusal("owner_not_live")


def store_caller_manifest(tree: Path, manifest: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(tree / CALLER_MANIFEST, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def command_require_caller_temporary(
    args: argparse.Namespace, root: Path, tree: Path
) -> int:
    reject_symlink_components(tree)
    owner_pid, owner_boot_id, owner_start_ticks = parent_identity()
    descriptor = lock_existing_tree(tree)
    try:
        if tree.resolve(strict=True) != tree:
            raise Refusal("symlink_escape")
        entries = list(tree.iterdir())
        if entries:
            if tree / CALLER_MANIFEST not in entries:
                raise Refusal("caller_temporary_not_empty")
            manifest = load_caller_manifest(tree)
            validate_caller_manifest(manifest, args, root, tree)
            raise Refusal("caller_temporary_active")
        store_caller_manifest(
            tree,
            {
                "schema": CALLER_SCHEMA,
                "producer": args.producer,
                "bead": args.bead,
                "device": args.device,
                "root": str(root),
                "tree": str(tree),
                "state": "active",
                "owner_pid": owner_pid,
                "owner_boot_id": owner_boot_id,
                "owner_start_ticks": owner_start_ticks,
                "created_utc": now(),
            },
        )
        os.fsync(descriptor)
        print(
            f"CALLER_TEMP_BOUND producer={args.producer} device={args.device} "
            f"max_active=1 active=1 bead={args.bead} path={tree}"
        )
        return 0
    finally:
        os.close(descriptor)


def command_release_caller_temporary(
    args: argparse.Namespace, root: Path, tree: Path
) -> int:
    reject_symlink_components(tree)
    descriptor = lock_existing_tree(tree)
    try:
        if tree.resolve(strict=True) != tree:
            raise Refusal("symlink_escape")
        manifest = load_caller_manifest(tree)
        validate_caller_manifest(manifest, args, root, tree)
        owner_pid, owner_boot_id, owner_start_ticks = parent_identity()
        if (
            manifest["bead"] != args.bead
            or manifest["owner_pid"] != owner_pid
            or manifest["owner_boot_id"] != owner_boot_id
            or manifest["owner_start_ticks"] != owner_start_ticks
        ):
            raise Refusal("owner_identity_mismatch")
        os.unlink(tree / CALLER_MANIFEST)
        os.fsync(descriptor)
        print(
            f"CALLER_TEMP_RELEASE producer={args.producer} device={args.device} "
            f"max_active=1 active=0 bead={args.bead} path={tree}"
        )
        return 0
    finally:
        os.close(descriptor)


def validate_retained_manifest(
    manifest: dict[str, Any], args: argparse.Namespace, root: Path, tree: Path
) -> None:
    expected = {
        "schema": SCHEMA,
        "producer": args.producer,
        "device": args.device,
        "root": str(root),
        "tree": str(tree),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise Refusal("manifest_identity_mismatch")
    if (
        set(manifest)
        != {
            "schema",
            "producer",
            "bead",
            "device",
            "input_sha256",
            "root",
            "tree",
            "state",
            "owner_pid",
            "owner_boot_id",
            "owner_start_ticks",
            "created_utc",
            "updated_utc",
        }
        or not isinstance(manifest.get("bead"), str)
        or not TOKEN.fullmatch(manifest["bead"])
        or not isinstance(manifest.get("input_sha256"), str)
        or not SHA256.fullmatch(manifest["input_sha256"])
        or manifest.get("state") not in {"running", "success", "failed"}
        or not isinstance(manifest.get("owner_pid"), int)
        or manifest["owner_pid"] <= 1
        or not isinstance(manifest.get("owner_boot_id"), str)
        or not BOOT_ID.fullmatch(manifest["owner_boot_id"])
        or not isinstance(manifest.get("owner_start_ticks"), int)
        or manifest["owner_start_ticks"] <= 0
        or not isinstance(manifest.get("created_utc"), str)
        or not manifest["created_utc"]
        or not isinstance(manifest.get("updated_utc"), str)
        or not manifest["updated_utc"]
    ):
        raise Refusal("invalid_manifest")


def validate_finish_manifest(
    manifest: dict[str, Any], args: argparse.Namespace, root: Path, tree: Path
) -> None:
    validate_retained_manifest(manifest, args, root, tree)
    if (
        manifest["bead"] != args.bead
        or manifest["input_sha256"] != args.input_sha
    ):
        raise Refusal("manifest_identity_mismatch")
    owner_pid, owner_boot_id, owner_start_ticks = parent_identity()
    if (
        manifest["owner_pid"] != owner_pid
        or manifest["owner_boot_id"] != owner_boot_id
        or manifest["owner_start_ticks"] != owner_start_ticks
    ):
        raise Refusal("owner_identity_mismatch")


def store_manifest(tree: Path, manifest: dict[str, Any]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".pf-stage-tree.", dir=tree)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, tree / MANIFEST)
        temporary = ""
        directory = os.open(
            tree,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def command_start(args: argparse.Namespace, root: Path, tree: Path) -> int:
    owner_pid, owner_boot_id, owner_start_ticks = parent_identity()
    descriptor = lock_root(root)
    try:
        reject_symlink_components(tree)
        try:
            mode = os.lstat(tree).st_mode
        except FileNotFoundError:
            print_bound(args, 0)
            os.mkdir(tree, 0o700)
            timestamp = now()
            store_manifest(
                tree,
                {
                    "schema": SCHEMA,
                    "producer": args.producer,
                    "bead": args.bead,
                    "device": args.device,
                    "input_sha256": args.input_sha,
                    "root": str(root),
                    "tree": str(tree),
                    "state": "running",
                    "owner_pid": owner_pid,
                    "owner_boot_id": owner_boot_id,
                    "owner_start_ticks": owner_start_ticks,
                    "created_utc": timestamp,
                    "updated_utc": timestamp,
                },
            )
            return 0
        print_bound(args, 1)
        if stat.S_ISLNK(mode):
            raise Refusal("symlink_escape")
        if not stat.S_ISDIR(mode):
            raise Refusal("invalid_tree")
        manifest = load_manifest(tree)
        validate_retained_manifest(manifest, args, root, tree)
        raise Refusal("unconsumed_stage_tree")
    finally:
        os.close(descriptor)


def command_finish(args: argparse.Namespace, root: Path, tree: Path) -> int:
    descriptor = lock_root(root)
    try:
        reject_symlink_components(tree)
        try:
            mode = os.lstat(tree).st_mode
        except FileNotFoundError as error:
            raise Refusal("missing_tree") from error
        if stat.S_ISLNK(mode):
            raise Refusal("symlink_escape")
        if not stat.S_ISDIR(mode):
            raise Refusal("invalid_tree")
        manifest = load_manifest(tree)
        validate_finish_manifest(manifest, args, root, tree)
        if manifest["state"] != "running":
            raise Refusal("not_running")
        manifest["state"] = args.state
        manifest["updated_utc"] = now()
        store_manifest(tree, manifest)
        print(
            f"STAGE_TREE_STATUS producer={args.producer} device={args.device} "
            f"bead={args.bead} state={args.state} path={tree}"
        )
        return 0
    finally:
        os.close(descriptor)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "finish"):
        command = commands.add_parser(name)
        command.add_argument("--root", required=True)
        command.add_argument("--tree", required=True)
        command.add_argument("--producer", required=True)
        command.add_argument("--bead", required=True)
        command.add_argument("--device", required=True)
        command.add_argument("--input-sha", required=True)
        if name == "finish":
            command.add_argument("--state", required=True, choices=("success", "failed"))
    for name in (
        "require-build-tree",
        "require-caller-temporary",
        "release-caller-temporary",
    ):
        command = commands.add_parser(name)
        command.add_argument("--root", required=True)
        command.add_argument("--tree", required=True)
        command.add_argument("--producer", required=True)
        command.add_argument("--bead", required=True)
        command.add_argument("--device", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "require-build-tree":
            root, tree = validate_build_args(args)
            return command_require_build_tree(args, root, tree)
        if args.command == "require-caller-temporary":
            root, tree = validate_caller_temporary_args(args)
            return command_require_caller_temporary(args, root, tree)
        if args.command == "release-caller-temporary":
            root, tree = validate_caller_temporary_args(args)
            return command_release_caller_temporary(args, root, tree)
        root, tree = validate_args(args)
        if args.command == "start":
            return command_start(args, root, tree)
        return command_finish(args, root, tree)
    except Refusal as error:
        if args.command in {
            "require-build-tree",
            "require-caller-temporary",
            "release-caller-temporary",
        }:
            return refuse_build(args, Path(args.tree), error.reason)
        return refuse(args, Path(args.tree), error.reason)
    except (OSError, ValueError) as error:
        reason = f"io_error_{error.__class__.__name__}"
        if args.command in {
            "require-build-tree",
            "require-caller-temporary",
            "release-caller-temporary",
        }:
            return refuse_build(args, Path(args.tree), reason)
        return refuse(args, Path(args.tree), reason)


if __name__ == "__main__":
    raise SystemExit(main())
