#!/usr/bin/env python3
"""Export and verify the device fixture dependency boundary.

The snapshot is the cross-repository handoff consumed by holder tooling.  Its
source revision is the newest first-parent commit that changed a fixture
contract or its schema, not the current visual-model HEAD.  Visual-only commits
therefore cannot churn holder dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

import validate_fixture_contracts as fixture


SNAPSHOT_SCHEMA = "pocketforge-fixture-dependency-snapshot-v1"
SOURCE_REPOSITORY = "https://github.com/pocketforge-os/platform.git"
CONTRACT_SCHEMA_PATH = "schemas/device-fixture-contract.schema.json"
CONTRACT_PATHSPEC = ":(glob)device-models/*/fixture-contract.json"
REVISION_PATHS = (CONTRACT_PATHSPEC, CONTRACT_SCHEMA_PATH)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_REV_RE = re.compile(r"^[0-9a-f]{40}$")


class SnapshotError(ValueError):
    """A deterministic fixture snapshot failure."""


def _git(root: Path, *arguments: str, text: bool = True) -> str | bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            stderr = exc.stderr
            if isinstance(stderr, bytes):
                detail = stderr.decode("utf-8", errors="replace").strip()
            elif isinstance(stderr, str):
                detail = stderr.strip()
        suffix = f": {detail}" if detail else ""
        raise SnapshotError(f"git {' '.join(arguments)} failed{suffix}") from exc
    return completed.stdout


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise SnapshotError(f"path escapes source root: {path}") from exc


def _keys(
    value: Mapping[str, Any],
    path: str,
    expected: set[str],
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        raise SnapshotError(
            f"{path}: missing required field(s): {', '.join(missing)}"
        )
    if extra:
        raise SnapshotError(
            f"{path}: unknown field(s): {', '.join(extra)}"
        )


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SnapshotError(f"{path}: must be an object")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SnapshotError(f"{path}: must be an array")
    return value


def _string(
    value: Any,
    path: str,
    *,
    pattern: re.Pattern[str] | None = None,
) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotError(f"{path}: must be a non-empty string")
    if pattern is not None and not pattern.fullmatch(value):
        raise SnapshotError(f"{path}: has invalid format: {value!r}")
    return value


def _positive_integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise SnapshotError(f"{path}: must be a positive integer")
    if isinstance(value, Decimal) and not value.is_finite():
        raise SnapshotError(f"{path}: must be a positive integer")
    integer = int(value)
    if value != integer or integer < 1:
        raise SnapshotError(f"{path}: must be a positive integer")
    return integer


def source_revision(root: Path) -> str:
    """Return the protected-history revision owning current contract state."""

    root = root.resolve()
    status = _git(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
    )
    assert isinstance(status, str)
    if status:
        raise SnapshotError("fixture snapshot requires a clean source tree")
    revision = _git(
        root,
        "log",
        "--first-parent",
        "-1",
        "--format=%H",
        "HEAD",
        "--",
        *REVISION_PATHS,
    )
    assert isinstance(revision, str)
    revision = revision.strip()
    if not GIT_REV_RE.fullmatch(revision):
        raise SnapshotError("fixture dependency source revision is unavailable")
    ancestor = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", revision, "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if ancestor.returncode != 0:
        raise SnapshotError("fixture dependency revision is not an ancestor of HEAD")
    return revision


def _blob_at_revision(root: Path, revision: str, path: str) -> bytes:
    value = _git(root, "show", f"{revision}:{path}", text=False)
    assert isinstance(value, bytes)
    return value


def _canonical_bytes(value: Any) -> bytes:
    normalized = fixture._normalize_semantic_lists(value)
    return (fixture._canonical_json(normalized) + "\n").encode("utf-8")


def build_snapshot(root: Path) -> dict[str, Any]:
    root = root.resolve()
    revision = source_revision(root)
    repository = fixture.ContractRepository(root)
    resolved = repository.validate_all()

    contracts: list[dict[str, Any]] = []
    interfaces: dict[str, dict[str, Any]] = {}
    for contract in resolved:
        relative = _relative(contract.path, root)
        raw = contract.path.read_bytes()
        if _blob_at_revision(root, revision, relative) != raw:
            raise SnapshotError(
                f"{relative}: bytes differ from dependency revision {revision}"
            )
        slug = contract.document["device"]["slug"]
        contracts.append(
            {
                "device_slug": slug,
                "kind": contract.document["kind"],
                "path": relative,
                "raw_sha256": _sha256(raw),
                "resolved_interface_sha256": contract.interface_hash,
            }
        )
        interface_document = contract.interface_document
        candidate = {
            "sha256": contract.interface_hash,
            "schema_version": interface_document["schema_version"],
            "interface_revision": contract.interface_revision,
            "coordinate_system": interface_document["coordinate_system"],
            "fixture_interface": interface_document["fixture_interface"],
        }
        prior = interfaces.get(contract.interface_hash)
        if prior is not None and _canonical_bytes(prior) != _canonical_bytes(
            candidate
        ):
            raise SnapshotError(
                f"resolved interface {contract.interface_hash} has mixed payloads"
            )
        interfaces[contract.interface_hash] = candidate

    contracts.sort(key=lambda item: item["device_slug"])
    schema_path = root / CONTRACT_SCHEMA_PATH
    schema_bytes = schema_path.read_bytes()
    if _blob_at_revision(root, revision, CONTRACT_SCHEMA_PATH) != schema_bytes:
        raise SnapshotError(
            f"{CONTRACT_SCHEMA_PATH}: bytes differ from dependency revision "
            f"{revision}"
        )
    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "canonicalization": fixture.CANONICALIZATION,
        "source": {
            "repository": SOURCE_REPOSITORY,
            "revision": revision,
        },
        "contract_schema": {
            "path": CONTRACT_SCHEMA_PATH,
            "raw_sha256": _sha256(schema_bytes),
        },
        "contracts": contracts,
        "interfaces": [
            interfaces[digest] for digest in sorted(interfaces)
        ],
    }
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(value: Any) -> Mapping[str, Any]:
    document = _object(value, "snapshot")
    _keys(
        document,
        "snapshot",
        {
            "schema",
            "canonicalization",
            "source",
            "contract_schema",
            "contracts",
            "interfaces",
        },
    )
    if document["schema"] != SNAPSHOT_SCHEMA:
        raise SnapshotError(f"snapshot.schema: must be {SNAPSHOT_SCHEMA!r}")
    if document["canonicalization"] != fixture.CANONICALIZATION:
        raise SnapshotError(
            "snapshot.canonicalization: unsupported canonicalization"
        )

    source = _object(document["source"], "snapshot.source")
    _keys(source, "snapshot.source", {"repository", "revision"})
    if source["repository"] != SOURCE_REPOSITORY:
        raise SnapshotError(
            f"snapshot.source.repository: must be {SOURCE_REPOSITORY!r}"
        )
    _string(
        source["revision"],
        "snapshot.source.revision",
        pattern=GIT_REV_RE,
    )

    schema = _object(document["contract_schema"], "snapshot.contract_schema")
    _keys(schema, "snapshot.contract_schema", {"path", "raw_sha256"})
    if schema["path"] != CONTRACT_SCHEMA_PATH:
        raise SnapshotError(
            f"snapshot.contract_schema.path: must be {CONTRACT_SCHEMA_PATH!r}"
        )
    _string(
        schema["raw_sha256"],
        "snapshot.contract_schema.raw_sha256",
        pattern=SHA256_RE,
    )

    interfaces = _array(document["interfaces"], "snapshot.interfaces")
    if not interfaces:
        raise SnapshotError("snapshot.interfaces: must not be empty")
    interface_hashes: list[str] = []
    for index, raw_interface in enumerate(interfaces):
        path = f"snapshot.interfaces[{index}]"
        interface = _object(raw_interface, path)
        _keys(
            interface,
            path,
            {
                "sha256",
                "schema_version",
                "interface_revision",
                "coordinate_system",
                "fixture_interface",
            },
        )
        digest = _string(
            interface["sha256"],
            f"{path}.sha256",
            pattern=SHA256_RE,
        )
        schema_version = _positive_integer(
            interface["schema_version"], f"{path}.schema_version"
        )
        if schema_version != fixture.SCHEMA_VERSION:
            raise SnapshotError(
                f"{path}.schema_version: unsupported version; "
                f"expected {fixture.SCHEMA_VERSION}"
            )
        _positive_integer(
            interface["interface_revision"], f"{path}.interface_revision"
        )
        try:
            fixture._validate_coordinate_system(
                interface["coordinate_system"],
                f"{path}.coordinate_system",
            )
            fixture._validate_fixture_interface(
                interface["fixture_interface"],
                f"{path}.fixture_interface",
            )
        except fixture.ContractError as exc:
            raise SnapshotError(str(exc)) from exc
        synthetic = {
            "kind": "fixture_interface",
            "schema_version": schema_version,
            "coordinate_system": interface["coordinate_system"],
            "fixture_interface": interface["fixture_interface"],
        }
        actual = fixture.interface_hash(synthetic)
        if actual != digest:
            raise SnapshotError(
                f"{path}.sha256: stale interface hash {digest}, computed {actual}"
            )
        interface_hashes.append(digest)
    if interface_hashes != sorted(set(interface_hashes)):
        raise SnapshotError(
            "snapshot.interfaces: hashes must be unique and sorted"
        )

    contracts = _array(document["contracts"], "snapshot.contracts")
    if not contracts:
        raise SnapshotError("snapshot.contracts: must not be empty")
    slugs: list[str] = []
    for index, raw_contract in enumerate(contracts):
        path = f"snapshot.contracts[{index}]"
        contract = _object(raw_contract, path)
        _keys(
            contract,
            path,
            {
                "device_slug",
                "kind",
                "path",
                "raw_sha256",
                "resolved_interface_sha256",
            },
        )
        slug = _string(
            contract["device_slug"],
            f"{path}.device_slug",
            pattern=fixture.SLUG_RE,
        )
        kind = _string(contract["kind"], f"{path}.kind")
        if kind not in {
            "fixture_interface",
            "shared_chassis_alias",
        }:
            raise SnapshotError(f"{path}.kind: unsupported contract kind")
        expected_path = f"device-models/{slug}/fixture-contract.json"
        if contract["path"] != expected_path:
            raise SnapshotError(f"{path}.path: must be {expected_path!r}")
        _string(
            contract["raw_sha256"],
            f"{path}.raw_sha256",
            pattern=SHA256_RE,
        )
        resolved_hash = _string(
            contract["resolved_interface_sha256"],
            f"{path}.resolved_interface_sha256",
            pattern=SHA256_RE,
        )
        if resolved_hash not in interface_hashes:
            raise SnapshotError(
                f"{path}.resolved_interface_sha256: unknown interface"
            )
        slugs.append(slug)
    if slugs != sorted(set(slugs)):
        raise SnapshotError(
            "snapshot.contracts: device slugs must be unique and sorted"
        )
    return document


def verify_snapshot(root: Path, path: Path) -> Mapping[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SnapshotError(f"cannot read snapshot {path}: {exc}") from exc
    document = validate_snapshot(fixture.load_json(path))
    if raw != _canonical_bytes(document):
        raise SnapshotError("snapshot bytes are not canonical")
    expected = build_snapshot(root)
    if _canonical_bytes(document) != _canonical_bytes(expected):
        raise SnapshotError("snapshot does not match source contract state")
    return document


def write_snapshot(
    snapshot: Mapping[str, Any],
    output: Path | None,
    source_root: Path,
) -> None:
    payload = _canonical_bytes(snapshot)
    if output is None:
        sys.stdout.buffer.write(payload)
        return
    output = output.expanduser().resolve()
    root = source_root.expanduser().resolve()
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise SnapshotError(
            "generated snapshot output must remain outside the repository"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output.parent,
            prefix=f".{output.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--root", type=Path, default=default_root)
    export_parser.add_argument("--output", type=Path)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, default=default_root)
    verify_parser.add_argument("--snapshot", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            snapshot = build_snapshot(args.root)
            write_snapshot(snapshot, args.output, args.root)
            if args.output is not None:
                print(
                    "fixture_snapshot_export=pass "
                    f"revision={snapshot['source']['revision']} "
                    f"contracts={len(snapshot['contracts'])} "
                    f"interfaces={len(snapshot['interfaces'])} "
                    f"output={args.output}"
                )
        elif args.command == "verify":
            snapshot = verify_snapshot(args.root, args.snapshot)
            print(
                "fixture_snapshot_verify=pass "
                f"revision={snapshot['source']['revision']} "
                f"contracts={len(snapshot['contracts'])} "
                f"interfaces={len(snapshot['interfaces'])} "
                f"snapshot={args.snapshot}"
            )
        else:  # pragma: no cover
            raise SnapshotError(f"unsupported command: {args.command}")
    except (SnapshotError, fixture.ContractError, OSError) as exc:
        print(f"fixture_snapshot_error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
