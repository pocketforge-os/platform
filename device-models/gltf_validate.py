#!/usr/bin/env python3
"""Run the pinned Khronos glTF-Validator over the committed device glbs.

    python3 device-models/gltf_validate.py --fetch "$dir"          # CI
    python3 device-models/gltf_validate.py --validator /path/gltf_validator

``--fetch DIR`` downloads the pinned release tarball into DIR (unless a binary
with the pinned sha256 is already there), checks the archive and the extracted
binary against their pinned sha256 and validates with it. The binary is 6.7 MB,
so it is fetched, not vendored. With no glb arguments every
``skins/*/model.glb`` is validated; zero discovered glbs is a failure.

A glb passes when the validator exits 0 and its JSON report has no errors and
no warnings (infos and hints are printed but allowed).
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.0.0-dev.3.10"
ARCHIVE = f"gltf_validator-{VERSION}-linux64.tar.xz"
URL = (
    "https://github.com/KhronosGroup/glTF-Validator/releases/download/"
    f"{VERSION}/{ARCHIVE}"
)
ARCHIVE_SHA256 = "168eba887964125abe17ae97899b38d0b3cfd73c266c78424c194929ddcbc522"
BINARY_SHA256 = "5cba1e097935c9efd929d24a49610824259b030f0ae45672273bfbcbb5b87a62"
BINARY = "gltf_validator"


class ValidatorError(Exception):
    """The pinned validator could not be obtained or run."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: Path) -> None:
    actual = sha256_file(path)
    if actual != ARCHIVE_SHA256:
        raise ValidatorError(
            f"{path}: sha256 {actual} != pinned {ARCHIVE_SHA256} ({ARCHIVE})"
        )


def fetch(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / BINARY
    if binary.is_file() and sha256_file(binary) == BINARY_SHA256:
        return binary
    archive = directory / ARCHIVE
    if not archive.is_file():
        print(f"fetching {URL}", file=sys.stderr)
        partial = directory / (ARCHIVE + ".part")
        with urllib.request.urlopen(URL, timeout=120) as response, \
                partial.open("wb") as stream:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                stream.write(chunk)
        os.replace(partial, archive)
    verify_archive(archive)
    with tarfile.open(archive, "r:xz") as tar:
        member = tar.getmember(BINARY)
        if not member.isfile():
            raise ValidatorError(f"{ARCHIVE}: {BINARY} is not a regular file")
        source = tar.extractfile(member)
        partial = directory / (BINARY + ".part")
        partial.write_bytes(source.read())
    if sha256_file(partial) != BINARY_SHA256:
        partial.unlink()
        raise ValidatorError(f"{BINARY} sha256 != pinned {BINARY_SHA256}")
    partial.chmod(0o755)
    os.replace(partial, binary)
    return binary


def validate(validator: Path, glb: Path) -> tuple[bool, str]:
    """Return (passed, one-line summary + issue messages) for one glb."""
    if not validator.is_file():
        raise ValidatorError(f"validator binary not found: {validator}")
    result = subprocess.run(
        [str(validator), "--stdout", "--validate-resources", str(glb)],
        capture_output=True, text=True, check=False, timeout=300,
    )
    try:
        report = json.loads(result.stdout)
        issues = report["issues"]
        errors, warnings = issues["numErrors"], issues["numWarnings"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return False, (f"{glb}: validator exit={result.returncode}, no JSON report; "
                       f"stderr: {result.stderr.strip()[:2000]}")
    lines = [
        f"{glb}: exit={result.returncode} errors={errors} warnings={warnings} "
        f"infos={issues.get('numInfos')} hints={issues.get('numHints')}"
    ]
    for message in issues.get("messages", [])[:50]:
        lines.append(
            f"  [{message.get('severity')}] {message.get('code')} "
            f"{message.get('pointer', '')}: {message.get('message')}"
        )
    passed = result.returncode == 0 and errors == 0 and warnings == 0
    return passed, "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--validator", type=Path, help="pinned gltf_validator binary")
    source.add_argument("--fetch", type=Path, metavar="DIR",
                        help="download/verify the pinned binary into DIR")
    parser.add_argument("--print-path", action="store_true",
                        help="only fetch/verify and print the binary path")
    parser.add_argument("glb", nargs="*", type=Path)
    args = parser.parse_args(argv)
    try:
        validator = fetch(args.fetch) if args.fetch else args.validator
        if args.print_path:
            print(validator)
            return 0
        if args.validator and sha256_file(validator) != BINARY_SHA256:
            raise ValidatorError(f"{validator}: sha256 != pinned {BINARY_SHA256}")
        glbs = args.glb or sorted((ROOT / "skins").glob("*/model.glb"))
        if not glbs:
            print("gltf_validate=fail: no skins/*/model.glb found", file=sys.stderr)
            return 1
        failed = 0
        for glb in glbs:
            passed, text = validate(validator, glb)
            print(text)
            failed += not passed
    except ValidatorError as error:
        print(f"gltf_validate=fail: {error}", file=sys.stderr)
        return 1
    if failed:
        print(f"gltf_validate=fail failed={failed} of {len(glbs)}", file=sys.stderr)
        return 1
    print(f"gltf_validate=pass glbs={len(glbs)} validator={VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
