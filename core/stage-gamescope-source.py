#!/usr/bin/env python3
"""Stage an exact, offline-admitted and materialized Gamescope source tree."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
MANIFEST_FIELDS = (
    "schema", "edge_id", "parent_id", "project_id", "path", "kind",
    "upstream_url", "upstream_revision", "declared_url", "locator_revision",
    "pf_url", "pf_revision", "tree_oid", "content_sha256", "license_path",
    "license_sha256", "selectors", "tests", "patch_status",
    "transform_receipt", "fork_history_proof", "fork_pin_ref",
)


class StageError(RuntimeError):
    pass


def run(*command: str, input_bytes: bytes | None = None,
        env: dict[str, str] | None = None) -> bytes:
    try:
        return subprocess.run(
            command, input=input_bytes, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=True, env=env,
        ).stdout
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode(errors="replace").strip()
        raise StageError(f"{' '.join(command)} failed: {detail}") from error


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StageError(f"invalid receipt {path}: {error}") from error
    if not isinstance(value, dict):
        raise StageError(f"receipt is not an object: {path}")
    return value


def verify_series(control: Path, args: argparse.Namespace) -> str:
    if run("git", "-C", str(control), "merge-base", "--is-ancestor",
           args.base, args.head) != b"":
        raise StageError("unexpected merge-base output")
    merges = run("git", "-C", str(control), "rev-list", "--merges",
                 f"{args.base}..{args.head}").decode().strip()
    if merges:
        raise StageError("Gamescope integration contains a merge commit")
    commits = run("git", "-C", str(control), "rev-list", "--reverse",
                  f"{args.base}..{args.head}").decode().splitlines()
    patch_ids = []
    for commit in commits:
        patch = run("git", "-C", str(control), "show", "--pretty=email",
                    "--patch", commit)
        patch_id = run("git", "patch-id", "--stable", input_bytes=patch).decode().split()[0]
        patch_ids.append(patch_id)
    if " ".join(patch_ids) != args.expected_patch_ids:
        raise StageError("Gamescope patch identities/order do not match the admitted series")
    stream = run("git", "-C", str(control), "format-patch", "--stdout",
                 "--no-stat", f"{args.base}..{args.head}")
    patch_digest = sha256_bytes(stream)
    if patch_digest != args.patch_series_sha256:
        raise StageError("Gamescope format-patch digest mismatch")
    if sha256_bytes((control / "LICENSE").read_bytes()) != args.license_sha256:
        raise StageError("Gamescope licence digest mismatch")
    return patch_digest


def parse_manifest(path: Path) -> tuple[list[dict[str, str]], bytes]:
    raw = path.read_bytes()
    lines = raw.decode("utf-8").splitlines()
    if not lines or lines[0] != "# gamescope-source-closure-v1":
        raise StageError("Gamescope dependency manifest schema marker mismatch")
    reader = csv.DictReader(io.StringIO("\n".join(lines[1:])), dialect="excel-tab")
    if tuple(reader.fieldnames or ()) != MANIFEST_FIELDS:
        raise StageError("Gamescope dependency manifest header mismatch")
    rows = list(reader)
    if len(rows) != 34:
        raise StageError("Gamescope dependency manifest edge count mismatch")
    return rows, raw


def export_licenses(rows: list[dict[str, str]], cache: Path, output: Path) -> int:
    licenses: dict[tuple[str, str], tuple[str, str]] = {}
    for row in rows:
        project = row["project_id"]
        revision = row["pf_revision"]
        license_path = row["license_path"]
        license_sha = row["license_sha256"]
        if (not re.fullmatch(r"[A-Za-z0-9._-]+", project) or
                HEX40.fullmatch(revision) is None or
                HEX64.fullmatch(license_sha) is None or
                license_path.startswith("/") or ".." in license_path.split("/")):
            raise StageError(f"unsafe dependency licence metadata: {project}")
        key = (project, revision)
        value = (license_path, license_sha)
        if key in licenses and licenses[key] != value:
            raise StageError(f"inconsistent dependency licence metadata: {project}")
        licenses[key] = value
    if len(licenses) != 32:
        raise StageError("Gamescope dependency project/pin count mismatch")
    bundle = output / ".pf-source-licenses"
    bundle.mkdir()
    for (project, revision), (license_path, license_sha) in sorted(licenses.items()):
        repo = cache / "repos" / f"{project}.git"
        data = run("git", f"--git-dir={repo}", "show", f"{revision}:{license_path}")
        if sha256_bytes(data) != license_sha:
            raise StageError(f"dependency licence digest mismatch: {project}")
        destination = bundle / f"{project}-{revision[:12]}-{Path(license_path).name}"
        destination.write_bytes(data)
        destination.chmod(0o644)
    return len(licenses)


def stage(args: argparse.Namespace) -> None:
    if args.output.exists():
        raise StageError(f"Gamescope output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    control = Path(tempfile.mkdtemp(prefix=".gamescope-control.", dir=args.output.parent))
    receipt_path = control.parent / f".{args.output.name}.materialization.json"
    try:
        run("git", "clone", "--shared", "--no-checkout", "--quiet",
            str(args.git_dir), str(control))
        run("git", "-C", str(control), "checkout", "--detach", "--quiet", args.head)
        if run("git", "-C", str(control), "rev-parse", "HEAD").decode().strip() != args.head:
            raise StageError("Gamescope control checkout head mismatch")
        patch_digest = verify_series(control, args)
        manifest = control / ".github" / "pocketforge-source-closure.tsv"
        rows, raw_manifest = parse_manifest(manifest)
        if sha256_bytes(raw_manifest) != args.manifest_sha256:
            raise StageError("Gamescope dependency manifest digest mismatch")

        primer = control / ".github" / "scripts" / "prime-meson-sources.sh"
        materializer = control / ".github" / "scripts" / "materialize-source-closure.py"
        if not primer.is_file() or not materializer.is_file():
            raise StageError("tsp-op5a.440.7 admission/materialization path is missing")
        environment = os.environ.copy()
        environment["PF_MESON_CACHE_OFFLINE"] = "1"
        environment["MESON_SOURCE_CACHE_ROOT"] = str(args.cache_root)
        run(str(primer), "--offline", env=environment)
        cache = args.cache_root / args.manifest_sha256
        admission_path = cache / "admission-receipt.json"
        admission = load_json(admission_path)
        if (admission.get("schema") != "gamescope-source-admission-v1" or
                admission.get("gamescope_head") != args.head or
                admission.get("manifest_sha256") != args.manifest_sha256 or
                admission.get("validated_edges") != 34 or
                admission.get("verified_project_pins") != 32):
            raise StageError("Gamescope admission receipt mismatch")

        run("python3", str(materializer), "--repo-root", str(control),
            "--manifest", str(manifest), "--vendored-registry",
            str(control / ".github" / "vendored-sources.tsv"),
            "--cache-root", str(cache), "--output", str(args.output),
            "--receipt", str(receipt_path))
        materialization = load_json(receipt_path)
        expected_materialization = {
            "schema": "gamescope-source-materialization-v1",
            "gamescope_head": args.head,
            "manifest_sha256": args.manifest_sha256,
            "materialized_git_inputs": 31,
            "generated_root_wrap_aliases": 2,
            "verified_materialized_locator_targets": 33,
        }
        for key, value in expected_materialization.items():
            if materialization.get(key) != value:
                raise StageError(f"Gamescope materialization {key} mismatch")
        source_tree_sha = materialization.get("source_tree_sha256")
        if not isinstance(source_tree_sha, str) or HEX64.fullmatch(source_tree_sha) is None:
            raise StageError("Gamescope materialization source-tree digest is invalid")

        export_licenses(rows, cache, args.output)
        admission_bytes = admission_path.read_bytes()
        materialization_bytes = receipt_path.read_bytes()
        (args.output / ".pf-gamescope-admission.json").write_bytes(admission_bytes)
        (args.output / ".pf-gamescope-materialization.json").write_bytes(materialization_bytes)
        source_receipt = {
            "schema": "pocketforge.gamescope-source/v1",
            "source_url": "https://github.com/pocketforge-os/gamescope.git",
            "upstream_base": args.base,
            "integrated_head": args.head,
            "patch_series_sha256": patch_digest,
            "dependency_manifest_sha256": args.manifest_sha256,
            "admission_receipt_sha256": sha256_bytes(admission_bytes),
            "materialization_receipt_sha256": sha256_bytes(materialization_bytes),
            "source_tree_sha256": source_tree_sha,
            "required_heads": {
                "present": args.present_head,
                "staging": args.staging_head,
                "rotation": args.rotation_head,
            },
        }
        (args.output / ".pf-gamescope-source.json").write_text(
            json.dumps(source_receipt, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        if receipt_path.exists():
            receipt_path.unlink()
        shutil.rmtree(control)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--git-dir", type=Path, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--present-head", required=True)
    parser.add_argument("--staging-head", required=True)
    parser.add_argument("--rotation-head", required=True)
    parser.add_argument("--expected-patch-ids", required=True)
    parser.add_argument("--patch-series-sha256", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--license-sha256", required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for name in ("head", "base", "present_head", "staging_head", "rotation_head"):
        if HEX40.fullmatch(getattr(args, name)) is None:
            parser.error(f"--{name.replace('_', '-')} must be a lowercase SHA-1")
    for name in ("patch_series_sha256", "manifest_sha256", "license_sha256"):
        if HEX64.fullmatch(getattr(args, name)) is None:
            parser.error(f"--{name.replace('_', '-')} must be a lowercase SHA-256")
    return args


def main() -> int:
    try:
        stage(parse_args())
    except (OSError, StageError, UnicodeError) as error:
        print(f"stage-gamescope-source: {error}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
