#!/usr/bin/env python3
"""Problem report v1 contract tests (tsp-ihne1.37).

Fixtures are the shared truth: the runtime crate pf-problem-report reads the
same files and must reach the same verdicts. Property tests use a seeded
generator so a failure prints a reproducible case.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import random
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("problem_report", ROOT / "problem_report.py")
pr = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(pr)

VALID = sorted((ROOT / "fixtures/valid").glob("*.json"))
INVALID = sorted((ROOT / "fixtures/invalid").glob("*.json"))
SEED = 0x1D37
CASES = 400


def refusal(test: unittest.TestCase, data: bytes) -> str:
    with test.assertRaises(pr.Refused) as raised:
        pr.decode(data)
    return raised.exception.reason


def random_report(rng: random.Random, kind: str | None = None) -> dict:
    """A valid report in the JSON mapping, drawn across every bounded field."""
    kind = kind or rng.choice(pr.KINDS)
    word = "abcdefghijklmnopqrstuvwxyz0123456789"

    def label(n: int) -> str:
        inner = "".join(rng.choice(word + "_-") for _ in range(max(0, n - 2)))
        edge = rng.choice(word)
        return edge if n == 1 else edge + inner + rng.choice(word)

    def app_id() -> str:
        return ".".join(label(rng.randint(1, 20)) for _ in range(rng.randint(2, 6)))

    def frame() -> list:
        if rng.random() < 0.25:
            return [None, None]
        size = rng.choice([8, 16, 20, 32])
        return [bytes(rng.getrandbits(8) for _ in range(size)).hex(), rng.randrange(0, pr.MAX_OFFSET + 1)]

    report: dict = {
        "v": 1,
        "kind": kind,
        "how": rng.choice(pr.HOW[kind]),
        "day": "%04d-%02d-%02d" % (rng.randint(2020, 2099), rng.randint(1, 12), rng.randint(1, 28)),
        "build": "".join(rng.choice("0123456789abcdef") for _ in range(12)),
        "model": rng.choice(["a133", "a523", "trimui-smart-pro", "trimui-smart-pro-s"]),
        "uptime": rng.choice(pr.BUCKETS),
        "del": bytes(rng.getrandbits(8) for _ in range(32)).hex(),
    }
    if kind == "kernel":
        kframes = []
        for _ in range(rng.randint(0, pr.MAX_KFRAMES)):
            module = None if rng.random() < 0.5 else "".join(rng.choice(word + "_") for _ in range(rng.randint(1, 24)))
            kframes.append([
                "".join(rng.choice(word + "_") for _ in range(rng.randint(1, 48))),
                rng.randrange(0, 2**32),
                rng.randrange(0, 2**32),
                module,
            ])
        report["kframes"] = kframes
        return report
    origin = "image" if kind == "component" else rng.choice(pr.ORIGINS)
    app: dict = {"origin": origin}
    if origin != "sideloaded":
        app["id"] = app_id()
        if origin == "catalog" or rng.random() < 0.5:
            app["ver"] = ".".join(str(rng.randint(0, 99999)) for _ in range(rng.randint(1, 4)))
    report["app"] = app
    report["session"] = rng.choice(pr.BUCKETS)
    report["mem"] = {"pressure": rng.random() < 0.5, "oom": kind == "oom" or rng.random() < 0.2}
    if kind == "hang":
        samples = [rng.randint(1, 24) for _ in range(rng.randint(0, 2))]
        report["samples"] = samples
        report["frames"] = [frame() for _ in range(sum(samples))]
    else:
        report["frames"] = [frame() for _ in range(rng.randint(0, pr.MAX_FRAMES))]
    if kind in ("crash", "component") and origin == "image" and report["how"] == "SIGABRT" and rng.random() < 0.5:
        report["panic_at"] = "crates/pf-%s/src/%s.rs:%d:%d" % (label(8), label(6), rng.randint(1, 99999), rng.randint(1, 999))
    return report


class FixtureTest(unittest.TestCase):
    def test_fixture_sets_cover_every_kind_and_typed_unknown_frames(self) -> None:
        kinds = set()
        unknown = False
        for path in VALID:
            report = json.loads(path.read_text())["report"]
            kinds.add(report["kind"])
            unknown |= [None, None] in report.get("frames", [])
        self.assertEqual(set(pr.KINDS), kinds)
        self.assertTrue(unknown, "no valid fixture carries a typed unknown frame")
        reasons = {json.loads(p.read_text())["expected_reason"] for p in INVALID}
        self.assertEqual(set(pr.REASONS), reasons, "every refusal reason needs an invalid fixture")

    def test_valid_fixtures_encode_to_their_canonical_bytes_and_round_trip(self) -> None:
        self.assertTrue(VALID)
        for path in VALID:
            with self.subTest(fixture=path.name):
                fixture = json.loads(path.read_text())
                data = bytes.fromhex(fixture["cbor_hex"])
                self.assertEqual(data, pr.encode(fixture["report"]))
                self.assertLessEqual(len(data), pr.MAX_BYTES)
                self.assertEqual(fixture["report"], pr.decode(data))

    def test_invalid_fixtures_are_refused_with_their_typed_reason(self) -> None:
        self.assertTrue(INVALID)
        for path in INVALID:
            with self.subTest(fixture=path.name):
                fixture = json.loads(path.read_text())
                if "cbor_hex" in fixture:
                    data = bytes.fromhex(fixture["cbor_hex"])
                else:
                    data = pr.encode_generic(pr.from_tagged_json(fixture["report"]))
                self.assertIn(fixture["expected_reason"], pr.REASONS)
                self.assertEqual(fixture["expected_reason"], refusal(self, data))

    def test_encoder_refuses_what_the_decoder_refuses(self) -> None:
        good = json.loads(VALID[0].read_text())["report"]
        bad = dict(good, hostname="pocket")
        with self.assertRaises(pr.Refused) as raised:
            pr.encode(bad)
        self.assertEqual("unknown-field", raised.exception.reason)
        pr.encode(good)  # positive control in the same invocation


class PropertyTest(unittest.TestCase):
    def test_every_valid_report_fits_and_round_trips(self) -> None:
        rng = random.Random(SEED)
        largest = 0
        for case in range(CASES):
            report = random_report(rng, pr.KINDS[case % len(pr.KINDS)])
            with self.subTest(case=case, report=json.dumps(report)):
                data = pr.encode(report)
                largest = max(largest, len(data))
                self.assertLessEqual(len(data), pr.MAX_BYTES)
                self.assertEqual(report, pr.decode(data))
                self.assertEqual(data, pr.encode(pr.decode(data)))
        self.assertGreater(largest, 1000, "generator never approached the size bound")

    def test_worst_case_reports_fit_in_4_kib(self) -> None:
        for kind in pr.KINDS:
            with self.subTest(kind=kind):
                data = pr.encode(pr.worst_case(kind))
                self.assertLessEqual(len(data), pr.MAX_BYTES, "%s worst case is %d bytes" % (kind, len(data)))

    def test_unknown_fields_are_refused_at_every_map(self) -> None:
        rng = random.Random(SEED + 1)
        for case in range(CASES // 4):
            report = random_report(rng, pr.KINDS[case % len(pr.KINDS)])
            pr.encode(report)  # positive control
            for at in [None] + [k for k in ("app", "mem") if k in report]:
                with self.subTest(case=case, at=at):
                    mutated = copy.deepcopy(report)
                    where = mutated if at is None else mutated[at]
                    where[rng.choice(["comment", "hostname", "x", "path", "serial"])] = "pocket"
                    value = pr.to_tagged_value(mutated)
                    self.assertEqual("unknown-field", refusal(self, pr.encode_generic(value)))

    def test_out_of_vocabulary_values_are_refused(self) -> None:
        rng = random.Random(SEED + 2)
        mutations = [
            ("kind", ["panic", "Crash", "crash ", ""], "vocabulary"),
            ("how", ["SIGKILL", "sigsegv", "timeout", "segfault"], "vocabulary"),
            ("uptime", ["1–10m", "2m", "<1h", "unknown"], "vocabulary"),
        ]
        for case in range(CASES // 4):
            report = random_report(rng, pr.KINDS[case % len(pr.KINDS)])
            pr.encode(report)
            for field, values, reason in mutations:
                for value in values:
                    with self.subTest(case=case, field=field, value=value):
                        mutated = dict(report, **{field: value})
                        self.assertEqual(reason, refusal(self, pr.encode_generic(pr.to_tagged_value(mutated))))
            if "app" in report:
                with self.subTest(case=case, field="app.origin"):
                    mutated = copy.deepcopy(report)
                    mutated["app"]["origin"] = "sdcard"
                    self.assertEqual("vocabulary", refusal(self, pr.encode_generic(pr.to_tagged_value(mutated))))

    def test_free_text_is_refused_in_every_string_field(self) -> None:
        rng = random.Random(SEED + 3)
        texts = [
            "/home/gamer/roms/Secret Game.zip",
            "hello world",
            "user@example.com",
            "Wi-Fi: HomeNet",
            "café",
            "A" * 300,
        ]
        for case in range(CASES // 8):
            report = random_report(rng, pr.KINDS[case % len(pr.KINDS)])
            pr.encode(report)
            paths = [("day",), ("build",), ("model",)]
            if "app" in report and "id" in report["app"]:
                paths.append(("app", "id"))
            if "app" in report and "ver" in report["app"]:
                paths.append(("app", "ver"))
            if "panic_at" in report:
                paths.append(("panic_at",))
            for path in paths:
                for text in texts:
                    with self.subTest(case=case, path=path, text=text[:20]):
                        mutated = copy.deepcopy(report)
                        target = mutated
                        for key in path[:-1]:
                            target = target[key]
                        target[path[-1]] = text
                        self.assertEqual("grammar", refusal(self, pr.encode_generic(pr.to_tagged_value(mutated))))

    def test_truncations_are_refused_never_partially_read(self) -> None:
        rng = random.Random(SEED + 4)
        for case in range(CASES // 8):
            data = pr.encode(random_report(rng, pr.KINDS[case % len(pr.KINDS)]))
            pr.decode(data)
            for cut in sorted({1, len(data) // 2, len(data) - 1}):
                with self.subTest(case=case, cut=cut):
                    self.assertEqual("malformed", refusal(self, data[:cut]))
            with self.subTest(case=case, trailing=True):
                self.assertEqual("malformed", refusal(self, data + b"\x00"))


if __name__ == "__main__":
    unittest.main()
