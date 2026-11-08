#!/usr/bin/env python3
"""Cross-repo app-descriptor drift corpus (v3 fetch).

The corpus in ``regression/abi/fixtures/app-schema-corpus`` is stored
byte-identically in pocketforge-os/platform and pocketforge-os/runtime
(``crates/pf-app-manifest/tests/fixtures/app-schema-corpus``). It pins the
descriptors the image and MBHaxe ship today plus one positive and one negative
schema_version 3 case per fetch rule. ``expected.json`` records the corpus
sha256 and the expected verdict for every descriptor, so the runtime parser and
``abi/app.schema.json`` cannot drift apart silently.

Standard-library only. When the reference ``jsonschema`` package is importable
the schema is additionally checked with it; otherwise (the CI contract) a small
Draft 2020-12 interpreter covers the keywords this schema uses. Set
``PF_SCHEMA_FORCE_STDLIB=1`` to exercise the interpreter locally.
"""

import hashlib
import json
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CORPUS = os.path.join(HERE, "fixtures", "app-schema-corpus")
SCHEMA_PATH = os.path.join(ROOT, "abi", "app.schema.json")

FAILS = 0


def check(ok, label, detail=""):
    global FAILS
    if ok:
        print(f"ok   {label}")
    else:
        FAILS += 1
        print(f"FAIL {label}" + (f": {detail}" if detail else ""))


def described_files():
    base = os.path.join(CORPUS, "descriptors")
    found = []
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            path = os.path.join(dirpath, name)
            relative = os.path.relpath(path, base).replace(os.sep, "/")
            found.append((relative, path))
    return sorted(found)


def corpus_digest():
    digest = hashlib.sha256()
    for relative, path in described_files():
        digest.update(relative.encode())
        digest.update(b"\0")
        with open(path, "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()


# --- minimal Draft 2020-12 interpreter (the keywords abi/app.schema.json uses) ---


def _join(path, part):
    return f"{path}.{part}" if path else str(part)


def _resolve(root, ref):
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported $ref {ref}")
    node = root
    for token in ref[2:].split("/"):
        node = node[token.replace("~1", "/").replace("~0", "~")]
    return node


def _type_ok(value, name):
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    raise ValueError(f"unsupported schema type {name}")


def validate(instance, schema, root, path=""):
    """Return a list of (instance-path, message) schema violations."""
    errors = []
    if isinstance(schema, bool):
        return [] if schema else [(path, "false schema")]
    if not isinstance(schema, dict):
        return errors

    if "$ref" in schema:
        errors.extend(validate(instance, _resolve(root, schema["$ref"]), root, path))
    for subschema in schema.get("allOf", []):
        errors.extend(validate(instance, subschema, root, path))
    if "anyOf" in schema:
        if not any(not validate(instance, sub, root, path) for sub in schema["anyOf"]):
            errors.append((path, "does not match any anyOf branch"))
    if "not" in schema:
        if not validate(instance, schema["not"], root, path):
            errors.append((path, "matches a forbidden schema"))
    if "if" in schema:
        branch = "then" if not validate(instance, schema["if"], root, path) else "else"
        if branch in schema:
            errors.extend(validate(instance, schema[branch], root, path))

    if "type" in schema:
        declared = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(instance, name) for name in declared):
            errors.append((path, f"expected type {schema['type']}"))
    if "enum" in schema and instance not in schema["enum"]:
        errors.append((path, f"{instance!r} is not one of {schema['enum']!r}"))
    if "const" in schema and instance != schema["const"]:
        errors.append((path, f"expected const {schema['const']!r}"))
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append((path, "string is too short"))
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append((path, f"does not match {schema['pattern']!r}"))
    if isinstance(instance, int) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append((path, f"below minimum {schema['minimum']}"))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append((path, f"above maximum {schema['maximum']}"))

    if isinstance(instance, dict):
        for name in schema.get("required", []):
            if name not in instance:
                errors.append((path, f"missing required property {name!r}"))
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for name, value in instance.items():
            if name in properties:
                errors.extend(
                    validate(value, properties[name], root, _join(path, name))
                )
            elif additional is False:
                errors.append((path, f"unexpected property {name!r}"))
            elif isinstance(additional, dict):
                errors.extend(validate(value, additional, root, _join(path, name)))

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append((path, "array has too few items"))
        if schema.get("uniqueItems"):
            for index, value in enumerate(instance):
                if value in instance[:index]:
                    errors.append((path, f"duplicate item {value!r}"))
        items = schema.get("items")
        if isinstance(items, (dict, bool)):
            for index, value in enumerate(instance):
                errors.extend(validate(value, items, root, _join(path, index)))
    return errors


def schema_errors(instance, schema):
    if not os.environ.get("PF_SCHEMA_FORCE_STDLIB"):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            pass
        else:
            validator = Draft202012Validator(schema)
            return [
                (".".join(str(part) for part in error.absolute_path), error.message)
                for error in validator.iter_errors(instance)
            ]
    return validate(instance, schema, schema)


def main():
    with open(os.path.join(CORPUS, "expected.json"), encoding="utf-8") as handle:
        table = json.load(handle)
    with open(SCHEMA_PATH, encoding="utf-8") as handle:
        schema = json.load(handle)

    force_stdlib = bool(os.environ.get("PF_SCHEMA_FORCE_STDLIB"))
    try:
        if force_stdlib:
            raise ImportError
        from jsonschema import Draft202012Validator  # noqa: F401

        engine = "jsonschema Draft202012Validator"
    except ImportError:
        engine = "bundled Draft 2020-12 interpreter"
    print(f"app-schema corpus verdicts via {engine}")

    check(
        len(table["cases"]) == len(described_files()),
        "expected table lists every corpus descriptor",
        f"{len(table['cases'])} cases, {len(described_files())} files",
    )
    check(
        corpus_digest() == table["corpus_sha256"],
        "corpus sha256 matches the expected table",
        f"computed {corpus_digest()}",
    )

    for case in table["cases"]:
        relative = case["path"]
        path = os.path.join(CORPUS, "descriptors", relative)
        with open(path, "rb") as handle:
            descriptor = tomllib.loads(handle.read().decode("utf-8"))
        errors = schema_errors(descriptor, schema)
        if case["expect"] == "accept":
            check(
                not errors,
                f"{relative}: accepted",
                "; ".join(f"{where}: {message}" for where, message in errors[:3]),
            )
        elif case["expect"] == "refuse":
            check(
                bool(errors),
                f"{relative}: refused ({case['reason']})",
                "schema accepted the descriptor",
            )
            wanted = case["schema_path"]
            matched = any(
                where == wanted or where.startswith(wanted + ".")
                for where, _message in errors
            )
            check(
                matched,
                f"{relative}: refusal names {wanted}",
                "errors at " + ", ".join(sorted({where for where, _ in errors})[:5]),
            )
        else:
            check(False, f"{relative}: unknown expectation {case['expect']!r}")

    if FAILS:
        print(f"\n{FAILS} check(s) failed")
        return 1
    print(f"\nall {len(table['cases']) * 2 + 2} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())