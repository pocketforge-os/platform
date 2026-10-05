#!/usr/bin/env python3
"""Fail closed when a pinned consumer's platform.lock mirrors drift.

The candidate platform.lock is the only source of consumer commit identities,
while the exact PR-base manifest anchors the required consumer/mirror inventory.
Production resolution fetches literal commits into temporary Git object databases
and reads their trees without consulting a branch or checkout.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Mapping, Protocol

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - CI and supported hosts use 3.11+
    sys.stderr.write("FATAL: lock mirror gate requires Python 3.11+ (tomllib)\n")
    raise SystemExit(3)


HEX_RE = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{64}|[0-9A-Fa-f]{40})(?![0-9A-Fa-f])")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
RULE_PARSERS = frozenset({"shell-assignment", "template"})
BOOTSTRAP_BASE_COMMIT = "dc4b6a6fc5adf583a4b1697bc8c54a9f1be13803"
MANIFEST_PATH = "ci/lock-mirrors.toml"
MIRROR_IDENTITY_FIELDS = (
    "platform_field",
    "aliases",
    "consumer_repo",
    "consumer_path",
    "parser",
    "key",
    "template",
    "comparison",
    "expected_matches",
)


@dataclass(frozen=True)
class Consumer:
    repo: str
    url: str
    commit_selector: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    kind: str
    platform_field: str
    aliases: tuple[str, ...]
    consumer_repo: str
    consumer_path: str
    parser: str
    key: str | None
    template: str | None
    comparison: str | None
    expected_matches: int | None
    reason: str | None

    @property
    def platform_fields(self) -> tuple[str, ...]:
        return (self.platform_field, *self.aliases)


@dataclass(frozen=True)
class Manifest:
    consumers: tuple[Consumer, ...]
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class Diagnostic:
    classification: str
    platform_field: str
    consumer_repo: str
    commit: str
    path: str
    expected: str
    actual: str
    detail: str

    def render(self) -> str:
        return (
            f"{self.classification} platform_field={self.platform_field} "
            f"consumer={self.consumer_repo}@{self.commit} path={self.path} "
            f"expected={self.expected} actual={self.actual} detail={self.detail}"
        )


@dataclass(frozen=True)
class GateResult:
    diagnostics: tuple[Diagnostic, ...]
    consumer_count: int = 0
    mirror_rule_count: int = 0
    reference_rule_count: int = 0
    classified_hit_count: int = 0
    lock_value_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    def render(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [diagnostic.render() for diagnostic in self.diagnostics]
        lines.append(
            f"lock-mirror gate: {status} consumers={self.consumer_count} "
            f"mirror_rules={self.mirror_rule_count} "
            f"reference_rules={self.reference_rule_count} "
            f"classified_hits={self.classified_hit_count} "
            f"lock_values={self.lock_value_count} errors={len(self.diagnostics)}"
        )
        return "\n".join(lines)


class MissingConsumerCommit(Exception):
    """The candidate lock's literal consumer commit could not be read."""


class ConsumerResolver(Protocol):
    def read_tree(self, consumer: Consumer, commit: str) -> Mapping[str, bytes]: ...


class GitCommitResolver:
    """Fetch and read literal commits; never resolve or checkout a branch."""

    def __init__(self, temp_root: str | None = None):
        self._temporary = tempfile.TemporaryDirectory(prefix="pf-lock-mirrors-", dir=temp_root)
        self._root = Path(self._temporary.name)

    def close(self) -> None:
        self._temporary.cleanup()

    def __enter__(self) -> "GitCommitResolver":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @staticmethod
    def _run(args: list[str], *, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)

    def _git_env(self, consumer: Consumer, repo_dir: Path) -> dict[str, str]:
        env = os.environ.copy()
        token = env.get("GH_TOKEN", "")
        if token and consumer.url.startswith("https://github.com/"):
            encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            config = repo_dir.parent / f"{consumer.repo}.auth.gitconfig"
            config.write_text(
                '[http "https://github.com/"]\n'
                f"\textraHeader = Authorization: Basic {encoded}\n",
                encoding="utf-8",
            )
            config.chmod(0o600)
            env["GIT_CONFIG_GLOBAL"] = str(config)
        return env

    def read_tree(self, consumer: Consumer, commit: str) -> Mapping[str, bytes]:
        repo_dir = self._root / f"{consumer.repo}.git"
        initialized = self._run(["git", "init", "--quiet", "--bare", str(repo_dir)])
        if initialized.returncode != 0:
            raise MissingConsumerCommit("could not initialize temporary Git database")
        env = self._git_env(consumer, repo_dir)
        fetched = self._run(
            [
                "git",
                f"--git-dir={repo_dir}",
                "fetch",
                "--quiet",
                "--no-tags",
                "--depth=1",
                consumer.url,
                commit,
            ],
            env=env,
        )
        if fetched.returncode != 0:
            raise MissingConsumerCommit("literal commit fetch failed")
        resolved = self._run(
            ["git", f"--git-dir={repo_dir}", "rev-parse", "--verify", "FETCH_HEAD^{commit}"],
            env=env,
        )
        actual = resolved.stdout.decode("ascii", "replace").strip()
        if resolved.returncode != 0 or actual != commit:
            raise MissingConsumerCommit(f"fetch resolved {actual or '<missing>'}, not the requested commit")
        listed = self._run(
            ["git", f"--git-dir={repo_dir}", "ls-tree", "-r", "-z", "--full-tree", commit],
            env=env,
        )
        if listed.returncode != 0:
            raise MissingConsumerCommit("literal commit tree could not be listed")
        tree: dict[str, bytes] = {}
        for entry in listed.stdout.split(b"\0"):
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            _mode, object_type, object_id = metadata.split(b" ", 2)
            if object_type != b"blob":
                continue
            path = raw_path.decode("utf-8", "strict")
            blob = self._run(
                ["git", f"--git-dir={repo_dir}", "cat-file", "blob", object_id.decode("ascii")],
                env=env,
            )
            if blob.returncode != 0:
                raise MissingConsumerCommit(f"could not read blob at {path}")
            tree[path] = blob.stdout
        return tree


def _manifest_error(detail: str, path: str = MANIFEST_PATH) -> GateResult:
    return GateResult(
        diagnostics=(
            Diagnostic(
                "MALFORMED_MANIFEST",
                "<manifest>",
                "<none>",
                "<none>",
                path,
                "valid-schema-v1",
                "invalid",
                detail,
            ),
        )
    )


def _baseline_error(detail: str, commit: str, path: str = MANIFEST_PATH) -> GateResult:
    return GateResult(
        diagnostics=(
            Diagnostic(
                "MALFORMED_BASELINE_MANIFEST",
                "<baseline-manifest>",
                "<none>",
                commit,
                path,
                "valid-schema-v1",
                "invalid",
                detail,
            ),
        )
    )


def _lock_error(detail: str, path: str = "platform.lock") -> GateResult:
    return GateResult(
        diagnostics=(
            Diagnostic(
                "MALFORMED_LOCK",
                "<lock>",
                "<none>",
                "<none>",
                path,
                "valid-TOML",
                "invalid",
                detail,
            ),
        )
    )


def _strict_keys(table: Mapping[str, object], allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ValueError(f"{where}: unknown key(s): {', '.join(unknown)}")


def _required_string(table: Mapping[str, object], key: str, where: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}.{key} must be a non-empty string")
    return value


def _safe_consumer_path(value: str, where: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value in ("", "."):
        raise ValueError(f"{where}.consumer_path must be a relative path without '..'")
    return str(path)


def parse_manifest(raw: bytes) -> Manifest:
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"TOML parse failed: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("manifest root must be a table")
    _strict_keys(data, {"schema_version", "consumers", "mirrors", "references"}, "manifest")
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must equal 1")

    raw_consumers = data.get("consumers")
    if not isinstance(raw_consumers, list) or not raw_consumers:
        raise ValueError("consumers must be a non-empty array of tables")
    consumers: list[Consumer] = []
    consumer_names: set[str] = set()
    for index, item in enumerate(raw_consumers):
        where = f"consumers[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{where} must be a table")
        _strict_keys(item, {"repo", "url", "commit_selector"}, where)
        repo = _required_string(item, "repo", where)
        url = _required_string(item, "url", where)
        selector = _required_string(item, "commit_selector", where)
        if repo in consumer_names:
            raise ValueError(f"{where}: duplicate consumer repo {repo!r}")
        if selector != f"repos.{repo}.sha":
            raise ValueError(f"{where}.commit_selector must be 'repos.{repo}.sha'")
        consumer_names.add(repo)
        consumers.append(Consumer(repo, url, selector))

    rules: list[Rule] = []
    rule_ids: set[str] = set()
    for kind, table_name in (("mirror", "mirrors"), ("reference", "references")):
        raw_rules = data.get(table_name, [])
        if not isinstance(raw_rules, list):
            raise ValueError(f"{table_name} must be an array of tables")
        for index, item in enumerate(raw_rules):
            where = f"{table_name}[{index}]"
            if not isinstance(item, dict):
                raise ValueError(f"{where} must be a table")
            allowed = {
                "id",
                "platform_field",
                "aliases",
                "consumer_repo",
                "consumer_path",
                "parser",
                "key",
                "template",
            }
            if kind == "mirror":
                allowed |= {"comparison", "expected_matches"}
            else:
                allowed.add("reason")
            _strict_keys(item, allowed, where)
            rule_id = _required_string(item, "id", where)
            if rule_id in rule_ids:
                raise ValueError(f"{where}: duplicate rule id {rule_id!r}")
            rule_ids.add(rule_id)
            platform_field = _required_string(item, "platform_field", where)
            raw_aliases = item.get("aliases", [])
            if not isinstance(raw_aliases, list) or not all(
                isinstance(alias, str) and alias for alias in raw_aliases
            ):
                raise ValueError(f"{where}.aliases must be an array of non-empty strings")
            aliases = tuple(raw_aliases)
            if len(set((platform_field, *aliases))) != 1 + len(aliases):
                raise ValueError(f"{where}.aliases contains a duplicate platform field")
            consumer_repo = _required_string(item, "consumer_repo", where)
            if consumer_repo not in consumer_names:
                raise ValueError(f"{where}.consumer_repo is not declared in consumers")
            consumer_path = _safe_consumer_path(
                _required_string(item, "consumer_path", where), where
            )
            parser = _required_string(item, "parser", where)
            if parser not in RULE_PARSERS:
                raise ValueError(f"{where}.parser must be one of {sorted(RULE_PARSERS)}")
            key = item.get("key")
            template = item.get("template")
            if parser == "shell-assignment":
                if not isinstance(key, str) or not key or template is not None:
                    raise ValueError(f"{where}: shell-assignment requires key and forbids template")
            if parser == "template":
                if not isinstance(template, str) or template.count("{value}") != 1 or key is not None:
                    raise ValueError(f"{where}: template parser requires exactly one '{{value}}' and forbids key")
            comparison: str | None = None
            expected_matches: int | None = None
            reason: str | None = None
            if kind == "mirror":
                comparison = _required_string(item, "comparison", where)
                if comparison != "equal":
                    raise ValueError(f"{where}.comparison must equal 'equal'")
                expected_matches = item.get("expected_matches", 1)
                if isinstance(expected_matches, bool) or not isinstance(expected_matches, int) or expected_matches < 1:
                    raise ValueError(f"{where}.expected_matches must be a positive integer")
            else:
                reason = _required_string(item, "reason", where)
            rules.append(
                Rule(
                    rule_id,
                    kind,
                    platform_field,
                    aliases,
                    consumer_repo,
                    consumer_path,
                    parser,
                    key if isinstance(key, str) else None,
                    template if isinstance(template, str) else None,
                    comparison,
                    expected_matches,
                    reason,
                )
            )
    if not any(rule.kind == "mirror" for rule in rules):
        raise ValueError("at least one mirror rule is required")
    return Manifest(tuple(consumers), tuple(rules))


def _consumer_identity(consumer: Consumer) -> str:
    return f"url={consumer.url};commit_selector={consumer.commit_selector}"


def _mirror_identity(rule: Rule) -> str:
    return ";".join(f"{field}={getattr(rule, field)!r}" for field in MIRROR_IDENTITY_FIELDS)


def _changed_mirror_fields(required: Rule, candidate: Rule) -> list[str]:
    return [
        field
        for field in MIRROR_IDENTITY_FIELDS
        if getattr(required, field) != getattr(candidate, field)
    ]


def baseline_diagnostics(
    candidate: Manifest, baseline: Manifest, baseline_commit: str
) -> list[Diagnostic]:
    """Require every trusted-base consumer and mirror declaration unchanged.

    Candidate additions are allowed. References are deliberately not part of
    the load-bearing baseline inventory. A legitimate future mirror migration
    must first land a separately reviewed, exact-base-scoped policy exception,
    then migrate in a follow-up and remove that exception; it must never happen
    by silently weakening this subset comparison.
    """

    diagnostics: list[Diagnostic] = []
    candidate_consumers = {consumer.repo: consumer for consumer in candidate.consumers}
    for required in baseline.consumers:
        actual = candidate_consumers.get(required.repo)
        if actual is None:
            classification = "BASELINE_CONSUMER_REMOVED"
            actual_identity = "<missing>"
            detail = f"required consumer {required.repo!r} was removed from the candidate manifest"
        elif actual != required:
            classification = "BASELINE_CONSUMER_CHANGED"
            actual_identity = _consumer_identity(actual)
            detail = f"required consumer {required.repo!r} changed load-bearing identity"
        else:
            continue
        diagnostics.append(
            Diagnostic(
                classification,
                required.commit_selector,
                required.repo,
                baseline_commit,
                MANIFEST_PATH,
                _consumer_identity(required),
                actual_identity,
                detail,
            )
        )

    candidate_mirrors = {
        rule.rule_id: rule for rule in candidate.rules if rule.kind == "mirror"
    }
    for required in (rule for rule in baseline.rules if rule.kind == "mirror"):
        actual = candidate_mirrors.get(required.rule_id)
        if actual is None:
            classification = "BASELINE_MIRROR_REMOVED"
            actual_identity = "<missing>"
            detail = f"required mirror {required.rule_id!r} was removed from the candidate manifest"
        else:
            changed = _changed_mirror_fields(required, actual)
            if not changed:
                continue
            classification = "BASELINE_MIRROR_CHANGED"
            actual_identity = _mirror_identity(actual)
            detail = (
                f"required mirror {required.rule_id!r} changed load-bearing field(s): "
                + ",".join(changed)
            )
        diagnostics.append(
            Diagnostic(
                classification,
                required.platform_field,
                required.consumer_repo,
                baseline_commit,
                required.consumer_path,
                _mirror_identity(required),
                actual_identity,
                detail,
            )
        )
    return diagnostics


def _flatten_lock(value: object, path: tuple[str, ...] = ()) -> dict[str, object]:
    flattened: dict[str, object] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            flattened.update(_flatten_lock(child, (*path, str(key))))
    elif isinstance(value, list):
        seen_names: set[str] = set()
        for index, child in enumerate(value):
            component = str(index)
            if isinstance(child, dict) and isinstance(child.get("name"), str):
                component = child["name"]
                if component in seen_names:
                    raise ValueError(f"duplicate named array entry at {'.'.join(path)}: {component}")
                seen_names.add(component)
            flattened.update(_flatten_lock(child, (*path, component)))
    else:
        flattened[".".join(path)] = value
    return flattened


def parse_lock(raw: bytes) -> tuple[dict[str, object], dict[str, list[str]]]:
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"TOML parse failed: {error}") from error
    fields = _flatten_lock(document)
    hex_values: dict[str, list[str]] = {}
    for field, value in fields.items():
        if isinstance(value, str) and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
            hex_values.setdefault(value, []).append(field)
    return fields, hex_values


def _text_files(tree: Mapping[str, bytes]) -> dict[str, str]:
    text: dict[str, str] = {}
    for path, raw in tree.items():
        if b"\0" in raw:
            continue
        try:
            text[path] = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return text


def _rule_matches(rule: Rule, content: str) -> list[tuple[int, int, str]]:
    if rule.parser == "shell-assignment":
        assert rule.key is not None
        expression = re.compile(
            rf"(?m)^[ \t]*(?:export[ \t]+)?{re.escape(rule.key)}[ \t]*=[ \t]*"
            rf"(?:'(?P<single>[^']*)'|\"(?P<double>[^\"]*)\"|(?P<bare>[^#\s]+))"
            rf"[ \t]*(?:#.*)?$"
        )
    else:
        assert rule.template is not None
        before, after = rule.template.split("{value}")
        expression = re.compile(
            re.escape(before)
            + r"(?P<value>(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{64}|[0-9A-Fa-f]{40})(?![0-9A-Fa-f]))"
            + re.escape(after)
        )
    matches: list[tuple[int, int, str]] = []
    for match in expression.finditer(content):
        if rule.parser == "template":
            group = "value"
        else:
            group = next(name for name in ("single", "double", "bare") if match.group(name) is not None)
        matches.append((match.start(group), match.end(group), match.group(group)))
    return matches


def check_gate(
    lock_raw: bytes,
    manifest_raw: bytes,
    resolver: ConsumerResolver,
    *,
    baseline_manifest_raw: bytes | None = None,
    baseline_commit: str = "<not-enforced>",
) -> GateResult:
    try:
        fields, hex_values = parse_lock(lock_raw)
    except ValueError as error:
        return _lock_error(str(error))
    try:
        manifest = parse_manifest(manifest_raw)
    except ValueError as error:
        return _manifest_error(str(error))

    mirror_count = sum(rule.kind == "mirror" for rule in manifest.rules)
    reference_count = len(manifest.rules) - mirror_count
    base_counts = {
        "consumer_count": len(manifest.consumers),
        "mirror_rule_count": mirror_count,
        "reference_rule_count": reference_count,
        "lock_value_count": len(hex_values),
    }
    diagnostics: list[Diagnostic] = []
    if baseline_manifest_raw is not None:
        try:
            baseline = parse_manifest(baseline_manifest_raw)
        except ValueError as error:
            return _baseline_error(str(error), baseline_commit)
        diagnostics.extend(baseline_diagnostics(manifest, baseline, baseline_commit))
    commits: dict[str, str] = {}
    trees: dict[str, dict[str, str]] = {}
    for consumer in manifest.consumers:
        commit_value = fields.get(consumer.commit_selector)
        lock_url = fields.get(f"repos.{consumer.repo}.url")
        commit = commit_value if isinstance(commit_value, str) else "<missing>"
        commits[consumer.repo] = commit
        if not isinstance(commit_value, str) or not COMMIT_RE.fullmatch(commit_value):
            diagnostics.append(
                Diagnostic(
                    "MISSING_CONSUMER_PIN",
                    consumer.commit_selector,
                    consumer.repo,
                    commit,
                    "platform.lock",
                    "40-hex-commit",
                    commit,
                    "candidate lock does not provide an exact consumer commit",
                )
            )
            continue
        if lock_url != consumer.url:
            diagnostics.append(
                Diagnostic(
                    "CONSUMER_URL_MISMATCH",
                    f"repos.{consumer.repo}.url",
                    consumer.repo,
                    commit,
                    "platform.lock",
                    consumer.url,
                    str(lock_url) if lock_url is not None else "<missing>",
                    "candidate lock consumer URL differs from the declared repository",
                )
            )
            continue
        try:
            trees[consumer.repo] = _text_files(resolver.read_tree(consumer, commit))
        except MissingConsumerCommit as error:
            diagnostics.append(
                Diagnostic(
                    "MISSING_CONSUMER_COMMIT",
                    consumer.commit_selector,
                    consumer.repo,
                    commit,
                    "<git-commit>",
                    commit,
                    "<missing>",
                    str(error),
                )
            )

    # Claims are exact value spans. The fallback sweep requires precisely one
    # manifest classification for every candidate-lock value found in a consumer.
    claims: dict[tuple[str, str, int, int], list[str]] = {}
    for rule in manifest.rules:
        commit = commits.get(rule.consumer_repo, "<missing>")
        if rule.consumer_repo not in trees:
            # Consumer resolution already emitted the root-cause diagnostic.
            continue
        expected_value = fields.get(rule.platform_field)
        if not isinstance(expected_value, str) or (
            rule.kind == "reference" and expected_value not in hex_values
        ):
            diagnostics.append(
                Diagnostic(
                    "MALFORMED_MANIFEST",
                    rule.platform_field,
                    rule.consumer_repo,
                    commit,
                    rule.consumer_path,
                    "lock-string" if rule.kind == "mirror" else "40-or-64-hex-lock-value",
                    str(expected_value) if expected_value is not None else "<missing>",
                    f"rule {rule.rule_id} platform_field is absent or is not a swept lock value",
                )
            )
            continue
        alias_problem = None
        for alias in rule.aliases:
            if fields.get(alias) != expected_value:
                alias_problem = alias
                break
        if alias_problem is not None:
            diagnostics.append(
                Diagnostic(
                    "MALFORMED_MANIFEST",
                    rule.platform_field,
                    rule.consumer_repo,
                    commit,
                    rule.consumer_path,
                    expected_value,
                    str(fields.get(alias_problem, "<missing>")),
                    f"rule {rule.rule_id} alias {alias_problem} does not equal the primary field",
                )
            )
            continue
        tree = trees.get(rule.consumer_repo)
        content = tree.get(rule.consumer_path) if tree is not None else None
        matches = _rule_matches(rule, content) if content is not None else []
        if rule.kind == "mirror":
            assert rule.expected_matches is not None
            if len(matches) < rule.expected_matches:
                actual = matches[0][2] if matches else "<missing>"
                diagnostics.append(
                    Diagnostic(
                        "MISSING_MIRROR",
                        rule.platform_field,
                        rule.consumer_repo,
                        commit,
                        rule.consumer_path,
                        expected_value,
                        actual,
                        f"rule {rule.rule_id} expected {rule.expected_matches} match(es), found {len(matches)}",
                    )
                )
            elif len(matches) > rule.expected_matches:
                diagnostics.append(
                    Diagnostic(
                        "AMBIGUOUS_MIRROR",
                        rule.platform_field,
                        rule.consumer_repo,
                        commit,
                        rule.consumer_path,
                        expected_value,
                        ",".join(match[2] for match in matches),
                        f"rule {rule.rule_id} expected {rule.expected_matches} match(es), found {len(matches)}",
                    )
                )
            for start, end, actual in matches:
                if actual != expected_value:
                    diagnostics.append(
                        Diagnostic(
                            "STALE_MIRROR",
                            rule.platform_field,
                            rule.consumer_repo,
                            commit,
                            rule.consumer_path,
                            expected_value,
                            actual,
                            f"rule {rule.rule_id} comparison={rule.comparison}",
                        )
                    )
                    continue
                claims.setdefault((rule.consumer_repo, rule.consumer_path, start, end), []).append(
                    rule.rule_id
                )
        else:
            for start, end, actual in matches:
                if actual == expected_value:
                    claims.setdefault((rule.consumer_repo, rule.consumer_path, start, end), []).append(
                        rule.rule_id
                    )

    classified_hits = 0
    for repo, tree in trees.items():
        commit = commits[repo]
        for path, content in tree.items():
            for match in HEX_RE.finditer(content):
                actual = match.group(0).lower()
                candidate_fields = hex_values.get(actual)
                if not candidate_fields:
                    continue
                hit_claims = claims.get((repo, path, match.start(), match.end()), [])
                if len(hit_claims) == 1:
                    classified_hits += 1
                    continue
                platform_field = ",".join(candidate_fields)
                if not hit_claims:
                    classification = "AMBIGUOUS_HIT" if len(candidate_fields) > 1 else "UNDECLARED_HIT"
                    detail = "no manifest rule classifies this hit"
                else:
                    classification = "AMBIGUOUS_HIT"
                    detail = f"multiple manifest rules classify this hit: {','.join(hit_claims)}"
                diagnostics.append(
                    Diagnostic(
                        classification,
                        platform_field,
                        repo,
                        commit,
                        path,
                        actual,
                        actual,
                        detail,
                    )
                )

    return GateResult(tuple(diagnostics), classified_hit_count=classified_hits, **base_counts)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default="platform.lock", help="candidate platform.lock")
    parser.add_argument(
        "--manifest", default="ci/lock-mirrors.toml", help="declared consumer mirror manifest"
    )
    parser.add_argument(
        "--baseline-manifest",
        help="manifest extracted from the verified exact base commit",
    )
    parser.add_argument(
        "--baseline-commit",
        required=True,
        help="authoritative exact PR base (or push before) commit",
    )
    parser.add_argument(
        "--bootstrap-missing-baseline",
        action="store_true",
        help="allow the one admitted introductory base that predates the manifest",
    )
    args = parser.parse_args(argv)
    baseline_raw: bytes | None = None
    if not COMMIT_RE.fullmatch(args.baseline_commit):
        baseline_status = f"lock-mirror baseline: FAIL base={args.baseline_commit}"
        result = _baseline_error("baseline commit must be an exact 40-hex SHA", args.baseline_commit)
    elif args.baseline_manifest and args.bootstrap_missing_baseline:
        baseline_status = f"lock-mirror baseline: FAIL base={args.baseline_commit}"
        result = _baseline_error(
            "baseline manifest and bootstrap flag are mutually exclusive", args.baseline_commit
        )
    elif args.bootstrap_missing_baseline:
        baseline_status = f"lock-mirror baseline: BOOTSTRAP base={args.baseline_commit}"
        if args.baseline_commit != BOOTSTRAP_BASE_COMMIT:
            result = _baseline_error(
                f"bootstrap is allowed only for exact introductory base {BOOTSTRAP_BASE_COMMIT}",
                args.baseline_commit,
            )
        else:
            result = None
    elif not args.baseline_manifest:
        baseline_status = f"lock-mirror baseline: FAIL base={args.baseline_commit}"
        result = _baseline_error(
            "verified exact-base manifest is required after the introductory bootstrap",
            args.baseline_commit,
        )
    else:
        try:
            baseline_raw = Path(args.baseline_manifest).read_bytes()
        except OSError as error:
            baseline_status = f"lock-mirror baseline: FAIL base={args.baseline_commit}"
            result = _baseline_error(str(error), args.baseline_commit, args.baseline_manifest)
        else:
            baseline_status = f"lock-mirror baseline: VERIFIED base={args.baseline_commit}"
            result = None
    if result is None:
        try:
            lock_raw = Path(args.lock).read_bytes()
        except OSError as error:
            result = _lock_error(str(error), args.lock)
        else:
            try:
                manifest_raw = Path(args.manifest).read_bytes()
            except OSError as error:
                result = _manifest_error(str(error), args.manifest)
            else:
                with GitCommitResolver(temp_root=os.environ.get("RUNNER_TEMP")) as resolver:
                    result = check_gate(
                        lock_raw,
                        manifest_raw,
                        resolver,
                        baseline_manifest_raw=baseline_raw,
                        baseline_commit=args.baseline_commit,
                    )
    stream = sys.stdout if result.ok else sys.stderr
    stream.write(baseline_status + "\n")
    stream.write(result.render() + "\n")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
