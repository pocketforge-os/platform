#!/usr/bin/env bash
# Reject pull_request-reachable self-hosted jobs that can run code from forks.
set -euo pipefail

repo="${PF_WORKFLOW_FORK_GUARD_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
python3 - "$repo/.github/workflows" "${1:-}" <<'PY'
import pathlib
import re
import socket
import sys
import tempfile

try:
    import yaml
except ImportError:
    raise SystemExit(
        "ERROR: PyYAML is required for the workflow fork guard; "
        f"missing in {sys.executable} on {socket.gethostname()}"
    )

workflow_dir = pathlib.Path(sys.argv[1])
if not workflow_dir.is_dir():
    raise SystemExit(f"ERROR: workflow directory is missing: {workflow_dir}")


class DuplicateKeyError(yaml.YAMLError):
    pass


class UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in mapping:
                raise DuplicateKeyError(f"duplicate mapping key {key!r}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def workflow_events(document):
    # PyYAML 1.1 resolves the plain scalar `on` as True.
    value = document.get("on", document.get(True))
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return set(value)
    if isinstance(value, dict):
        return set(value)
    raise ValueError("missing or unsupported on trigger")


def is_self_hosted(runs_on):
    if isinstance(runs_on, str):
        labels = [runs_on]
    elif isinstance(runs_on, list) and all(isinstance(label, str) for label in runs_on):
        labels = runs_on
    else:
        raise ValueError("runs-on must be a string or string sequence")
    return "self-hosted" in labels


def expression_text(value):
    if not isinstance(value, str):
        raise ValueError("job if must be a string")
    value = value.strip()
    if value.startswith("${{") and value.endswith("}}"):
        value = value[3:-2].strip()
    return value


def logical_operators(expression):
    """Return (operator, nesting depth) pairs outside quoted strings."""
    operators = []
    depth = 0
    quote = None
    index = 0
    while index < len(expression):
        char = expression[index]
        if quote:
            if char == quote and (index == 0 or expression[index - 1] != "\\"):
                quote = None
            index += 1
            continue
        if char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("job if has unbalanced parentheses")
        elif expression[index:index + 2] in ("&&", "||"):
            operators.append((expression[index:index + 2], depth))
            index += 1
        index += 1
    if quote:
        raise ValueError("job if has an unterminated quote")
    if depth:
        raise ValueError("job if has unbalanced parentheses")
    return operators


def strip_outer_parentheses(expression):
    expression = expression.strip()
    while expression.startswith("(") and expression.endswith(")"):
        logical_operators(expression)
        depth = 0
        encloses_all = True
        quote = None
        for index, char in enumerate(expression):
            if quote:
                if char == quote and expression[index - 1] != "\\":
                    quote = None
                continue
            if char in "'\"":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(expression) - 1:
                    encloses_all = False
                    break
        if not encloses_all:
            break
        expression = expression[1:-1].strip()
    return expression


def split_top_level(expression, operator):
    logical_operators(expression)  # Validate before splitting.
    parts = []
    start = 0
    depth = 0
    quote = None
    index = 0
    while index < len(expression):
        char = expression[index]
        if quote:
            if char == quote and (index == 0 or expression[index - 1] != "\\"):
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and expression[index:index + 2] == operator:
            parts.append(expression[start:index].strip())
            start = index + 2
            index += 1
        index += 1
    parts.append(expression[start:].strip())
    return parts


def compact_atom(expression):
    return re.sub(r"\s+", "", strip_outer_parentheses(expression))


def has_fork_guard(expression):
    event_halves = {"github.event_name!='pull_request'", 'github.event_name!="pull_request"'}
    repo_halves = {
        "github.event.pull_request.head.repo.full_name==github.repository",
        "github.repository==github.event.pull_request.head.repo.full_name",
    }
    # The canonical disjunction must be a complete AND term. A sibling OR branch
    # widens the condition and can admit a fork PR; sibling AND terms only constrain it.
    for term in split_top_level(expression, "&&"):
        branches = split_top_level(strip_outer_parentheses(term), "||")
        if len(branches) != 2:
            continue
        atoms = {compact_atom(branch) for branch in branches}
        if len(atoms & event_halves) == 1 and len(atoms & repo_halves) == 1:
            return True
    return False


def excludes_pull_requests(expression):
    # An OR can reopen the PR path, so only credit a required non-PR event predicate
    # in an AND-only expression. This is deliberately conservative and fail-closed.
    if any(operator == "||" for operator, _ in logical_operators(expression)):
        return False
    atoms = [compact_atom(term) for term in split_top_level(expression, "&&")]
    if any(atom in ("github.event_name!='pull_request'", 'github.event_name!="pull_request"') for atom in atoms):
        return True
    matches = [
        match
        for atom in atoms
        if (match := re.fullmatch(r"github\.event_name==(['\"])([^'\"]+)\1", atom))
    ]
    return bool(matches) and all(match.group(2) != "pull_request" for match in matches)


def inspect_workflows(workflow_dir):
    files = sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")))
    if not files:
        return [f"ERROR: inspected zero workflows under {workflow_dir}"], 0

    failures = []
    checked = 0
    for workflow in files:
        try:
            document = yaml.load(workflow.read_text(encoding="utf-8"), Loader=UniqueKeySafeLoader)
            if not isinstance(document, dict):
                raise ValueError("workflow root must be a mapping")
            events = workflow_events(document)
            jobs = document.get("jobs")
            if not isinstance(jobs, dict) or not jobs:
                raise ValueError("jobs must be a non-empty mapping")
        except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
            failures.append(f"{workflow}: {exc}")
            continue

        if "pull_request" not in events:
            continue
        for job_name, job in jobs.items():
            try:
                if not isinstance(job_name, str) or not isinstance(job, dict):
                    raise ValueError("job definition must be a mapping")
                if "runs-on" not in job or not is_self_hosted(job["runs-on"]):
                    continue
                checked += 1
                condition = expression_text(job.get("if", ""))
                if not (has_fork_guard(condition) or excludes_pull_requests(condition)):
                    failures.append(
                        f"{workflow}: job {job_name}: pull_request-reachable self-hosted job "
                        "lacks a fork guard or non-PR event restriction"
                    )
            except ValueError as exc:
                failures.append(f"{workflow}: job {job_name}: {exc}")
    return failures, checked


def run_self_test():
    cases = {
        "canonical": ("github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository", True),
        "constrained": ("(github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) && github.actor != 'blocked'", True),
        "widened": ("github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository || github.actor == 'dependabot[bot]'", False),
        "dispatch_only": ("github.event_name == 'workflow_dispatch'", True),
        "dispatch_reopened": ("github.event_name == 'workflow_dispatch' || github.actor == 'dependabot[bot]'", False),
        "unguarded": ("github.actor != 'blocked'", False),
    }
    with tempfile.TemporaryDirectory(prefix="workflow-fork-guard-") as temporary:
        workflow_dir = pathlib.Path(temporary)
        jobs = []
        for name, (condition, _) in cases.items():
            jobs.append(
                f"  {name}:\n"
                f"    if: >-\n      {condition}\n"
                "    runs-on: [self-hosted, test]\n"
                "    steps: []\n"
            )
        (workflow_dir / "fixture.yml").write_text(
            "on: [pull_request, workflow_dispatch]\njobs:\n" + "".join(jobs),
            encoding="utf-8",
        )
        failures, checked = inspect_workflows(workflow_dir)
    failed_jobs = {failure.split("job ", 1)[1].split(":", 1)[0] for failure in failures}
    expected_failures = {name for name, (_, accepted) in cases.items() if not accepted}
    if checked != len(cases) or failed_jobs != expected_failures:
        raise SystemExit(
            f"SELF-TEST FAIL: checked={checked}; expected failures={sorted(expected_failures)}; "
            f"actual failures={sorted(failed_jobs)}"
        )
    print("SELF-TEST PASS: widening OR branches rejected; canonical, constraining AND, and non-PR predicates accepted")


if sys.argv[2] == "--self-test":
    run_self_test()
    raise SystemExit(0)

failures, checked = inspect_workflows(workflow_dir)
if failures:
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    raise SystemExit(1)
print(f"PASS: all {checked} pull_request-reachable self-hosted jobs are fork-guarded or restricted to non-PR events")
PY
