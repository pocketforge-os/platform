#!/usr/bin/env python3
"""Check that every family capability is known by the exactly pinned runtime."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import tomllib
from typing import Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_lock_mirrors import Consumer, ConsumerResolver, GitCommitResolver, MissingConsumerCommit


RUNTIME_SOURCE = "crates/pf-app-manifest/src/lib.rs"
COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def runtime_pin(lock_raw: bytes) -> tuple[str, str]:
    data = tomllib.loads(lock_raw.decode("utf-8"))
    matches = [repo for repo in data.get("repos", []) if repo.get("name") == "runtime"]
    if len(matches) != 1:
        raise ValueError(f"platform.lock must contain exactly one runtime repo, found {len(matches)}")
    url = matches[0].get("url")
    commit = matches[0].get("sha")
    if not isinstance(url, str) or not url:
        raise ValueError("runtime repo URL is missing")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise ValueError("runtime repo SHA is not an exact 40-hex commit")
    return url, commit


def family_capabilities(families_raw: bytes) -> set[str]:
    data = tomllib.loads(families_raw.decode("utf-8"))
    capabilities: set[str] = set()
    for family in data.get("family", []):
        app_runtime = family.get("app_runtime")
        if app_runtime is None:
            continue
        values = app_runtime.get("supported_capabilities")
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValueError("family app_runtime.supported_capabilities must be a string list")
        capabilities.update(values)
    return capabilities


def runtime_capabilities(source: bytes) -> set[str]:
    text = source.decode("utf-8")
    match = re.search(
        r"pub\s+const\s+KNOWN_CAPABILITIES\s*:[^=]+?=\s*&\[(.*?)\];",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise ValueError(f"{RUNTIME_SOURCE} has no KNOWN_CAPABILITIES string array")
    body = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.DOTALL)
    body = re.sub(r"//[^\n]*", "", body)
    values = re.findall(r'"([a-z][a-z0-9_]*)"', body)
    if not values or len(values) != len(set(values)):
        raise ValueError(f"{RUNTIME_SOURCE} KNOWN_CAPABILITIES is empty or contains duplicates")
    return set(values)


def check_contract(
    lock_raw: bytes,
    families_raw: bytes,
    resolver: ConsumerResolver,
) -> tuple[str, set[str], set[str]]:
    url, commit = runtime_pin(lock_raw)
    consumer = Consumer("runtime", url, "repos.runtime.sha")
    tree: Mapping[str, bytes] = resolver.read_tree(consumer, commit)
    source = tree.get(RUNTIME_SOURCE)
    if source is None:
        raise ValueError(f"pinned runtime lacks {RUNTIME_SOURCE}")
    admitted = family_capabilities(families_raw)
    known = runtime_capabilities(source)
    unknown = admitted - known
    if unknown:
        raise ValueError(
            "families.toml admits capabilities unknown to pinned runtime "
            f"{commit}: {', '.join(sorted(unknown))}"
        )
    return commit, admitted, known


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default="platform.lock")
    parser.add_argument("--families", default="abi/families.toml")
    args = parser.parse_args(argv)
    try:
        with GitCommitResolver() as resolver:
            commit, admitted, known = check_contract(
                Path(args.lock).read_bytes(), Path(args.families).read_bytes(), resolver
            )
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError,
            MissingConsumerCommit, ValueError) as error:
        print(f"FATAL: runtime capability contract: {error}", file=sys.stderr)
        return 1
    print(
        "runtime-capability-contract=PASS "
        f"runtime={commit} admitted={len(admitted)} known={len(known)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
