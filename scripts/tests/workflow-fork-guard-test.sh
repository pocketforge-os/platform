#!/usr/bin/env bash
# Reject pull_request-reachable self-hosted jobs that can run code from forks.
set -euo pipefail

repo="${PF_WORKFLOW_FORK_GUARD_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
python3 - "$repo/.github/workflows" <<'PY'
import pathlib
import re
import socket
import sys

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


def has_fork_guard(expression):
    compact = re.sub(r"\s+", "", expression)
    event_halves = ("github.event_name!='pull_request'", 'github.event_name!="pull_request"')
    repo_halves = (
        "github.event.pull_request.head.repo.full_name==github.repository",
        "github.repository==github.event.pull_request.head.repo.full_name",
    )
    # Require the two halves to form one OR term. Merely finding both tokens in
    # unrelated branches could credit an expression that still admits a fork PR.
    return any(
        f"{event_half}||{repo_half}" in compact
        for event_half in event_halves
        for repo_half in repo_halves
    )


def excludes_pull_requests(expression):
    # An OR can reopen the PR path, so only credit a required non-PR event predicate
    # in an AND-only expression. This is deliberately conservative and fail-closed.
    if "||" in expression:
        return False
    compact = re.sub(r"\s+", "", expression)
    if "github.event_name!='pull_request'" in compact or 'github.event_name!="pull_request"' in compact:
        return True
    matches = re.findall(r"github\.event_name==(['\"])([^'\"]+)\1", compact)
    return bool(matches) and all(event != "pull_request" for _, event in matches)


files = sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")))
if not files:
    raise SystemExit(f"ERROR: inspected zero workflows under {workflow_dir}")

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

if failures:
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    raise SystemExit(1)
print(f"PASS: all {checked} pull_request-reachable self-hosted jobs are fork-guarded or restricted to non-PR events")
PY
