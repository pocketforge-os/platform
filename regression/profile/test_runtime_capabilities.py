#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "runtime_capabilities", ROOT / "ci/check_runtime_capabilities.py"
)
runtime_capabilities = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime_capabilities)

RUNTIME_SHA = "1" * 40
RUNTIME_URL = "https://github.com/pocketforge-os/runtime.git"
LOCK = f'''\
[[repos]]
name = "runtime"
url = "{RUNTIME_URL}"
sha = "{RUNTIME_SHA}"
'''.encode()
FAMILIES = b'''\
[[family]]
id = "pocketforge/test"
[family.app_runtime]
supported_capabilities = ["audio", "open_url"]
'''


def runtime_source(*capabilities: str) -> bytes:
    values = "\n".join(f'    "{capability}",' for capability in capabilities)
    return f'''\
pub const KNOWN_CAPABILITIES: &[&str] = &[
    // A quoted comment must not become vocabulary: "comment_only".
{values}
];
'''.encode()


class Resolver:
    def __init__(self, source: bytes):
        self.source = source
        self.requests = []

    def read_tree(self, consumer, commit):
        self.requests.append((consumer.repo, consumer.url, commit))
        return {runtime_capabilities.RUNTIME_SOURCE: self.source}


class RuntimeCapabilityContractTests(unittest.TestCase):
    def test_family_capabilities_must_be_known_by_exact_pinned_runtime(self):
        resolver = Resolver(runtime_source("audio"))
        with self.assertRaisesRegex(
            ValueError,
            f"unknown to pinned runtime {RUNTIME_SHA}: open_url",
        ):
            runtime_capabilities.check_contract(LOCK, FAMILIES, resolver)
        self.assertEqual(resolver.requests, [("runtime", RUNTIME_URL, RUNTIME_SHA)])

        resolver = Resolver(runtime_source("audio", "open_url", "settings"))
        commit, admitted, known = runtime_capabilities.check_contract(
            LOCK, FAMILIES, resolver
        )
        self.assertEqual(commit, RUNTIME_SHA)
        self.assertEqual(admitted, {"audio", "open_url"})
        self.assertEqual(known, {"audio", "open_url", "settings"})

    def test_runtime_vocabulary_parser_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no KNOWN_CAPABILITIES"):
            runtime_capabilities.runtime_capabilities(b"pub const OTHER: &[&str] = &[];")
        with self.assertRaisesRegex(ValueError, "contains duplicates"):
            runtime_capabilities.runtime_capabilities(runtime_source("audio", "audio"))


if __name__ == "__main__":
    unittest.main()
