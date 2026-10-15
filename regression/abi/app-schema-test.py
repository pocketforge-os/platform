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
    additionalProperties, resolve $ref, handle if/then/else gating."""
    errs = []

    def resolve_ref(ref):
        if not ref.startswith("#/"):
            return None
        parts = ref[2:].split("/")
        node = schema
        for p in parts:
            if isinstance(node, dict):
                node = node.get(p)
            else:
                return None
        return node if isinstance(node, dict) else None

    def check_node(instance, node_schema, path):
        if not isinstance(node_schema, dict):
            return
        if "$ref" in node_schema:
            resolved = resolve_ref(node_schema["$ref"])
            if resolved:
                check_node(instance, resolved, path)
            return
        if not isinstance(instance, dict):
            return
        # allOf with if/then/else
        for item in node_schema.get("allOf", []):
            if "if" in item and isinstance(item["if"], dict):
                if_match = _check_if(instance, item["if"])
                if if_match and "then" in item:
                    check_node(instance, item["then"], path)
                elif not if_match and "else" in item:
                    check_node(instance, item["else"], path)
        # additionalProperties: false — only when explicitly set (JSON Schema
        # defaults to additionalProperties allowed, not forbidden)
        props = node_schema.get("properties", {})
        if "additionalProperties" in node_schema:
            ap = node_schema["additionalProperties"]
            if ap is False:
                for key in instance:
                    if key not in props:
                        errs.append(f"Additional properties are not allowed ('{path}{key}' was unexpected)")
        # check property schemas
        for prop_key, prop_schema in props.items():
            if not isinstance(prop_schema, dict):
                if prop_schema is False and prop_key in instance:
                    errs.append(f"Property '{path}{prop_key}' is not allowed")
                continue
            if prop_key in instance:
                val = instance[prop_key]
                if "$ref" in prop_schema:
                    resolved = resolve_ref(prop_schema["$ref"])
                    if resolved:
                        check_node_type(val, resolved, f"{path}{prop_key}.")
                        if isinstance(val, dict):
                            check_node(val, resolved, f"{path}{prop_key}.")
                check_node_type(val, prop_schema, f"{path}{prop_key}.")
                if isinstance(val, list) and isinstance(prop_schema, dict):
                    if "minItems" in prop_schema and len(val) < prop_schema["minItems"]:
                        errs.append(f"{path}{prop_key}: array too short (min {prop_schema['minItems']}, got {len(val)})")
                    if prop_schema.get("uniqueItems") and len(val) != len(set(str(v) for v in val)):
                        errs.append(f"{path}{prop_key}: duplicate items")
                    items_schema = prop_schema.get("items")
                    if isinstance(items_schema, dict) and "enum" in items_schema:
                        for v in val:
                            if v not in items_schema["enum"]:
                                errs.append(f"{path}{prop_key}: '{v}' is not one of {items_schema['enum']}")
                # required fields in sub-object
                if isinstance(val, dict):
                    for req_key in prop_schema.get("required", []):
                        if req_key not in val:
                            errs.append(f"{path}{prop_key}: missing required field '{req_key}'")

    def check_node_type(val, node_schema, path):
        t = node_schema.get("type")
        if t == "integer" and not isinstance(val, int):
            errs.append(f"{path} expected integer, got {type(val).__name__}")
        if t == "string" and not isinstance(val, str):
            errs.append(f"{path} expected string, got {type(val).__name__}")
        if t == "array" and not isinstance(val, list):
            errs.append(f"{path} expected array, got {type(val).__name__}")
        if t == "object" and not isinstance(val, dict):
            errs.append(f"{path} expected object, got {type(val).__name__}")
        if "enum" in node_schema and val not in node_schema["enum"]:
            errs.append(f"{path} {val} is not one of {node_schema['enum']}")

    def _check_if(instance, if_schema):
        if "required" in if_schema:
            if not all(k in instance for k in if_schema["required"]):
                return False
        if "properties" in if_schema:
            for pk, pv in if_schema["properties"].items():
                if not isinstance(pv, dict):
                    continue
                if pk not in instance:
                    continue
                if "const" in pv and instance[pk] != pv["const"]:
                    return False
        return True

    check_node(doc, schema, "")
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