#!/usr/bin/env python3
"""Validate a PocketForge-style semantic OpenSCAD device-model package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib


REQUIRED_FILES = ("README.md", "render.py", "compare.py")
REQUIRED_VIEWS = ("front", "rear", "top", "bottom", "left", "right")
PRIVATE_IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".heic",
    ".heif",
    ".dng",
    ".tif",
    ".tiff",
}
PNG_PIXEL_CHUNKS = {b"IHDR", b"PLTE", b"IDAT", b"tRNS", b"IEND"}


class ValidationError(RuntimeError):
    """A concise user-facing validation failure."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "model_dir",
        type=Path,
        help="device-models/<slug> package directory",
    )
    parser.add_argument(
        "--photos",
        type=Path,
        help="external private-reference directory for compare.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="retain evidence here; must be absent or empty (default: temporary)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="compile, hard-warning CSG, and one six-view render only",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print the final result as JSON",
    )
    return parser.parse_args()


def run(command: list[str], cwd: Path) -> str:
    process = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        rendered = " ".join(command)
        output = process.stdout.strip()
        raise ValidationError(
            f"command failed ({process.returncode}): {rendered}"
            + (f"\n{output}" if output else "")
        )
    return process.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compile_source(path: Path) -> None:
    try:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    except (OSError, SyntaxError) as error:
        raise ValidationError(f"Python compile failed: {path}: {error}") from error


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def inspect_package(model_dir: Path) -> dict[str, Path]:
    if not model_dir.is_dir():
        raise ValidationError(f"model directory not found: {model_dir}")

    paths = {name: model_dir / name for name in REQUIRED_FILES}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise ValidationError("missing package files: " + ", ".join(missing))

    scad_files = sorted(model_dir.glob("*.scad"))
    if len(scad_files) != 1:
        raise ValidationError(
            f"expected exactly one top-level .scad file, found {len(scad_files)}"
        )
    paths["scad"] = scad_files[0]

    private_images = sorted(
        path
        for path in model_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in PRIVATE_IMAGE_SUFFIXES
    )
    if private_images:
        rendered = ", ".join(str(path.relative_to(model_dir)) for path in private_images)
        raise ValidationError(f"private/reference image candidates inside package: {rendered}")

    readme = paths["README.md"].read_text(encoding="utf-8").lower()
    for phrase in ("measurement", "provenance", "semantic", "known limit"):
        if phrase not in readme:
            raise ValidationError(f"README is missing expected section/content: {phrase}")

    compile_source(paths["render.py"])
    compile_source(paths["compare.py"])
    return paths


def render_csg(paths: dict[str, Path], output_root: Path, repo_root: Path) -> int:
    openscad = shutil.which("openscad")
    if openscad is None:
        raise ValidationError("OpenSCAD CLI not found")
    output = (output_root / "assembly.csg").resolve()
    run(
        [
            openscad,
            "--hardwarnings",
            "-o",
            str(output),
            str(paths["scad"].resolve()),
        ],
        repo_root,
    )
    size = output.stat().st_size
    if size == 0:
        raise ValidationError("assembly CSG is empty")
    return size


def render_views(
    renderer: Path,
    output: Path,
    repo_root: Path,
) -> dict[str, str]:
    run(
        [sys.executable, str(renderer), "--views", str(output)],
        repo_root,
    )
    hashes: dict[str, str] = {}
    for name in REQUIRED_VIEWS:
        image = output / f"{name}.png"
        if not image.is_file() or image.stat().st_size == 0:
            raise ValidationError(f"missing or empty evidence view: {image}")
        hashes[name] = sha256(image)
    return hashes


def load_renderer(renderer: Path) -> dict:
    try:
        return runpy.run_path(
            str(renderer),
            run_name="device_model_validation",
        )
    except Exception as error:
        raise ValidationError(f"could not load renderer contract: {error}") from error


def descriptor_part_ids(namespace: dict) -> set[str] | None:
    descriptor = namespace.get("DESCRIPTOR")
    if descriptor is None:
        return None
    descriptor_path = Path(descriptor)
    if not descriptor_path.is_file():
        raise ValidationError(f"renderer descriptor does not exist: {descriptor_path}")
    data = tomllib.loads(descriptor_path.read_text(encoding="utf-8"))
    try:
        return set(data["skin"]["parts"])
    except (KeyError, TypeError) as error:
        raise ValidationError(
            f"descriptor lacks [skin.parts]: {descriptor_path}"
        ) from error


def validate_semantics(
    namespace: dict,
    paths: dict[str, Path],
    output_root: Path,
    repo_root: Path,
) -> dict:
    control_ids = tuple(namespace.get("CONTROL_IDS", ()))
    render_skin_set = namespace.get("render_skin_set")
    if not control_ids or not callable(render_skin_set):
        raise ValidationError("renderer must expose CONTROL_IDS and render_skin_set()")

    controls_dir = output_root / "controls"
    controls_dir.mkdir()
    openscad = shutil.which("openscad")
    assert openscad is not None
    for control_id in control_ids:
        output = (controls_dir / f"{control_id}.csg").resolve()
        run(
            [
                openscad,
                "--hardwarnings",
                "-D",
                'PART="control"',
                "-D",
                f'CONTROL_ID="{control_id}"',
                "-o",
                str(output),
                str(paths["scad"].resolve()),
            ],
            repo_root,
        )
        if output.stat().st_size == 0:
            raise ValidationError(f"empty standalone semantic control: {control_id}")

    semantic_dir = output_root / "semantic"
    semantic_dir.mkdir()
    try:
        _, _, metadata = render_skin_set(semantic_dir)
    except Exception as error:
        raise ValidationError(f"semantic render failed: {error}") from error

    controls = metadata.get("controls", {})
    if set(controls) != set(control_ids):
        raise ValidationError(
            "semantic controls differ from CONTROL_IDS: "
            f"rendered={sorted(controls)} declared={sorted(control_ids)}"
        )

    overlap_fn = namespace.get("rectangle_overlaps")
    if callable(overlap_fn):
        overlaps = overlap_fn(controls)
        if overlaps:
            raise ValidationError(f"semantic rectangles overlap: {overlaps}")

    descriptor_ids = descriptor_part_ids(namespace)
    if descriptor_ids is not None and descriptor_ids != set(control_ids):
        raise ValidationError(
            "descriptor drawable IDs differ from CONTROL_IDS: "
            f"descriptor={sorted(descriptor_ids)} renderer={sorted(control_ids)}"
        )

    atlas_mode = metadata.get("atlas_composition", "")
    if "pairwise-disjoint" not in atlas_mode:
        raise ValidationError(f"unexpected atlas composition: {atlas_mode!r}")

    return {
        "controls": len(control_ids),
        "display_rect": metadata.get("display_rect"),
        "atlas_composition": atlas_mode,
    }


def png_chunk_types(path: Path) -> set[bytes]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValidationError(f"not a PNG: {path}")
    offset = 8
    chunks: set[bytes] = set()
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValidationError(f"truncated PNG chunks: {path}")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        chunks.add(kind)
        offset += length + 12
    return chunks


def validate_comparison(
    compare_tool: Path,
    photos: Path,
    views: Path,
    output_root: Path,
    repo_root: Path,
) -> dict:
    if not photos.is_dir():
        raise ValidationError(f"photo directory not found: {photos}")
    if is_within(photos, repo_root):
        raise ValidationError("private photo directory must remain outside the repository")

    output = output_root / "comparison"
    run(
        [
            sys.executable,
            str(compare_tool),
            "--photos",
            str(photos),
            "--views",
            str(views),
            "--output",
            str(output),
        ],
        repo_root,
    )
    images = sorted(output.glob("*.png"))
    if not images:
        raise ValidationError("comparison tool produced no PNG evidence")
    for image in images:
        unexpected = png_chunk_types(image) - PNG_PIXEL_CHUNKS
        if unexpected:
            decoded = ", ".join(
                chunk.decode("latin-1", errors="replace")
                for chunk in sorted(unexpected)
            )
            raise ValidationError(
                f"comparison PNG carries ancillary metadata chunks: {image}: {decoded}"
            )
    return {
        "images": len(images),
        "metadata_chunks": 0,
    }


def prepare_output(path: Path | None) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    if path is None:
        temporary = tempfile.TemporaryDirectory(prefix="device-model-validation-")
        return Path(temporary.name), temporary
    output = path.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValidationError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    return output, None


def validate(args: argparse.Namespace) -> dict:
    model_dir = args.model_dir.resolve()
    paths = inspect_package(model_dir)
    repo_root = model_dir.parent.parent
    if not (repo_root / "device-models").is_dir():
        raise ValidationError(
            f"expected model directory under <repo>/device-models: {model_dir}"
        )

    output_root, temporary = prepare_output(args.output)
    try:
        result: dict = {
            "model_dir": str(model_dir),
            "mode": "quick" if args.quick else "full",
            "csg_bytes": render_csg(paths, output_root, repo_root),
        }
        views_a = output_root / "views-a"
        hashes_a = render_views(paths["render.py"], views_a, repo_root)
        result["view_hashes"] = hashes_a

        if not args.quick:
            views_b = output_root / "views-b"
            hashes_b = render_views(paths["render.py"], views_b, repo_root)
            if hashes_a != hashes_b:
                changed = sorted(
                    name
                    for name in REQUIRED_VIEWS
                    if hashes_a[name] != hashes_b[name]
                )
                raise ValidationError(
                    "evidence views are not byte-deterministic: " + ", ".join(changed)
                )
            result["deterministic_repeat"] = True
            namespace = load_renderer(paths["render.py"])
            result["semantic"] = validate_semantics(
                namespace,
                paths,
                output_root,
                repo_root,
            )

        if args.photos is not None:
            result["comparison"] = validate_comparison(
                paths["compare.py"],
                args.photos.resolve(),
                views_a,
                output_root,
                repo_root,
            )
        return result
    finally:
        if temporary is not None:
            temporary.cleanup()


def main() -> int:
    args = parse_args()
    try:
        result = validate(args)
    except ValidationError as error:
        print(f"model_validation=FAIL reason={error}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "model_validation=PASS "
            f"mode={result['mode']} "
            f"csg_bytes={result['csg_bytes']} "
            f"views={len(result['view_hashes'])}"
        )
        if "semantic" in result:
            semantic = result["semantic"]
            print(
                "semantic=PASS "
                f"controls={semantic['controls']} "
                f"atlas={semantic['atlas_composition']}"
            )
        if "comparison" in result:
            comparison = result["comparison"]
            print(
                "comparison=PASS "
                f"images={comparison['images']} "
                "metadata_chunks=0"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
