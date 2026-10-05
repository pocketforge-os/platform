#!/usr/bin/env python3
"""Create the reproducible, symlink-free Gamescope source publication."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tarfile
import tempfile


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_tree(src: Path, dst: Path) -> None:
    """Copy while resolving only in-tree symlinks; reject escapes and specials."""
    src = src.resolve()
    for item in sorted(src.rglob("*"), key=lambda p: p.relative_to(src).as_posix()):
        rel = item.relative_to(src)
        out = dst / rel
        if item.is_symlink():
            target = item.resolve()
            try:
                target.relative_to(src)
            except ValueError as exc:
                raise ValueError(f"symlink escapes Gamescope tree: {rel}") from exc
            if target.is_dir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            if not target.is_file():
                raise ValueError(f"symlink target is not a regular file: {rel}")
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, out)
            out.chmod(stat.S_IMODE(target.stat().st_mode) & 0o755)
        elif item.is_dir():
            out.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, out)
            out.chmod(stat.S_IMODE(item.stat().st_mode) & 0o755)
        else:
            raise ValueError(f"unsupported file type: {rel}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--patch-series-sha256", required=True)
    ap.add_argument("--manifest-sha256", required=True)
    ap.add_argument("--lock-sha256", required=True)
    args = ap.parse_args()
    source = args.source
    if not source.is_dir() or source.is_symlink():
        raise SystemExit(f"source is not a directory: {source}")
    args.store.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gamescope-normalized-", dir=source.parent) as td:
        normalized = Path(td) / "tree"
        normalized.mkdir()
        copy_tree(source, normalized)
        manifest_lines = []
        entries = sorted(normalized.rglob("*"), key=lambda p: p.relative_to(normalized).as_posix())
        for item in entries:
            rel = item.relative_to(normalized).as_posix()
            if item.is_dir():
                mode = 0o755
                item.chmod(mode)
            else:
                mode = stat.S_IMODE(item.stat().st_mode)
                mode = 0o755 if mode & 0o111 else 0o644
                item.chmod(mode)
            os.utime(item, (0, 0), follow_symlinks=False)
            if item.is_file():
                manifest_lines.append(f"{rel}\t{mode:04o}\t{digest(item)}\n")
        file_manifest = "".join(manifest_lines).encode()
        file_manifest_sha = hashlib.sha256(file_manifest).hexdigest()
        manifest_path = normalized / ".pf-gamescope-files.sha256"
        manifest_path.write_bytes(file_manifest)
        manifest_path.chmod(0o644)
        os.utime(manifest_path, (0, 0))
        archive_tmp = Path(td) / "gamescope.tar"
        with tarfile.open(archive_tmp, "w", format=tarfile.USTAR_FORMAT) as tar:
            for item in [normalized] + entries + [manifest_path]:
                rel = item.relative_to(normalized).as_posix() if item != normalized else "gamescope"
                info = tar.gettarinfo(str(item), arcname=("gamescope" if item == normalized else f"gamescope/{rel}"))
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                if item.is_file():
                    with item.open("rb") as stream:
                        tar.addfile(info, stream)
                else:
                    tar.addfile(info)
        archive_sha = digest(archive_tmp)
        final = args.store / f"gamescope-{archive_sha}.tar"
        if final.exists() and digest(final) != archive_sha:
            raise SystemExit(f"content-addressed archive collision: {final}")
        if not final.exists():
            shutil.copyfile(archive_tmp, final)
            final.chmod(0o644)
        receipt = {
            "schema": "pocketforge.gamescope-deterministic-publication/v1",
            "source_url": args.source_url, "integrated_head": args.head,
            "upstream_base": args.base, "patch_series_sha256": args.patch_series_sha256,
            "dependency_manifest_sha256": args.manifest_sha256,
            "platform_lock_sha256": args.lock_sha256,
            "file_manifest_sha256": file_manifest_sha,
            "archive_sha256": archive_sha,
            "archive": str(final), "files": len(manifest_lines),
        }
        # Replace the staged tree atomically after all validation and publication.
        backup = Path(td) / "original"
        source.rename(backup)
        normalized.rename(source)
        (source / ".pf-gamescope-deterministic.json").write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
        (source / ".pf-gamescope-deterministic.json").chmod(0o644)
        os.utime(source / ".pf-gamescope-deterministic.json", (0, 0))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"gamescope-deterministic-archive: {exc}")
