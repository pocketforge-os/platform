#!/usr/bin/env python3
"""Hermetic regression coverage for the exact-consumer lock mirror gate."""

from __future__ import annotations

from contextlib import redirect_stderr
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
import check_lock_mirrors as gate  # noqa: E402


IMAGE_URL = "https://github.com/pocketforge-os/image.git"
PLATFORM267_IMAGE = "4b92b6d625c38ffd4dce36e63cf847645b18da18"
CORRECTED_IMAGE = "803f1f3848b33f9363d0054e1bb1d43957828fbc"
CURRENT_IMAGE = "34eb2b36002931d7006abc3bdc9fa9dffab7694f"
CURRENT_UAPI = "45b87a7d0e68a5aaafdc94523db791483e8a27cd"
BUILD9_KERNEL = "45b87a7d0e68a5aaafdc94523db791483e8a27cd"
CURRENT_GAMESCOPE = "298881e3dff1ade108d57a257e8bf59bf8c6436f"
STALE_GAMESCOPE = "0000000000000000000000000000000000000000"
EXPECTED_UAPI = "a75bf257f2ecb4d6cff7e2a921b77d24ebecbbb7"
STALE_UAPI = "40ea8fd9dcaeb9526b8032038f1dc820216d7959"
RUNTIME_SHA = "b289235d8cbdc8d542e551b8139d22b6abf31ec1"
LAUNCHER_SHA = "8209c392ea19abfe6377d7254cb063eed43c491b"
PREVIOUS_RUNTIME_SHA = "1dd87ecc2952584a7ef1473c5dcb872662b7c0cb"
SOURCE_LOCK_PATH = "build/platform-runtimes/steamlink-ffmpeg59/v1/source.lock"
FIXTURES = Path(__file__).with_name("fixtures")
BASE_COMMIT = "dc4b6a6fc5adf583a4b1697bc8c54a9f1be13803"


class FixtureResolver:
    """Test-only exact-identity resolver; production uses GitCommitResolver."""

    def __init__(self, trees: dict[tuple[str, str], dict[str, bytes]]):
        self.trees = trees
        self.requests: list[tuple[str, str]] = []

    def read_tree(self, consumer: gate.Consumer, commit: str) -> dict[str, bytes]:
        self.requests.append((consumer.repo, commit))
        try:
            return self.trees[(consumer.repo, commit)]
        except KeyError as error:
            raise gate.MissingConsumerCommit("fixture has no tree for the requested literal commit") from error


def uapi_lock(image_commit: str, image_url: str = IMAGE_URL) -> bytes:
    return f'''\
[platform_runtime.steamlink_ffmpeg59_v1.build_args]
PF_FFMPEG_UAPI_SHA = "{EXPECTED_UAPI}"

[[repos]]
name = "image"
url = "{image_url}"
sha = "{image_commit}"
'''.encode()


def uapi_manifest(image_url: str = IMAGE_URL) -> bytes:
    return f'''\
schema_version = 1

[[consumers]]
repo = "image"
url = "{image_url}"
commit_selector = "repos.image.sha"

[[mirrors]]
id = "steamlink-kernel-uapi-sha"
platform_field = "platform_runtime.steamlink_ffmpeg59_v1.build_args.PF_FFMPEG_UAPI_SHA"
consumer_repo = "image"
consumer_path = "{SOURCE_LOCK_PATH}"
parser = "shell-assignment"
key = "KERNEL_UAPI_SHA"
comparison = "equal"
'''.encode()


def build9_lock(image_commit: str) -> bytes:
    return f'''\
[platform_runtime.steamlink_ffmpeg59_v1]
source_sha = "{CURRENT_UAPI}"

[platform_runtime.steamlink_ffmpeg59_v1.build_args]
PF_FFMPEG_UAPI_SHA = "{CURRENT_UAPI}"

[[repos]]
name = "kernel-sunxi-7.x"
url = "https://github.com/pocketforge-os/kernel-sunxi-7.x.git"
sha = "{BUILD9_KERNEL}"

[[repos]]
name = "image"
url = "{IMAGE_URL}"
sha = "{image_commit}"
'''.encode()


def build9_uapi_manifest(*, aliases: tuple[str, ...], migration: bytes = b"") -> bytes:
    rendered_aliases = ", ".join(f'"{alias}"' for alias in aliases)
    return f'''\
schema_version = 1

[[consumers]]
repo = "image"
url = "{IMAGE_URL}"
commit_selector = "repos.image.sha"

[[mirrors]]
id = "steamlink-kernel-uapi-sha"
platform_field = "platform_runtime.steamlink_ffmpeg59_v1.build_args.PF_FFMPEG_UAPI_SHA"
aliases = [{rendered_aliases}]
consumer_repo = "image"
consumer_path = "{SOURCE_LOCK_PATH}"
parser = "shell-assignment"
key = "KERNEL_UAPI_SHA"
comparison = "equal"
'''.encode() + migration


def build9_uapi_migration(
    *,
    mirror_id: str = "steamlink-kernel-uapi-sha",
    old_aliases: tuple[str, ...] = (
        "platform_runtime.steamlink_ffmpeg59_v1.source_sha",
        "repos.kernel-sunxi-7.x.sha",
    ),
    new_aliases: tuple[str, ...] = (
        "platform_runtime.steamlink_ffmpeg59_v1.source_sha",
    ),
) -> bytes:
    def identity(aliases: tuple[str, ...]) -> str:
        rendered_aliases = ", ".join(f'"{alias}"' for alias in aliases)
        return (
            '{ platform_field = "platform_runtime.steamlink_ffmpeg59_v1.build_args.PF_FFMPEG_UAPI_SHA", '
            f'aliases = [{rendered_aliases}], consumer_repo = "image", '
            f'consumer_path = "{SOURCE_LOCK_PATH}", parser = "shell-assignment", '
            'key = "KERNEL_UAPI_SHA", comparison = "equal", expected_matches = 1 }'
        )

    return f'''\

[[mirror_migrations]]
id = "build9-steamlink-kernel-uapi-sha"
mirror_id = "{mirror_id}"
old = {identity(old_aliases)}
new = {identity(new_aliases)}
'''.encode()


def pin_lock(image_commit: str, *, duplicate_runtime_field: bool = False) -> bytes:
    duplicate = f'''\

[profile_pins.fixture]
runtime = "{RUNTIME_SHA}"
''' if duplicate_runtime_field else ""
    return f'''\
[[repos]]
name = "image"
url = "{IMAGE_URL}"
sha = "{image_commit}"

[[repos]]
name = "runtime"
url = "https://github.com/pocketforge-os/runtime.git"
sha = "{RUNTIME_SHA}"

[[repos]]
name = "launcher"
url = "https://github.com/pocketforge-os/launcher.git"
sha = "{LAUNCHER_SHA}"
{duplicate}'''.encode()


def classification_manifest(*, include_reference: bool = False) -> bytes:
    reference = f'''\

[[references]]
id = "runtime-prose"
platform_field = "repos.runtime.sha"
consumer_repo = "image"
consumer_path = "README.md"
parser = "template"
template = "documented runtime {{value}}"
reason = "fixture prose, not a consumer mirror"
''' if include_reference else ""
    return f'''\
schema_version = 1

[[consumers]]
repo = "image"
url = "{IMAGE_URL}"
commit_selector = "repos.image.sha"

[[mirrors]]
id = "launcher-guard"
platform_field = "repos.launcher.sha"
consumer_repo = "image"
consumer_path = "guard.sh"
parser = "shell-assignment"
key = "PIN_SHA"
comparison = "equal"
{reference}'''.encode()


def reviewer_bypass_lock() -> bytes:
    return (
        f'''\
[platform_runtime.steamlink_ffmpeg59_v1.build_args]
PF_FFMPEG_UAPI_SHA = "{EXPECTED_UAPI}"

'''.encode()
        + pin_lock(PLATFORM267_IMAGE)
    )


class LockMirrorGateTests(unittest.TestCase):
    def test_build9_mirror_migration_is_exact_scoped_and_one_shot(self) -> None:
        old_aliases = (
            "platform_runtime.steamlink_ffmpeg59_v1.source_sha",
            "repos.kernel-sunxi-7.x.sha",
        )
        new_aliases = ("platform_runtime.steamlink_ffmpeg59_v1.source_sha",)
        tree = {
            SOURCE_LOCK_PATH: f"KERNEL_UAPI_SHA='{CURRENT_UAPI}'\n".encode(),
        }
        lock = build9_lock(CORRECTED_IMAGE)
        old_manifest = build9_uapi_manifest(aliases=old_aliases)
        candidate = build9_uapi_manifest(aliases=new_aliases)

        undeclared = gate.check_gate(
            lock,
            candidate,
            FixtureResolver({("image", CORRECTED_IMAGE): tree}),
            baseline_manifest_raw=old_manifest,
            baseline_commit=BASE_COMMIT,
        )
        self.assertFalse(undeclared.ok)
        exact_refusal = next(
            diagnostic
            for diagnostic in undeclared.diagnostics
            if diagnostic.classification == "BASELINE_MIRROR_CHANGED"
        )
        self.assertEqual(
            exact_refusal.platform_field,
            "platform_runtime.steamlink_ffmpeg59_v1.build_args.PF_FFMPEG_UAPI_SHA",
        )
        self.assertIn("'steamlink-kernel-uapi-sha'", exact_refusal.detail)
        self.assertIn("aliases", exact_refusal.detail)
        print("BUILD9 RED undeclared:", exact_refusal.render())

        migration = build9_uapi_migration()
        declared_baseline = build9_uapi_manifest(aliases=old_aliases, migration=migration)
        exact = gate.check_gate(
            lock,
            candidate,
            FixtureResolver({("image", CORRECTED_IMAGE): tree}),
            baseline_manifest_raw=declared_baseline,
            baseline_commit=BASE_COMMIT,
        )
        self.assertTrue(exact.ok, exact.render())

        other_mirror = b"[[mirrors]]" + old_manifest.split(b"[[mirrors]]", 1)[1].replace(
            b'id = "steamlink-kernel-uapi-sha"', b'id = "some-other-mirror"', 1
        )
        different_id_baseline = (
            old_manifest
            + b"\n"
            + other_mirror
            + build9_uapi_migration(mirror_id="some-other-mirror")
        )
        different_id_candidate = candidate + b"\n" + other_mirror
        negative_cases = {
            "different mirror id": (
                different_id_baseline,
                different_id_candidate,
                "BASELINE_MIRROR_CHANGED",
            ),
            "extra field change": (
                declared_baseline,
                candidate.replace(
                    b'consumer_path = "build/platform-runtimes/steamlink-ffmpeg59/v1/source.lock"',
                    b'consumer_path = "build/platform-runtimes/steamlink-ffmpeg59/v1/moved.lock"',
                ),
                "BASELINE_MIRROR_CHANGED",
            ),
            "wrong old identity": (
                build9_uapi_manifest(
                    aliases=old_aliases,
                    migration=build9_uapi_migration(old_aliases=new_aliases),
                ),
                candidate,
                "MALFORMED_BASELINE_MANIFEST",
            ),
            "wrong new identity": (
                build9_uapi_manifest(
                    aliases=old_aliases,
                    migration=build9_uapi_migration(new_aliases=()),
                ),
                candidate,
                "BASELINE_MIRROR_CHANGED",
            ),
            "stale declaration": (
                declared_baseline,
                declared_baseline,
                "BASELINE_MIRROR_MIGRATION_STALE",
            ),
        }
        for name, (
            negative_baseline,
            negative_candidate,
            classification,
        ) in negative_cases.items():
            with self.subTest(name=name):
                result = gate.check_gate(
                    lock,
                    negative_candidate,
                    FixtureResolver({("image", CORRECTED_IMAGE): tree}),
                    baseline_manifest_raw=negative_baseline,
                    baseline_commit=BASE_COMMIT,
                )
                self.assertFalse(result.ok, f"{name} unexpectedly passed")
                self.assertIn(
                    classification,
                    [diagnostic.classification for diagnostic in result.diagnostics],
                )

    def test_platform267_red_and_corrected_green(self) -> None:
        stale_tree = {
            SOURCE_LOCK_PATH: (FIXTURES / "platform267" / "source.lock").read_bytes(),
        }
        stale_resolver = FixtureResolver({("image", PLATFORM267_IMAGE): stale_tree})
        red = gate.check_gate(uapi_lock(PLATFORM267_IMAGE), uapi_manifest(), stale_resolver)
        self.assertFalse(red.ok)
        self.assertEqual(stale_resolver.requests, [("image", PLATFORM267_IMAGE)])
        stale = next(d for d in red.diagnostics if d.classification == "STALE_MIRROR")
        self.assertEqual(stale.platform_field, "platform_runtime.steamlink_ffmpeg59_v1.build_args.PF_FFMPEG_UAPI_SHA")
        self.assertEqual(stale.commit, PLATFORM267_IMAGE)
        self.assertEqual(stale.path, SOURCE_LOCK_PATH)
        self.assertEqual(stale.expected, EXPECTED_UAPI)
        self.assertEqual(stale.actual, STALE_UAPI)
        print("RED evidence:", stale.render())

        corrected_tree = {
            SOURCE_LOCK_PATH: (FIXTURES / "corrected" / "source.lock").read_bytes(),
        }
        corrected_resolver = FixtureResolver({("image", CORRECTED_IMAGE): corrected_tree})
        green = gate.check_gate(uapi_lock(CORRECTED_IMAGE), uapi_manifest(), corrected_resolver)
        self.assertTrue(green.ok, green.render())
        self.assertEqual(corrected_resolver.requests, [("image", CORRECTED_IMAGE)])
        print("GREEN evidence:", green.render())

    def test_baseline_rejects_reviewer_candidate_only_bypass(self) -> None:
        tree = {
            SOURCE_LOCK_PATH: (FIXTURES / "platform267" / "source.lock").read_bytes(),
            "guard.sh": f"PIN_SHA='{LAUNCHER_SHA}'\n".encode(),
        }
        lock = reviewer_bypass_lock()
        candidate_without_uapi = classification_manifest()

        parent_behavior = gate.check_gate(
            lock,
            candidate_without_uapi,
            FixtureResolver({("image", PLATFORM267_IMAGE): tree}),
        )
        self.assertTrue(parent_behavior.ok, parent_behavior.render())
        self.assertNotIn(STALE_UAPI, gate.parse_lock(lock)[1])
        print("STRICT PARENT RED: candidate-only gate incorrectly returned PASS")
        print(parent_behavior.render())

        repaired = gate.check_gate(
            lock,
            candidate_without_uapi,
            FixtureResolver({("image", PLATFORM267_IMAGE): tree}),
            baseline_manifest_raw=uapi_manifest(),
            baseline_commit=BASE_COMMIT,
        )
        self.assertFalse(repaired.ok)
        removed = next(
            diagnostic
            for diagnostic in repaired.diagnostics
            if diagnostic.classification == "BASELINE_MIRROR_REMOVED"
        )
        self.assertEqual(removed.platform_field, "platform_runtime.steamlink_ffmpeg59_v1.build_args.PF_FFMPEG_UAPI_SHA")
        self.assertEqual(removed.consumer_repo, "image")
        self.assertEqual(removed.commit, BASE_COMMIT)
        self.assertEqual(removed.path, SOURCE_LOCK_PATH)
        self.assertEqual(removed.actual, "<missing>")
        print("STRICT REPAIR GREEN: baseline anchor rejected removed UAPI mirror")
        print(removed.render())

    def test_baseline_rejects_required_consumer_removal(self) -> None:
        replacement_consumer = b'''\
[[consumers]]
repo = "other"
url = "https://github.com/pocketforge-os/other.git"
commit_selector = "repos.other.sha"

'''
        candidate = (
            replacement_consumer
            + b"[[mirrors]]"
            + uapi_manifest().split(b"[[mirrors]]", 1)[1]
        )
        candidate = b"schema_version = 1\n\n" + candidate.replace(
            b'consumer_repo = "image"', b'consumer_repo = "other"'
        )
        result = gate.check_gate(
            uapi_lock(CORRECTED_IMAGE),
            candidate,
            FixtureResolver({}),
            baseline_manifest_raw=uapi_manifest(),
            baseline_commit=BASE_COMMIT,
        )
        removed = next(
            diagnostic
            for diagnostic in result.diagnostics
            if diagnostic.classification == "BASELINE_CONSUMER_REMOVED"
        )
        self.assertEqual(removed.consumer_repo, "image")
        self.assertEqual(removed.platform_field, "repos.image.sha")
        self.assertEqual(removed.actual, "<missing>")

    def test_baseline_rejects_every_load_bearing_mirror_identity_change(self) -> None:
        baseline = uapi_manifest()
        other_consumer = b'''\
[[consumers]]
repo = "other"
url = "https://github.com/pocketforge-os/other.git"
commit_selector = "repos.other.sha"

'''
        template_baseline = baseline.replace(
            b'parser = "shell-assignment"\nkey = "KERNEL_UAPI_SHA"',
            b'parser = "template"\ntemplate = "KERNEL_UAPI_SHA=\'{value}\'"',
        )
        cases = {
            "platform_field": (
                baseline,
                baseline.replace(
                    b'platform_field = "platform_runtime.steamlink_ffmpeg59_v1.build_args.PF_FFMPEG_UAPI_SHA"',
                    b'platform_field = "repos.image.sha"',
                ),
            ),
            "aliases": (
                baseline,
                baseline.replace(
                    b'consumer_repo = "image"',
                    b'aliases = ["repos.image.sha"]\nconsumer_repo = "image"',
                ),
            ),
            "consumer_repo": (
                baseline,
                baseline.replace(b"[[mirrors]]", other_consumer + b"[[mirrors]]", 1).replace(
                    b'consumer_repo = "image"', b'consumer_repo = "other"', 1
                ),
            ),
            "consumer_path": (
                baseline,
                baseline.replace(SOURCE_LOCK_PATH.encode(), b"moved/source.lock"),
            ),
            "parser": (
                baseline,
                baseline.replace(
                    b'parser = "shell-assignment"\nkey = "KERNEL_UAPI_SHA"',
                    b'parser = "template"\ntemplate = "KERNEL_UAPI_SHA=\'{value}\'"',
                ),
            ),
            "key": (
                baseline,
                baseline.replace(b'key = "KERNEL_UAPI_SHA"', b'key = "OTHER_SHA"'),
            ),
            "template": (
                template_baseline,
                template_baseline.replace(
                    b"KERNEL_UAPI_SHA='{value}'", b"KERNEL_UAPI_SHA = '{value}'"
                ),
            ),
            "expected_matches": (
                baseline,
                baseline.replace(
                    b'comparison = "equal"',
                    b'comparison = "equal"\nexpected_matches = 2',
                ),
            ),
        }
        tree = {
            SOURCE_LOCK_PATH: (FIXTURES / "corrected" / "source.lock").read_bytes(),
        }
        for field, (required, candidate) in cases.items():
            with self.subTest(field=field):
                result = gate.check_gate(
                    uapi_lock(CORRECTED_IMAGE),
                    candidate,
                    FixtureResolver({("image", CORRECTED_IMAGE): tree}),
                    baseline_manifest_raw=required,
                    baseline_commit=BASE_COMMIT,
                )
                changed = next(
                    diagnostic
                    for diagnostic in result.diagnostics
                    if diagnostic.classification == "BASELINE_MIRROR_CHANGED"
                )
                self.assertIn(field, changed.detail)

        comparison_change = baseline.replace(
            b'comparison = "equal"', b'comparison = "prefix-match"'
        )
        malformed = gate.check_gate(
            uapi_lock(CORRECTED_IMAGE),
            comparison_change,
            FixtureResolver({("image", CORRECTED_IMAGE): tree}),
            baseline_manifest_raw=baseline,
            baseline_commit=BASE_COMMIT,
        )
        self.assertEqual(
            [diagnostic.classification for diagnostic in malformed.diagnostics],
            ["MALFORMED_MANIFEST"],
        )

    def test_baseline_allows_additions_and_reference_removal(self) -> None:
        baseline_reference = f'''\

[[references]]
id = "uapi-prose"
platform_field = "platform_runtime.steamlink_ffmpeg59_v1.build_args.PF_FFMPEG_UAPI_SHA"
consumer_repo = "image"
consumer_path = "README.md"
parser = "template"
template = "documented {{value}}"
reason = "incidental prose"
'''.encode()
        added_mirror = f'''\

[[mirrors]]
id = "added-launcher-guard"
platform_field = "repos.launcher.sha"
consumer_repo = "image"
consumer_path = "guard.sh"
parser = "shell-assignment"
key = "PIN_SHA"
comparison = "equal"
'''.encode()
        baseline = uapi_manifest() + baseline_reference
        candidate = uapi_manifest() + added_mirror
        tree = {
            SOURCE_LOCK_PATH: (FIXTURES / "corrected" / "source.lock").read_bytes(),
            "guard.sh": f"PIN_SHA='{LAUNCHER_SHA}'\n".encode(),
        }
        result = gate.check_gate(
            reviewer_bypass_lock().replace(PLATFORM267_IMAGE.encode(), CORRECTED_IMAGE.encode()),
            candidate,
            FixtureResolver({("image", CORRECTED_IMAGE): tree}),
            baseline_manifest_raw=baseline,
            baseline_commit=BASE_COMMIT,
        )
        self.assertTrue(result.ok, result.render())
        self.assertEqual(result.mirror_rule_count, 2)

    def test_malformed_baseline_manifest_fails_closed(self) -> None:
        result = gate.check_gate(
            uapi_lock(PLATFORM267_IMAGE),
            uapi_manifest(),
            FixtureResolver({}),
            baseline_manifest_raw=b"schema_version = [",
            baseline_commit=BASE_COMMIT,
        )
        self.assertEqual(
            [diagnostic.classification for diagnostic in result.diagnostics],
            ["MALFORMED_BASELINE_MANIFEST"],
        )

    def test_cli_requires_baseline_and_limits_bootstrap_commit(self) -> None:
        errors = io.StringIO()
        with redirect_stderr(errors):
            missing = gate.main(["--baseline-commit", CURRENT_IMAGE])
            wrong_bootstrap = gate.main(
                ["--baseline-commit", CURRENT_IMAGE, "--bootstrap-missing-baseline"]
            )
            unreadable = gate.main(
                [
                    "--baseline-commit",
                    CURRENT_IMAGE,
                    "--baseline-manifest",
                    "/definitely/missing/lock-mirrors.toml",
                ]
            )
        self.assertEqual((missing, wrong_bootstrap, unreadable), (1, 1, 1))
        self.assertIn("verified exact-base manifest is required", errors.getvalue())
        self.assertIn("bootstrap is allowed only for exact introductory base", errors.getvalue())
        self.assertIn("No such file or directory", errors.getvalue())

    def test_missing_consumer_commit_fails_closed(self) -> None:
        result = gate.check_gate(uapi_lock(PLATFORM267_IMAGE), uapi_manifest(), FixtureResolver({}))
        self.assertEqual([d.classification for d in result.diagnostics], ["MISSING_CONSUMER_COMMIT"])
        diagnostic = result.diagnostics[0]
        self.assertEqual(diagnostic.commit, PLATFORM267_IMAGE)
        self.assertEqual(diagnostic.expected, PLATFORM267_IMAGE)
        self.assertEqual(diagnostic.actual, "<missing>")

    def test_git_resolver_reads_exact_commit_not_branch_tip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lock-mirror-git-test-") as temporary:
            repo = Path(temporary) / "image"
            subprocess.run(
                ["git", "init", "--quiet", "--object-format=sha1", str(repo)], check=True
            )
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"],
                check=True,
            )
            source_lock = repo / SOURCE_LOCK_PATH
            source_lock.parent.mkdir(parents=True)
            source_lock.write_bytes((FIXTURES / "corrected" / "source.lock").read_bytes())
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "--quiet", "-m", "corrected"], check=True)
            pinned = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            source_lock.write_bytes((FIXTURES / "platform267" / "source.lock").read_bytes())
            subprocess.run(["git", "-C", str(repo), "commit", "--quiet", "-am", "stale branch tip"], check=True)
            branch_tip = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip()
            self.assertNotEqual(pinned, branch_tip)

            with gate.GitCommitResolver() as resolver:
                result = gate.check_gate(
                    uapi_lock(pinned, str(repo)), uapi_manifest(str(repo)), resolver
                )
            self.assertTrue(result.ok, result.render())

    def test_malformed_manifest_fails_closed(self) -> None:
        result = gate.check_gate(uapi_lock(PLATFORM267_IMAGE), b"schema_version = [", FixtureResolver({}))
        self.assertEqual([d.classification for d in result.diagnostics], ["MALFORMED_MANIFEST"])

    def test_missing_declared_mirror_fails_closed(self) -> None:
        resolver = FixtureResolver({("image", PLATFORM267_IMAGE): {}})
        result = gate.check_gate(uapi_lock(PLATFORM267_IMAGE), uapi_manifest(), resolver)
        missing = next(d for d in result.diagnostics if d.classification == "MISSING_MIRROR")
        self.assertEqual(missing.path, SOURCE_LOCK_PATH)
        self.assertEqual(missing.expected, EXPECTED_UAPI)
        self.assertEqual(missing.actual, "<missing>")

    def test_duplicate_mirror_hit_is_ambiguous(self) -> None:
        source = f"KERNEL_UAPI_SHA='{EXPECTED_UAPI}'\nKERNEL_UAPI_SHA='{EXPECTED_UAPI}'\n".encode()
        resolver = FixtureResolver({("image", PLATFORM267_IMAGE): {SOURCE_LOCK_PATH: source}})
        result = gate.check_gate(uapi_lock(PLATFORM267_IMAGE), uapi_manifest(), resolver)
        ambiguous = next(d for d in result.diagnostics if d.classification == "AMBIGUOUS_MIRROR")
        self.assertIn("expected 1 match(es), found 2", ambiguous.detail)

    def test_unrelated_non_mirror_value_requires_explicit_reference(self) -> None:
        tree = {
            "guard.sh": f"PIN_SHA='{LAUNCHER_SHA}'\n".encode(),
            "README.md": f"documented runtime {RUNTIME_SHA}\n".encode(),
        }
        resolver = FixtureResolver({("image", PLATFORM267_IMAGE): tree})
        result = gate.check_gate(
            pin_lock(PLATFORM267_IMAGE), classification_manifest(include_reference=True), resolver
        )
        self.assertTrue(result.ok, result.render())
        self.assertEqual(result.classified_hit_count, 2)

    def test_new_undeclared_hit_fails_closed(self) -> None:
        tree = {
            "guard.sh": f"PIN_SHA='{LAUNCHER_SHA}'\n".encode(),
            "README.md": f"new runtime mirror {RUNTIME_SHA}\n".encode(),
        }
        resolver = FixtureResolver({("image", PLATFORM267_IMAGE): tree})
        result = gate.check_gate(pin_lock(PLATFORM267_IMAGE), classification_manifest(), resolver)
        undeclared = next(d for d in result.diagnostics if d.classification == "UNDECLARED_HIT")
        self.assertEqual(undeclared.platform_field, "repos.runtime.sha")
        self.assertEqual(undeclared.path, "README.md")

    def test_equal_lock_values_make_unclassified_hit_ambiguous(self) -> None:
        tree = {
            "guard.sh": f"PIN_SHA='{LAUNCHER_SHA}'\n".encode(),
            "README.md": f"new runtime mirror {RUNTIME_SHA}\n".encode(),
        }
        resolver = FixtureResolver({("image", PLATFORM267_IMAGE): tree})
        result = gate.check_gate(
            pin_lock(PLATFORM267_IMAGE, duplicate_runtime_field=True), classification_manifest(), resolver
        )
        ambiguous = next(d for d in result.diagnostics if d.classification == "AMBIGUOUS_HIT")
        self.assertIn("repos.runtime.sha", ambiguous.platform_field)
        self.assertIn("profile_pins.fixture.runtime", ambiguous.platform_field)

    def test_current_contract_generation_passes_and_mixed_generation_fails(self) -> None:
        candidate_manifest = (ROOT / "ci" / "lock-mirrors.toml").read_bytes()
        current_tree = {
            "build/Dockerfile.pf": (FIXTURES / "current" / "Dockerfile.pf").read_bytes(),
            "scripts/verify-cursor-tools-recipe.py": (
                b'"10.0.32.86:5555/pocketforge/ci-tools@sha256:'
                b'2ff536627228c90e5c32b7d6345b21600a38a17481c075b41683db47ead3e862":\n'
                b'    "ec5b2621f636261978d3bb4fd9843ae22a59c320",\n'
            ),
            "build/produce-gamescope-pvr-cache.sh": (
                f"expected_gamescope_sha={CURRENT_GAMESCOPE}\n".encode()
            ),
            SOURCE_LOCK_PATH: (FIXTURES / "corrected" / "source.lock").read_bytes().replace(
                EXPECTED_UAPI.encode(), CURRENT_UAPI.encode(), 1
            ),
            "scripts/build-rootfs.sh": (FIXTURES / "current" / "build-rootfs.sh").read_bytes(),
            "tests/test-gamescope-pvr-cache.sh": (
                f"g1_sha={CURRENT_GAMESCOPE}\n"
                f"grep -F '{CURRENT_GAMESCOPE}' producer\n".encode()
            ),
        }
        resolver = FixtureResolver({("image", CURRENT_IMAGE): current_tree})
        result = gate.check_gate(
            (ROOT / "platform.lock").read_bytes(),
            candidate_manifest,
            resolver,
            baseline_manifest_raw=candidate_manifest,
            baseline_commit=BASE_COMMIT,
        )
        self.assertTrue(result.ok, result.render())
        self.assertEqual(resolver.requests, [("image", CURRENT_IMAGE)])
        self.assertEqual(result.mirror_rule_count, 19)

        mixed_lock = (ROOT / "platform.lock").read_bytes().replace(
            f'sha  = "{RUNTIME_SHA}"'.encode(),
            f'sha  = "{PREVIOUS_RUNTIME_SHA}"'.encode(),
            1,
        )
        mixed = gate.check_gate(
            mixed_lock,
            candidate_manifest,
            FixtureResolver({("image", CURRENT_IMAGE): current_tree}),
            baseline_manifest_raw=candidate_manifest,
            baseline_commit=BASE_COMMIT,
        )
        self.assertFalse(mixed.ok)
        drift = next(
            diagnostic for diagnostic in mixed.diagnostics
            if diagnostic.classification == "STALE_MIRROR"
            and diagnostic.platform_field == "repos.runtime.sha"
        )
        self.assertEqual(drift.expected, PREVIOUS_RUNTIME_SHA)

        mixed_gamescope_lock = (ROOT / "platform.lock").read_bytes().replace(
            f'sha  = "{CURRENT_GAMESCOPE}"'.encode(),
            f'sha  = "{STALE_GAMESCOPE}"'.encode(),
            1,
        )
        mixed_gamescope = gate.check_gate(
            mixed_gamescope_lock,
            candidate_manifest,
            FixtureResolver({("image", CURRENT_IMAGE): current_tree}),
            baseline_manifest_raw=candidate_manifest,
            baseline_commit=BASE_COMMIT,
        )
        self.assertFalse(mixed_gamescope.ok)
        gamescope_drift = next(
            diagnostic for diagnostic in mixed_gamescope.diagnostics
            if diagnostic.classification == "STALE_MIRROR"
            and diagnostic.platform_field == "repos.gamescope.sha"
        )
        self.assertEqual(gamescope_drift.expected, STALE_GAMESCOPE)
        self.assertEqual(gamescope_drift.actual, CURRENT_GAMESCOPE)
        self.assertEqual(drift.actual, RUNTIME_SHA)


if __name__ == "__main__":
    unittest.main()
