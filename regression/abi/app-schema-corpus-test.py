#!/usr/bin/env python3
"""Cross-repo app-descriptor drift corpus (v3 fetch).

The corpus in ``regression/abi/fixtures/app-schema-corpus`` is stored
byte-identically in pocketforge-os/platform and pocketforge-os/runtime
(``crates/pf-app-manifest/tests/fixtures/app-schema-corpus``). It pins the
descriptors the image and MBHaxe ship today plus one positive and one negative
schema_version 3 case per fetch rule. ``expected.json`` records the corpus
sha256 and the expected verdict for every descriptor, so the runtime parser and
``abi/app.schema.json`` cannot drift apart silently.

Standard-library only (the regression-suites contract). Verdicts come from a
small bundled Draft 2020-12 interpreter that FAILS CLOSED: before validating,
the schema is walked and any keyword outside the interpreter's supported set
aborts the run with ``FAIL unsupported schema keyword: <kw> at <pointer>``.
When the reference ``jsonschema`` package is importable (it is on the CI
runner) every corpus case is validated with BOTH engines and any verdict
disagreement fails the run. ``PF_SCHEMA_FORCE_STDLIB=1`` skips the
cross-check locally.
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


SUPPORTED_KEYWORDS = {
    # annotations (no validation effect)
    "$schema", "$id", "$comment", "title", "description", "default", "examples",
    # applicators and assertions the interpreter implements
    "$ref", "$defs", "allOf", "anyOf", "not", "if", "then", "else",
    "type", "enum", "const", "minLength", "pattern", "minimum", "maximum",
    "required", "properties", "additionalProperties",
    "minItems", "uniqueItems", "items", "contains",
}


def unsupported_keywords(schema, pointer=""):
    """Return [(keyword, json-pointer)] for every keyword the interpreter lacks."""
    found = []
    if isinstance(schema, list):
        for index, sub in enumerate(schema):
            found.extend(unsupported_keywords(sub, f"{pointer}/{index}"))
        return found
    if not isinstance(schema, dict):
        return found
    for keyword, value in schema.items():
        here = f"{pointer}/{keyword}"
        if keyword not in SUPPORTED_KEYWORDS:
            found.append((keyword, here))
        elif keyword in ("properties", "$defs"):
            for name, sub in value.items():  # names, not keywords
                found.extend(unsupported_keywords(sub, f"{here}/{name}"))
        elif keyword in ("not", "if", "then", "else", "items", "contains",
                         "additionalProperties", "allOf", "anyOf"):
            found.extend(unsupported_keywords(value, here))
        # const/enum/default/examples hold instance data: do not descend
    return found


def require_supported(schema):
    bad = unsupported_keywords(schema)
    if bad:
        keyword, pointer = bad[0]
        print(f"FAIL unsupported schema keyword: {keyword} at {pointer or '/'}")
        return False
    return True


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
        if "contains" in schema and not any(
            not validate(value, schema["contains"], root, path) for value in instance
        ):
            errors.append((path, "no array item matches contains"))
        items = schema.get("items")
        if isinstance(items, (dict, bool)):
            for index, value in enumerate(instance):
                errors.extend(validate(value, items, root, _join(path, index)))
    return errors


def jsonschema_module():
    if os.environ.get("PF_SCHEMA_FORCE_STDLIB"):
        return None
    try:
        import jsonschema
    except ImportError:
        return None
    return jsonschema


def stdlib_errors(instance, schema):
    return validate(instance, schema, schema)


def reference_errors(jsonschema, instance, schema):
    validator = jsonschema.Draft202012Validator(schema)
    return [
        (".".join(str(part) for part in error.absolute_path), error.message)
        for error in validator.iter_errors(instance)
    ]


# Per-reason predicate over a (path, message) error from the stdlib interpreter,
# so a refusal for the wrong reason (e.g. the schema_version enum) does not pass.
REASON_MATCH = {
    "missing-size": lambda path, message: "'size'" in message,
    "invalid-include": lambda path, message: re.search(r"\.include(\.\d+)?$", path) is not None,
    "invalid-dest": lambda path, message: path.endswith(".dest"),
    "reserved-source": lambda path, message: "vendor-signed-pointer" in message
    or path.endswith("source"),
    "v3-only-include": lambda path, message: path == "fetch"
    and "forbidden" in message,
    "v3-only-source": lambda path, message: path == "fetch"
    and "forbidden" in message,
}


def self_test():
    """The guard must reject a schema using a keyword the interpreter lacks."""
    bad = {"type": "object", "properties": {"a": {"propertyNames": {"pattern": "^x"}}}}
    found = unsupported_keywords(bad)
    check(
        found == [("propertyNames", "/properties/a/propertyNames")],
        "self-test: unsupported keyword propertyNames is detected",
        repr(found),
    )
    good = {"properties": {"propertyNames": {"type": "string"}}}
    check(
        not unsupported_keywords(good),
        "self-test: a property merely named like a keyword is not flagged",
    )


def reason_separation_test(schema):
    """A v3-only refusal predicate must name its own offending property.

    The include and source cases used to share one predicate (both matched the
    single ``fetch`` error produced by a ``not``), so either reason satisfied
    either case. Prove on purpose-built v1 descriptors that the predicates are
    disjoint.
    """
    common = (
        '[app]\nid = "com.pocketforge.reason"\n'
        '[runtime]\nfamily = "pocketforge/a133-powervr"\nabi = "1"\n'
        '[fetch]\nenabled = true\n'
    )
    source = tomllib.loads(common + 'source = "pinned"\n')
    include = tomllib.loads(
        common
        + '[[fetch.files]]\nurl = "https://example.invalid/a.tar.gz"\n'
        + 'format = "tar.gz"\ninclude = ["data/"]\n'
    )
    for label, descriptor, own, other in (
        ("source", source, "v3-only-source", "v3-only-include"),
        ("include", include, "v3-only-include", "v3-only-source"),
    ):
        errors = stdlib_errors(descriptor, schema)
        check(
            any(REASON_MATCH[own](where, message) for where, message in errors),
            f"reason self-test: v1 {label} refusal matches {own}",
            repr(errors),
        )
        check(
            not any(REASON_MATCH[other](where, message) for where, message in errors),
            f"reason self-test: v1 {label} refusal does not match {other}",
            repr(errors),
        )


def main():
    with open(os.path.join(CORPUS, "expected.json"), encoding="utf-8") as handle:
        table = json.load(handle)
    with open(SCHEMA_PATH, encoding="utf-8") as handle:
        schema = json.load(handle)

    self_test()
    if not require_supported(schema):
        return 1
    reason_separation_test(schema)
    jsonschema = jsonschema_module()
    if jsonschema:
        from importlib import metadata

        version = metadata.version("jsonschema")
        print(f"verdicts via stdlib interpreter (cross-checked against jsonschema {version})")
    else:
        print("verdicts via stdlib interpreter (jsonschema not present; no cross-check)")

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
        errors = stdlib_errors(descriptor, schema)
        if jsonschema:
            reference = reference_errors(jsonschema, descriptor, schema)
            check(
                bool(errors) == bool(reference),
                f"{relative}: stdlib and jsonschema verdicts agree",
                f"stdlib {'refuse' if errors else 'accept'}, "
                f"jsonschema {'refuse' if reference else 'accept'}",
            )
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
            predicate = REASON_MATCH.get(case["reason"])
            check(
                predicate is not None
                and any(predicate(where, message) for where, message in errors),
                f"{relative}: refusal matches reason {case['reason']}",
                "; ".join(f"{where}: {message}" for where, message in errors[:3]),
            )
        else:
            check(False, f"{relative}: unknown expectation {case['expect']!r}")

    # schema_version 4 is refused by the parser with a message the shared
    # corpus has no reason class for, so it is pinned here, schema side only.
    v4 = tomllib.loads(
        'schema_version = 4\n[app]\nid = "com.pocketforge.v4"\nname = "V4"\n'
        '[runtime]\nfamily = "pocketforge/a133-powervr"\nabi = "1"\n'
    )
    v4_errors = stdlib_errors(v4, schema)
    check(
        any(where == "schema_version" for where, _ in v4_errors),
        "schema_version = 4: refused at schema_version",
        repr(v4_errors[:2]),
    )
    if jsonschema:
        check(
            bool(reference_errors(jsonschema, v4, schema)),
            "schema_version = 4: jsonschema refuses too",
        )

    if FAILS:
        print(f"\n{FAILS} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())