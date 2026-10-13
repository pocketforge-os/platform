#!/usr/bin/env python3
"""regression/abi/app-schema-test.py — JSON Schema validation of app.toml
against abi/app.schema.json. Exercises the schema_version and [display] additions
from tsp-mc9m.41.1026.4 / runtime#126. Plain asserts; exit 0 = all pass."""
import json, os, sys, tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SCHEMA_PATH = os.path.join(ROOT, "abi", "app.schema.json")

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"ok   - {name}")
    else:
        print(f"FAIL - {name} {detail}")
        FAILS.append(name)


def schema_errors(manifest_text):
    """Validate manifest_text (TOML) against the schema. Returns list of error
    messages ([] = valid). Falls back to a structural-only check when the reference
    jsonschema library is not importable (match the caps test convention)."""
    try:
        doc = tomllib.loads(manifest_text)
    except Exception as e:
        return [f"toml parse error: {e}"]
    try:
        schema = json.loads(open(SCHEMA_PATH).read())
    except Exception as e:
        return [f"schema load error: {e}"]
    try:
        import jsonschema
    except ImportError:
        return _schema_structural_check(doc, schema)
    validator = jsonschema.Draft202012Validator(schema)
    errs = list(validator.iter_errors(doc))
    return [e.message for e in errs]


def _schema_structural_check(doc, schema):
    """Minimal structural check when jsonschema is not available: enforce
    additionalProperties. Not exhaustive but catches the key cases."""
    errs = []
    props = schema.get("properties", {})
    ap = schema.get("additionalProperties", False)
    if ap is False:
        for key in doc:
            if key not in props:
                errs.append(f"Additional properties are not allowed ('{key}' was unexpected)")
    for key, subschema in props.items():
        if key in doc and subschema.get("type") == "object":
            sub_doc = doc[key]
            if subschema.get("additionalProperties") is False:
                sub_props = subschema.get("properties", {})
                for sub_key in sub_doc:
                    if sub_key not in sub_props:
                        errs.append(f"Additional properties are not allowed ('{key}.{sub_key}' was unexpected)")
    if "schema_version" in props:
        sv = doc.get("schema_version")
        if sv is not None and "enum" in props["schema_version"]:
            if sv not in props["schema_version"]["enum"]:
                errs.append(f"{sv} is not one of {props['schema_version']['enum']}")
    return errs


# ── the shipped examples pass the schema gate ──
EX = os.path.join(ROOT, "abi", "examples")
for good in ("app-a133-powervr.toml", "app-a523-mali.toml", "app-input-layer.toml"):
    text = open(os.path.join(EX, good)).read()
    check(f"example {good} passes schema", schema_errors(text) == [], schema_errors(text))

# ── RED (before schema update): a v2 manifest with [display] ──
V2_DISPLAY = """\
schema_version = 2
[app]
id = "com.test.displayok"
[display]
orientations = ["landscape"]
[runtime]
family = "pocketforge/a133-powervr"
abi = "1"
"""
v2_errors = schema_errors(V2_DISPLAY)
v2_pass = v2_errors == []
check("v2 manifest with [display] accepted by schema", v2_pass, v2_errors)

# ── Negative: unknown orientation token ──
BAD_ORIENTATION = """\
schema_version = 2
[app]
id = "com.test.badorient"
[display]
orientations = ["rotated"]
[runtime]
family = "pocketforge/a133-powervr"
abi = "1"
"""
bad_orient_errors = schema_errors(BAD_ORIENTATION)
check("unknown orientation 'rotated' rejected",
      bad_orient_errors != [],
      bad_orient_errors)

# ── Negative: schema_version 3 rejected ──
SV3 = """\
schema_version = 3
[app]
id = "com.test.sv3"
[runtime]
family = "pocketforge/a133-powervr"
abi = "1"
"""
sv3_errors = schema_errors(SV3)
check("schema_version 3 rejected",
      sv3_errors != [],
      sv3_errors)

# ── Negative: empty orientations rejected ──
EMPTY_ORIENT = """\
schema_version = 2
[app]
id = "com.test.emptyorient"
[display]
orientations = []
[runtime]
family = "pocketforge/a133-powervr"
abi = "1"
"""
empty_errors = schema_errors(EMPTY_ORIENT)
check("empty orientations rejected",
      empty_errors != [],
      empty_errors)

# ── Negative: duplicate orientations rejected ──
DUP_ORIENT = """\
schema_version = 2
[app]
id = "com.test.duporient"
[display]
orientations = ["landscape", "landscape"]
[runtime]
family = "pocketforge/a133-powervr"
abi = "1"
"""
dup_errors = schema_errors(DUP_ORIENT)
check("duplicate orientations rejected",
      dup_errors != [],
      dup_errors)

# ── v4 default orientation: absent [display] = ["landscape"] ──
NO_DISPLAY = """\
schema_version = 2
[app]
id = "com.test.nodisplay"
[runtime]
family = "pocketforge/a133-powervr"
abi = "1"
"""
check("manifest without [display] still valid (defaults to landscape)",
      schema_errors(NO_DISPLAY) == [], schema_errors(NO_DISPLAY))

# ── a manifest with schema_version absent (default 1) and no display is valid ──
V1_PLAIN = """\
[app]
id = "com.test.v1plain"
[runtime]
family = "pocketforge/a133-powervr"
abi = "1"
"""
check("v1 manifest (no schema_version, no display) is valid",
      schema_errors(V1_PLAIN) == [], schema_errors(V1_PLAIN))

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s): {', '.join(FAILS)}")
    sys.exit(1)
print("ALL app schema checks passed")