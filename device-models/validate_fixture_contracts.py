#!/usr/bin/env python3
"""Validate and fingerprint PocketForge device fixture contracts.

The checker is deliberately stdlib-only and read-only.  It validates the
manufacturing handoff independently from OpenSCAD and from rendered skin
artifacts.  Use --print-interface-hash to review the hash for an intentional
interface edit; the command never rewrites a contract.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_REF = "../../schemas/device-fixture-contract.schema.json"
SCHEMA_VERSION = 1
CANONICALIZATION = "pocketforge-fixture-interface-json-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_REV_RE = re.compile(r"^[0-9a-f]{40}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ALIAS_RE = re.compile(r"^\.\./[a-z0-9][a-z0-9-]*/fixture-contract\.json$")

SURFACES = {
    "front",
    "rear",
    "top_edge",
    "bottom_edge",
    "left_edge",
    "right_edge",
}
SURFACE_AXES = {
    "front": ("x", "y"),
    "rear": ("x", "y"),
    "top_edge": ("x", "z"),
    "bottom_edge": ("x", "z"),
    "left_edge": ("y", "z"),
    "right_edge": ("y", "z"),
}
EDGE_INTERVAL_AXIS = {
    "top_edge": "x",
    "bottom_edge": "x",
    "left_edge": "y",
    "right_edge": "y",
}
INWARD_NORMAL = {
    "front": (0, 0, -1),
    "rear": (0, 0, 1),
    "top_edge": (0, -1, 0),
    "bottom_edge": (0, 1, 0),
    "left_edge": (1, 0, 0),
    "right_edge": (-1, 0, 0),
}
MEASUREMENT_BASES = {
    "owner_caliper",
    "published_nominal",
    "inherited_shared_chassis",
    "fit_derived_proxy",
    "photo_derived",
}
CONTACT_MODES = {"support", "retention", "datum", "padded"}
KEEP_OUT_CATEGORIES = {
    "control",
    "port",
    "vent",
    "display",
    "optical",
    "cable",
    "trigger",
    "fastener",
    "service",
    "thermal",
}
ACCESS_CATEGORIES = {"service", "cable", "airflow", "optical"}
CLEARANCE_DIRECTIONS = {"rearward", "frontward", "radial"}
EVIDENCE_METHODS = {
    "owner_caliper",
    "owner_physical_fit",
    "official_specification",
    "photo_derived",
    "accepted_fixture_design",
    "inherited_shared_chassis",
}
CONFIDENCE = {"high", "medium_high", "medium", "low"}
QUALIFICATION_STATES = {
    "unqualified",
    "fit_evidence_recorded",
    "physically_qualified",
}
UNRESOLVED_GATES = {
    "new_retention_family",
    "geometry_qualification",
    "precision_fit",
    "sealed_fixture",
}
UNORDERED_STRING_LIST_KEYS = {
    "contact_modes",
    "protects",
    "region_refs",
}


class ContractError(ValueError):
    """A deterministic fixture-contract validation failure."""


def _fail(path: str, message: str) -> None:
    raise ContractError(f"{path}: {message}")


def _reject_constant(token: str) -> None:
    raise ContractError(f"JSON contains non-finite number {token}")


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=_reject_constant,
        )
    except OSError as exc:
        raise ContractError(f"{path}: cannot read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}") from exc


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value


def _array(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        _fail(path, "must be an array")
    return value


def _keys(
    value: Mapping[str, Any],
    path: str,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    missing = sorted(required_set - value.keys())
    extra = sorted(value.keys() - allowed)
    if missing:
        _fail(path, f"missing required field(s): {', '.join(missing)}")
    if extra:
        _fail(path, f"unknown field(s): {', '.join(extra)}")


def _string(value: Any, path: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        _fail(path, "must be a non-empty string")
    if pattern is not None and not pattern.fullmatch(value):
        _fail(path, f"has invalid format: {value!r}")
    return value


def _enum(value: Any, path: str, allowed: set[str]) -> str:
    result = _string(value, path)
    if result not in allowed:
        _fail(path, f"must be one of {sorted(allowed)}, got {result!r}")
    return result


def _number(
    value: Any,
    path: str,
    *,
    minimum: Decimal | None = None,
    exclusive_minimum: Decimal | None = None,
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        _fail(path, "must be a finite number")
    result = Decimal(str(value)) if not isinstance(value, Decimal) else value
    if not result.is_finite():
        _fail(path, "must be a finite number")
    if minimum is not None and result < minimum:
        _fail(path, f"must be >= {minimum}")
    if exclusive_minimum is not None and result <= exclusive_minimum:
        _fail(path, f"must be > {exclusive_minimum}")
    return result


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    result = _number(value, path)
    if result != result.to_integral_value():
        _fail(path, "must be an integer")
    integer = int(result)
    if integer < minimum:
        _fail(path, f"must be >= {minimum}")
    return integer


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(path, "must be a boolean")
    return value


def _nullable_number(value: Any, path: str) -> Decimal | None:
    return None if value is None else _number(value, path, minimum=Decimal(0))


def _vector(value: Any, path: str, length: int) -> tuple[Decimal, ...]:
    items = _array(value, path)
    if len(items) != length:
        _fail(path, f"must contain exactly {length} numbers")
    return tuple(_number(item, f"{path}[{index}]") for index, item in enumerate(items))


def _string_list(
    value: Any,
    path: str,
    *,
    minimum: int = 0,
    pattern: re.Pattern[str] | None = None,
    allowed: set[str] | None = None,
) -> list[str]:
    items = _array(value, path)
    if len(items) < minimum:
        _fail(path, f"must contain at least {minimum} item(s)")
    result: list[str] = []
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        string = _string(item, item_path, pattern=pattern)
        if allowed is not None and string not in allowed:
            _fail(item_path, f"must be one of {sorted(allowed)}, got {string!r}")
        result.append(string)
    if len(result) != len(set(result)):
        _fail(path, "must not contain duplicates")
    return result


def _validate_device(value: Any, path: str) -> Mapping[str, Any]:
    obj = _object(value, path)
    _keys(
        obj,
        path,
        {
            "slug",
            "platform_device_ids",
            "manufacturer",
            "product",
            "model_number",
            "hardware_revisions",
            "chassis_family",
        },
    )
    _string(obj["slug"], f"{path}.slug", pattern=SLUG_RE)
    _string_list(
        obj["platform_device_ids"],
        f"{path}.platform_device_ids",
        minimum=1,
        pattern=SLUG_RE,
    )
    for key in ("manufacturer", "product", "model_number"):
        _string(obj[key], f"{path}.{key}")
    _string_list(obj["hardware_revisions"], f"{path}.hardware_revisions", minimum=1)
    _string(obj["chassis_family"], f"{path}.chassis_family", pattern=SLUG_RE)
    return obj


def _validate_visual_model(value: Any, path: str, contract_path: Path) -> None:
    obj = _object(value, path)
    _keys(obj, path, {"path", "role", "manufacturing_source"})
    model_path = _string(
        obj["path"],
        f"{path}.path",
        pattern=re.compile(r"^[a-z0-9][a-z0-9-]*\.scad$"),
    )
    _enum(
        obj["role"],
        f"{path}.role",
        {"visual_reference_only", "shared_chassis_visual_derivative"},
    )
    if _boolean(obj["manufacturing_source"], f"{path}.manufacturing_source"):
        _fail(f"{path}.manufacturing_source", "must remain false")
    if not (contract_path.parent / model_path).is_file():
        _fail(f"{path}.path", f"model does not exist beside contract: {model_path}")


def _validate_coordinate_system(value: Any, path: str) -> None:
    obj = _object(value, path)
    _keys(obj, path, {"units", "handedness", "origin", "axes"})
    expected = {
        "units": "mm",
        "handedness": "right_handed",
        "origin": "rear_left_bottom_nominal_shell_datum",
    }
    for key, wanted in expected.items():
        if obj[key] != wanted:
            _fail(f"{path}.{key}", f"must be {wanted!r}")
    axes = _object(obj["axes"], f"{path}.axes")
    _keys(axes, f"{path}.axes", {"x", "y", "z"})
    expected_axes = {
        "x": "physical_left_to_right",
        "y": "physical_bottom_to_top",
        "z": "physical_rear_to_front",
    }
    for key, wanted in expected_axes.items():
        if axes[key] != wanted:
            _fail(f"{path}.axes.{key}", f"must be {wanted!r}")


def _validate_measurement(value: Any, path: str) -> None:
    obj = _object(value, path)
    _keys(
        obj,
        path,
        {"nominal_mm", "basis", "measurement_uncertainty_mm", "manufacturing_ready"},
    )
    _number(obj["nominal_mm"], f"{path}.nominal_mm", exclusive_minimum=Decimal(0))
    _enum(obj["basis"], f"{path}.basis", MEASUREMENT_BASES)
    _nullable_number(obj["measurement_uncertainty_mm"], f"{path}.measurement_uncertainty_mm")
    _boolean(obj["manufacturing_ready"], f"{path}.manufacturing_ready")


def _validate_shape(value: Any, path: str) -> tuple[str, tuple[Decimal, ...], tuple[Decimal, ...]]:
    obj = _object(value, path)
    kind = _string(obj.get("kind"), f"{path}.kind")
    if kind == "edge_interval":
        _keys(obj, path, {"kind", "surface", "axis", "min_mm", "max_mm"})
        surface = _enum(obj["surface"], f"{path}.surface", SURFACES)
        if surface not in EDGE_INTERVAL_AXIS:
            _fail(f"{path}.surface", "edge_interval requires an edge surface")
        axis = _enum(obj["axis"], f"{path}.axis", {"x", "y", "z"})
        if axis != EDGE_INTERVAL_AXIS[surface]:
            _fail(f"{path}.axis", f"{surface} intervals must use {EDGE_INTERVAL_AXIS[surface]!r}")
        lower = _number(obj["min_mm"], f"{path}.min_mm")
        upper = _number(obj["max_mm"], f"{path}.max_mm")
        if lower >= upper:
            _fail(path, "min_mm must be less than max_mm")
        return surface, (lower,), (upper,)
    if kind == "surface_rectangle":
        _keys(obj, path, {"kind", "surface", "axes", "min_mm", "max_mm"})
        surface = _enum(obj["surface"], f"{path}.surface", SURFACES)
        axes = _string_list(
            obj["axes"], f"{path}.axes", minimum=2, allowed={"x", "y", "z"}
        )
        if len(axes) != 2 or tuple(axes) != SURFACE_AXES[surface]:
            _fail(f"{path}.axes", f"{surface} rectangles must use {SURFACE_AXES[surface]}")
        lower = _vector(obj["min_mm"], f"{path}.min_mm", 2)
        upper = _vector(obj["max_mm"], f"{path}.max_mm", 2)
        if any(a >= b for a, b in zip(lower, upper)):
            _fail(path, "each min_mm coordinate must be less than max_mm")
        return surface, lower, upper
    if kind == "aabb":
        _keys(obj, path, {"kind", "min_mm", "max_mm"})
        lower = _vector(obj["min_mm"], f"{path}.min_mm", 3)
        upper = _vector(obj["max_mm"], f"{path}.max_mm", 3)
        if any(a >= b for a, b in zip(lower, upper)):
            _fail(path, "each min_mm coordinate must be less than max_mm")
        return "volume", lower, upper
    _fail(f"{path}.kind", f"unknown shape kind {kind!r}")
    raise AssertionError("unreachable")


def _shape_within_xy_envelope(
    shape: Mapping[str, Any],
    path: str,
    xy_min: tuple[Decimal, Decimal],
    xy_max: tuple[Decimal, Decimal],
) -> None:
    kind = shape["kind"]
    if kind == "edge_interval":
        axis = shape["axis"]
        lower = _number(shape["min_mm"], f"{path}.min_mm")
        upper = _number(shape["max_mm"], f"{path}.max_mm")
        index = 0 if axis == "x" else 1
        if lower < xy_min[index] or upper > xy_max[index]:
            _fail(path, f"interval exceeds envelope on {axis}")
    elif kind == "surface_rectangle":
        axes = shape["axes"]
        lower = _vector(shape["min_mm"], f"{path}.min_mm", 2)
        upper = _vector(shape["max_mm"], f"{path}.max_mm", 2)
        for index, axis in enumerate(axes):
            if axis in {"x", "y"}:
                envelope_index = 0 if axis == "x" else 1
                if lower[index] < xy_min[envelope_index] or upper[index] > xy_max[envelope_index]:
                    _fail(path, f"rectangle exceeds envelope on {axis}")
    elif kind == "aabb":
        lower = _vector(shape["min_mm"], f"{path}.min_mm", 3)
        upper = _vector(shape["max_mm"], f"{path}.max_mm", 3)
        if lower[0] < xy_min[0] or upper[0] > xy_max[0]:
            _fail(path, "AABB exceeds envelope on x")
        if lower[1] < xy_min[1] or upper[1] > xy_max[1]:
            _fail(path, "AABB exceeds envelope on y")


def _add_unique_id(seen: dict[str, str], item_id: str, path: str) -> None:
    previous = seen.get(item_id)
    if previous is not None:
        _fail(path, f"duplicate interface id {item_id!r}; first declared at {previous}")
    seen[item_id] = path


def _validate_fixture_interface(value: Any, path: str) -> set[str]:
    obj = _object(value, path)
    _keys(
        obj,
        path,
        {
            "envelope",
            "local_depths",
            "contact_regions",
            "keepouts",
            "access_regions",
            "datums",
            "clearance_requirements",
        },
    )

    envelope = _object(obj["envelope"], f"{path}.envelope")
    _keys(
        envelope,
        f"{path}.envelope",
        {"xy_bounds_mm", "xy_measurement_uncertainty_mm", "overall_depth"},
    )
    bounds = _object(envelope["xy_bounds_mm"], f"{path}.envelope.xy_bounds_mm")
    _keys(bounds, f"{path}.envelope.xy_bounds_mm", {"min", "max"})
    xy_min = _vector(bounds["min"], f"{path}.envelope.xy_bounds_mm.min", 2)
    xy_max = _vector(bounds["max"], f"{path}.envelope.xy_bounds_mm.max", 2)
    if any(a >= b for a, b in zip(xy_min, xy_max)):
        _fail(f"{path}.envelope.xy_bounds_mm", "each min coordinate must be less than max")
    _nullable_number(
        envelope["xy_measurement_uncertainty_mm"],
        f"{path}.envelope.xy_measurement_uncertainty_mm",
    )
    _validate_measurement(envelope["overall_depth"], f"{path}.envelope.overall_depth")

    seen_ids: dict[str, str] = {}
    interface_refs = {"envelope:xy", "envelope:overall_depth"}

    local_depths = _array(obj["local_depths"], f"{path}.local_depths")
    if not local_depths:
        _fail(f"{path}.local_depths", "must not be empty")
    depth_by_id: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(local_depths):
        item_path = f"{path}.local_depths[{index}]"
        depth = _object(item, item_path)
        _keys(
            depth,
            item_path,
            {
                "id",
                "region_refs",
                "nominal_mm",
                "basis",
                "measurement_uncertainty_mm",
                "manufacturing_ready",
            },
        )
        item_id = _string(depth["id"], f"{item_path}.id", pattern=ID_RE)
        _add_unique_id(seen_ids, item_id, item_path)
        depth_by_id[item_id] = depth
        _string_list(
            depth["region_refs"],
            f"{item_path}.region_refs",
            minimum=1,
            pattern=ID_RE,
        )
        _number(depth["nominal_mm"], f"{item_path}.nominal_mm", exclusive_minimum=Decimal(0))
        _enum(depth["basis"], f"{item_path}.basis", MEASUREMENT_BASES)
        _nullable_number(
            depth["measurement_uncertainty_mm"],
            f"{item_path}.measurement_uncertainty_mm",
        )
        _boolean(depth["manufacturing_ready"], f"{item_path}.manufacturing_ready")
        interface_refs.add(f"depth:{item_id}")

    contact_ids: set[str] = set()
    contacts = _array(obj["contact_regions"], f"{path}.contact_regions")
    if not contacts:
        _fail(f"{path}.contact_regions", "must not be empty")
    for index, item in enumerate(contacts):
        item_path = f"{path}.contact_regions[{index}]"
        contact = _object(item, item_path)
        _keys(contact, item_path, {"id", "shape", "normal", "contact_modes", "local_depth_ref"})
        item_id = _string(contact["id"], f"{item_path}.id", pattern=ID_RE)
        _add_unique_id(seen_ids, item_id, item_path)
        contact_ids.add(item_id)
        shape = _object(contact["shape"], f"{item_path}.shape")
        surface, _, _ = _validate_shape(shape, f"{item_path}.shape")
        _shape_within_xy_envelope(shape, f"{item_path}.shape", xy_min, xy_max)
        normal = _vector(contact["normal"], f"{item_path}.normal", 3)
        expected_normal = tuple(Decimal(component) for component in INWARD_NORMAL[surface])
        if normal != expected_normal:
            _fail(
                f"{item_path}.normal",
                f"must be the inward normal {INWARD_NORMAL[surface]} for {surface}",
            )
        _string_list(
            contact["contact_modes"],
            f"{item_path}.contact_modes",
            minimum=1,
            allowed=CONTACT_MODES,
        )
        depth_ref = _string(
            contact["local_depth_ref"],
            f"{item_path}.local_depth_ref",
            pattern=ID_RE,
        )
        if depth_ref not in depth_by_id:
            _fail(f"{item_path}.local_depth_ref", f"unknown local depth {depth_ref!r}")
        interface_refs.add(f"contact:{item_id}")

    for depth_id, depth in depth_by_id.items():
        for region_ref in depth["region_refs"]:
            if region_ref not in contact_ids:
                _fail(
                    f"{path}.local_depths[{depth_id}].region_refs",
                    f"unknown contact region {region_ref!r}",
                )

    for collection_name, categories, ref_prefix in (
        ("keepouts", KEEP_OUT_CATEGORIES, "keepout"),
        ("access_regions", ACCESS_CATEGORIES, "access"),
    ):
        collection = _array(obj[collection_name], f"{path}.{collection_name}")
        for index, item in enumerate(collection):
            item_path = f"{path}.{collection_name}[{index}]"
            region = _object(item, item_path)
            required = {"id", "category", "shape"}
            required.add("clearance_mm" if collection_name == "keepouts" else "must_remain_open")
            _keys(region, item_path, required)
            item_id = _string(region["id"], f"{item_path}.id", pattern=ID_RE)
            _add_unique_id(seen_ids, item_id, item_path)
            _enum(region["category"], f"{item_path}.category", categories)
            shape = _object(region["shape"], f"{item_path}.shape")
            _validate_shape(shape, f"{item_path}.shape")
            _shape_within_xy_envelope(shape, f"{item_path}.shape", xy_min, xy_max)
            if collection_name == "keepouts":
                _number(region["clearance_mm"], f"{item_path}.clearance_mm", minimum=Decimal(0))
            else:
                if not _boolean(region["must_remain_open"], f"{item_path}.must_remain_open"):
                    _fail(f"{item_path}.must_remain_open", "must be true for an access region")
            interface_refs.add(f"{ref_prefix}:{item_id}")

    datum_ids: set[str] = set()
    datums = _array(obj["datums"], f"{path}.datums")
    if not datums:
        _fail(f"{path}.datums", "must not be empty")
    for index, item in enumerate(datums):
        item_path = f"{path}.datums[{index}]"
        datum = _object(item, item_path)
        item_id = _string(datum.get("id"), f"{item_path}.id", pattern=ID_RE)
        _add_unique_id(seen_ids, item_id, item_path)
        datum_ids.add(item_id)
        kind = _string(datum.get("kind"), f"{item_path}.kind")
        if kind == "point_2d":
            _keys(datum, item_path, {"id", "kind", "axes", "value_mm"})
            axes = _string_list(
                datum["axes"], f"{item_path}.axes", minimum=2, allowed={"x", "y", "z"}
            )
            if len(axes) != 2:
                _fail(f"{item_path}.axes", "must contain exactly two axes")
            value_mm = _vector(datum["value_mm"], f"{item_path}.value_mm", 2)
            for axis_index, axis in enumerate(axes):
                if axis in {"x", "y"}:
                    envelope_index = 0 if axis == "x" else 1
                    if not xy_min[envelope_index] <= value_mm[axis_index] <= xy_max[envelope_index]:
                        _fail(f"{item_path}.value_mm", f"datum exceeds envelope on {axis}")
        elif kind == "plane":
            _keys(datum, item_path, {"id", "kind", "normal", "offset_mm"})
            normal = _vector(datum["normal"], f"{item_path}.normal", 3)
            if sorted(abs(component) for component in normal) != [
                Decimal(0),
                Decimal(0),
                Decimal(1),
            ]:
                _fail(f"{item_path}.normal", "must be an axis-aligned unit vector")
            _number(datum["offset_mm"], f"{item_path}.offset_mm")
        else:
            _fail(f"{item_path}.kind", f"unknown datum kind {kind!r}")
        interface_refs.add(f"datum:{item_id}")

    clearances = _array(obj["clearance_requirements"], f"{path}.clearance_requirements")
    for index, item in enumerate(clearances):
        item_path = f"{path}.clearance_requirements[{index}]"
        clearance = _object(item, item_path)
        _keys(clearance, item_path, {"id", "direction", "minimum_mm", "from_datum", "protects"})
        item_id = _string(clearance["id"], f"{item_path}.id", pattern=ID_RE)
        _add_unique_id(seen_ids, item_id, item_path)
        _enum(clearance["direction"], f"{item_path}.direction", CLEARANCE_DIRECTIONS)
        _number(clearance["minimum_mm"], f"{item_path}.minimum_mm", minimum=Decimal(0))
        datum_ref = _string(clearance["from_datum"], f"{item_path}.from_datum", pattern=ID_RE)
        if datum_ref not in datum_ids:
            _fail(f"{item_path}.from_datum", f"unknown datum {datum_ref!r}")
        _string_list(
            clearance["protects"],
            f"{item_path}.protects",
            minimum=1,
            allowed=KEEP_OUT_CATEGORIES - {"fastener"},
        )
        interface_refs.add(f"clearance:{item_id}")

    return interface_refs


def _validate_refs(
    value: Any,
    path: str,
    available_refs: set[str],
    *,
    minimum: int = 0,
) -> list[str]:
    refs = _string_list(value, path, minimum=minimum)
    for index, ref in enumerate(refs):
        if ref not in available_refs:
            _fail(f"{path}[{index}]", f"unknown interface reference {ref!r}")
    return refs


def _validate_holder_evidence(value: Any, path: str) -> Mapping[str, Any]:
    obj = _object(value, path)
    _keys(obj, path, {"repository", "revision", "qualification_path"})
    if obj["repository"] != "pocketforge-os/test-node-hw":
        _fail(f"{path}.repository", "must be 'pocketforge-os/test-node-hw'")
    _string(obj["revision"], f"{path}.revision", pattern=GIT_REV_RE)
    _string(obj["qualification_path"], f"{path}.qualification_path")
    return obj


def _validate_qualification(
    value: Any,
    path: str,
    interface_hash_value: str,
    available_refs: set[str],
) -> Mapping[str, Any]:
    obj = _object(value, path)
    _keys(
        obj,
        path,
        {
            "status",
            "scope",
            "qualified_fixture_interface_sha256",
            "accepted_on",
            "acceptance_ref",
            "interface_refs",
            "holder_evidence",
            "exclusions",
        },
    )
    status = _enum(obj["status"], f"{path}.status", QUALIFICATION_STATES)
    _string(obj["scope"], f"{path}.scope")
    refs = _validate_refs(obj["interface_refs"], f"{path}.interface_refs", available_refs)
    _string_list(obj["exclusions"], f"{path}.exclusions", minimum=1)

    if status == "unqualified":
        for key in (
            "qualified_fixture_interface_sha256",
            "accepted_on",
            "acceptance_ref",
            "holder_evidence",
        ):
            if obj[key] is not None:
                _fail(f"{path}.{key}", "must be null while status is unqualified")
        if refs:
            _fail(f"{path}.interface_refs", "must be empty while status is unqualified")
        return obj

    qualified_hash = _string(
        obj["qualified_fixture_interface_sha256"],
        f"{path}.qualified_fixture_interface_sha256",
        pattern=SHA256_RE,
    )
    if qualified_hash != interface_hash_value:
        _fail(
            f"{path}.qualified_fixture_interface_sha256",
            "does not match the resolved fixture interface",
        )
    accepted_on = _string(obj["accepted_on"], f"{path}.accepted_on")
    try:
        dt.date.fromisoformat(accepted_on)
    except ValueError as exc:
        _fail(f"{path}.accepted_on", f"invalid ISO date: {exc}")
    _string(obj["acceptance_ref"], f"{path}.acceptance_ref")
    _validate_holder_evidence(obj["holder_evidence"], f"{path}.holder_evidence")
    if not refs:
        _fail(f"{path}.interface_refs", "must identify the qualified scope")
    return obj


def _validate_evidence(
    value: Any,
    path: str,
    available_refs: set[str],
) -> None:
    items = _array(value, path)
    if not items:
        _fail(path, "must not be empty")
    ids: set[str] = set()
    covered: set[str] = set()
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        evidence = _object(item, item_path)
        _keys(
            evidence,
            item_path,
            {"id", "method", "confidence", "reference", "interface_refs", "note"},
        )
        item_id = _string(evidence["id"], f"{item_path}.id", pattern=ID_RE)
        if item_id in ids:
            _fail(f"{item_path}.id", f"duplicate evidence id {item_id!r}")
        ids.add(item_id)
        _enum(evidence["method"], f"{item_path}.method", EVIDENCE_METHODS)
        _enum(evidence["confidence"], f"{item_path}.confidence", CONFIDENCE)
        _string(evidence["reference"], f"{item_path}.reference")
        refs = _validate_refs(
            evidence["interface_refs"],
            f"{item_path}.interface_refs",
            available_refs,
            minimum=1,
        )
        covered.update(refs)
        _string(evidence["note"], f"{item_path}.note")
    missing = sorted(available_refs - covered)
    if missing:
        _fail(path, f"no provenance covers interface reference(s): {', '.join(missing)}")


def _validate_unresolved(value: Any, path: str, available_refs: set[str]) -> None:
    items = _array(value, path)
    ids: set[str] = set()
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        unresolved = _object(item, item_path)
        _keys(
            unresolved,
            item_path,
            {"id", "status", "required_before", "interface_refs", "needed"},
        )
        item_id = _string(unresolved["id"], f"{item_path}.id", pattern=ID_RE)
        if item_id in ids:
            _fail(f"{item_path}.id", f"duplicate unresolved-measurement id {item_id!r}")
        ids.add(item_id)
        if unresolved["status"] != "open":
            _fail(f"{item_path}.status", "must be 'open'; remove resolved entries")
        _enum(
            unresolved["required_before"],
            f"{item_path}.required_before",
            UNRESOLVED_GATES,
        )
        _validate_refs(
            unresolved["interface_refs"],
            f"{item_path}.interface_refs",
            available_refs,
            minimum=1,
        )
        _string(unresolved["needed"], f"{item_path}.needed")


def _canonical_number(value: int | float | Decimal) -> str:
    number = Decimal(str(value)) if not isinstance(value, Decimal) else value
    if not number.is_finite():
        raise ContractError("cannot canonicalize non-finite number")
    if number == 0:
        return "0"
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _normalize_semantic_lists(value: Any, parent_key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_semantic_lists(child, key)
            for key, child in value.items()
        }
    if isinstance(value, list):
        normalized = [_normalize_semantic_lists(child, parent_key) for child in value]
        if normalized and all(
            isinstance(child, dict) and isinstance(child.get("id"), str)
            for child in normalized
        ):
            return sorted(normalized, key=lambda child: child["id"])
        if parent_key in UNORDERED_STRING_LIST_KEYS and all(
            isinstance(child, str) for child in normalized
        ):
            return sorted(normalized)
        return normalized
    return value


def _canonical_json(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return _canonical_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{_canonical_json(key)}:{_canonical_json(value[key])}"
            for key in sorted(value)
        ) + "}"
    raise ContractError(f"cannot canonicalize value of type {type(value).__name__}")


def interface_hash(document: Mapping[str, Any]) -> str:
    if document.get("kind") != "fixture_interface":
        raise ContractError("interface_hash requires a full fixture_interface document")
    payload = {
        "canonicalization": CANONICALIZATION,
        "schema_version": document["schema_version"],
        "coordinate_system": document["coordinate_system"],
        "fixture_interface": document["fixture_interface"],
    }
    normalized = _normalize_semantic_lists(payload)
    encoded = _canonical_json(normalized).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_common(
    document: Mapping[str, Any],
    path: Path,
    expected_keys: set[str],
) -> Mapping[str, Any]:
    _keys(document, str(path), expected_keys)
    if document["$schema"] != SCHEMA_REF:
        _fail(f"{path}.$schema", f"must be {SCHEMA_REF!r}")
    if _integer(document["schema_version"], f"{path}.schema_version", minimum=1) != SCHEMA_VERSION:
        _fail(f"{path}.schema_version", f"unsupported version; expected {SCHEMA_VERSION}")
    device = _validate_device(document["device"], f"{path}.device")
    if device["slug"] != path.parent.name:
        _fail(f"{path}.device.slug", f"must match package directory {path.parent.name!r}")
    _validate_visual_model(document["visual_model"], f"{path}.visual_model", path)
    return device


@dataclass(frozen=True)
class ResolvedContract:
    path: Path
    document: Mapping[str, Any]
    interface_document: Mapping[str, Any]
    interface_hash: str
    interface_revision: int
    qualification: Mapping[str, Any]
    interface_refs: frozenset[str]


class ContractRepository:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.model_root = (self.root / "device-models").resolve()
        self._cache: dict[Path, ResolvedContract] = {}

    def discover(self) -> list[Path]:
        return sorted(self.model_root.glob("*/fixture-contract.json"))

    def resolve(self, path: Path, stack: tuple[Path, ...] = ()) -> ResolvedContract:
        path = path.resolve()
        if path in self._cache:
            return self._cache[path]
        if path in stack:
            chain = " -> ".join(str(item.relative_to(self.root)) for item in (*stack, path))
            _fail(str(path), f"shared-chassis alias cycle: {chain}")
        try:
            path.relative_to(self.model_root)
        except ValueError:
            _fail(str(path), "contract path escapes device-models")
        if path.name != "fixture-contract.json":
            _fail(str(path), "contract must be named fixture-contract.json")
        document = _object(load_json(path), str(path))
        kind = document.get("kind")
        if kind == "fixture_interface":
            resolved = self._validate_full(path, document)
        elif kind == "shared_chassis_alias":
            resolved = self._validate_alias(path, document, (*stack, path))
        else:
            _fail(
                f"{path}.kind",
                f"must be 'fixture_interface' or 'shared_chassis_alias', got {kind!r}",
            )
        self._cache[path] = resolved
        return resolved

    def _validate_full(
        self,
        path: Path,
        document: Mapping[str, Any],
    ) -> ResolvedContract:
        expected = {
            "$schema",
            "schema_version",
            "kind",
            "device",
            "visual_model",
            "interface_revision",
            "fixture_interface_sha256",
            "coordinate_system",
            "fixture_interface",
            "evidence",
            "qualification",
            "unresolved_measurements",
        }
        _validate_common(document, path, expected)
        if document["kind"] != "fixture_interface":
            _fail(f"{path}.kind", "must be 'fixture_interface'")
        if document["visual_model"]["role"] != "visual_reference_only":
            _fail(
                f"{path}.visual_model.role",
                "full contracts must use 'visual_reference_only'",
            )
        revision = _integer(document["interface_revision"], f"{path}.interface_revision", minimum=1)
        _validate_coordinate_system(document["coordinate_system"], f"{path}.coordinate_system")
        interface_refs = _validate_fixture_interface(
            document["fixture_interface"],
            f"{path}.fixture_interface",
        )
        expected_hash = _string(
            document["fixture_interface_sha256"],
            f"{path}.fixture_interface_sha256",
            pattern=SHA256_RE,
        )
        actual_hash = interface_hash(document)
        if expected_hash != actual_hash:
            _fail(
                f"{path}.fixture_interface_sha256",
                f"stale interface hash: recorded {expected_hash}, computed {actual_hash}",
            )
        _validate_evidence(document["evidence"], f"{path}.evidence", interface_refs)
        qualification = _validate_qualification(
            document["qualification"],
            f"{path}.qualification",
            actual_hash,
            interface_refs,
        )
        _validate_unresolved(
            document["unresolved_measurements"],
            f"{path}.unresolved_measurements",
            interface_refs,
        )
        return ResolvedContract(
            path=path,
            document=document,
            interface_document=document,
            interface_hash=actual_hash,
            interface_revision=revision,
            qualification=qualification,
            interface_refs=frozenset(interface_refs),
        )

    def _validate_alias(
        self,
        path: Path,
        document: Mapping[str, Any],
        stack: tuple[Path, ...],
    ) -> ResolvedContract:
        expected = {
            "$schema",
            "schema_version",
            "kind",
            "device",
            "visual_model",
            "extends",
            "expected_fixture_interface_sha256",
            "relationship",
            "qualification",
        }
        device = _validate_common(document, path, expected)
        if document["kind"] != "shared_chassis_alias":
            _fail(f"{path}.kind", "must be 'shared_chassis_alias'")
        if document["visual_model"]["role"] != "shared_chassis_visual_derivative":
            _fail(
                f"{path}.visual_model.role",
                "aliases must use 'shared_chassis_visual_derivative'",
            )
        extends = _string(document["extends"], f"{path}.extends", pattern=ALIAS_RE)
        target = (path.parent / extends).resolve()
        try:
            target.relative_to(self.model_root)
        except ValueError:
            _fail(f"{path}.extends", "alias target escapes device-models")
        target_contract = self.resolve(target, stack)
        expected_hash = _string(
            document["expected_fixture_interface_sha256"],
            f"{path}.expected_fixture_interface_sha256",
            pattern=SHA256_RE,
        )
        if expected_hash != target_contract.interface_hash:
            _fail(
                f"{path}.expected_fixture_interface_sha256",
                f"alias hash {expected_hash} does not match target "
                f"{target_contract.interface_hash}",
            )
        if device["chassis_family"] != target_contract.document["device"]["chassis_family"]:
            _fail(f"{path}.device.chassis_family", "must match the resolved chassis family")

        relationship = _object(document["relationship"], f"{path}.relationship")
        _keys(
            relationship,
            f"{path}.relationship",
            {"basis", "evidence_refs", "fit_relevant_deltas", "visual_only_deltas"},
        )
        if relationship["basis"] != "shared_chassis":
            _fail(f"{path}.relationship.basis", "must be 'shared_chassis'")
        _string_list(
            relationship["evidence_refs"],
            f"{path}.relationship.evidence_refs",
            minimum=1,
        )
        fit_deltas = _string_list(
            relationship["fit_relevant_deltas"],
            f"{path}.relationship.fit_relevant_deltas",
        )
        if fit_deltas:
            _fail(
                f"{path}.relationship.fit_relevant_deltas",
                "an alias cannot carry fit-relevant deltas; create a full contract",
            )
        _string_list(
            relationship["visual_only_deltas"],
            f"{path}.relationship.visual_only_deltas",
            minimum=1,
        )
        qualification = _validate_qualification(
            document["qualification"],
            f"{path}.qualification",
            target_contract.interface_hash,
            set(target_contract.interface_refs),
        )
        return ResolvedContract(
            path=path,
            document=document,
            interface_document=target_contract.interface_document,
            interface_hash=target_contract.interface_hash,
            interface_revision=target_contract.interface_revision,
            qualification=qualification,
            interface_refs=target_contract.interface_refs,
        )

    def validate_all(self, paths: Sequence[Path] | None = None) -> list[ResolvedContract]:
        selected = list(paths) if paths is not None else self.discover()
        if not selected:
            _fail(str(self.model_root), "no fixture contracts discovered")
        resolved = [
            self.resolve(path if path.is_absolute() else self.root / path)
            for path in selected
        ]
        slugs: dict[str, Path] = {}
        for contract in resolved:
            device = contract.document["device"]
            slug = device["slug"]
            if slug in slugs:
                _fail(
                    str(contract.path),
                    f"duplicate device slug {slug!r} also used by {slugs[slug]}",
                )
            slugs[slug] = contract.path
        return resolved


def _qualification_evidence_signature(
    qualification: Mapping[str, Any],
) -> tuple[Any, ...]:
    holder = qualification.get("holder_evidence")
    return (
        qualification.get("acceptance_ref"),
        holder.get("revision") if isinstance(holder, dict) else None,
    )


def compare_contract_roots(current: ContractRepository, baseline: ContractRepository) -> list[str]:
    """Enforce revision and qualification transitions against a baseline tree."""

    current_contracts = current.validate_all()
    baseline_paths = baseline.discover()
    if not baseline_paths:
        return []
    baseline_contracts = baseline.validate_all()
    current_by_slug = {
        contract.document["device"]["slug"]: contract for contract in current_contracts
    }
    baseline_by_slug = {
        contract.document["device"]["slug"]: contract for contract in baseline_contracts
    }
    removed = sorted(baseline_by_slug.keys() - current_by_slug.keys())
    if removed:
        _fail(
            str(current.root),
            "fixture contract(s) disappeared or changed device slug: "
            + ", ".join(removed),
        )
    messages: list[str] = []
    for slug in sorted(current_by_slug.keys() & baseline_by_slug.keys()):
        new = current_by_slug[slug]
        old = baseline_by_slug[slug]
        if new.interface_hash == old.interface_hash:
            if new.interface_revision != old.interface_revision:
                _fail(
                    str(new.path),
                    f"{slug}: interface hash is unchanged but revision moved "
                    f"{old.interface_revision} -> {new.interface_revision}",
                )
            continue
        if new.interface_revision <= old.interface_revision:
            _fail(
                str(new.path),
                f"{slug}: interface changed without increasing revision "
                f"{old.interface_revision}",
            )
        if old.qualification["status"] == "physically_qualified":
            if new.qualification["status"] == "physically_qualified":
                if _qualification_evidence_signature(
                    new.qualification
                ) == _qualification_evidence_signature(old.qualification):
                    _fail(
                        str(new.path),
                        f"{slug}: changed a physically qualified interface without "
                        "invalidating qualification or recording new acceptance evidence",
                    )
            elif new.qualification["status"] != "unqualified":
                _fail(
                    str(new.path),
                    f"{slug}: changed a physically qualified interface; status must become "
                    "'unqualified' or carry new physical acceptance",
                )
        messages.append(
            f"CHANGED {slug} revision={old.interface_revision}->{new.interface_revision} "
            f"hash={old.interface_hash[:12]}->{new.interface_hash[:12]}"
        )
    return messages


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main(argv: Sequence[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument(
        "--contract",
        action="append",
        type=Path,
        help="validate only this contract (repeatable; relative to --root)",
    )
    parser.add_argument(
        "--compare-root",
        type=Path,
        help="compare against a checked-out baseline tree",
    )
    parser.add_argument(
        "--print-interface-hash",
        type=Path,
        help="validate one contract and print its resolved interface hash",
    )
    args = parser.parse_args(argv)

    try:
        repository = ContractRepository(args.root)
        if args.print_interface_hash:
            selected = args.print_interface_hash
            if not selected.is_absolute():
                selected = repository.root / selected
            contract = repository.resolve(selected)
            print(contract.interface_hash)
            return 0

        selected_paths = None
        if args.contract:
            selected_paths = [
                path if path.is_absolute() else repository.root / path
                for path in args.contract
            ]
        contracts = repository.validate_all(selected_paths)
        for contract in contracts:
            kind = contract.document["kind"]
            print(
                f"PASS {_relative(contract.path, repository.root)} "
                f"kind={kind} revision={contract.interface_revision} "
                f"interface_sha256={contract.interface_hash}"
            )
        if args.compare_root:
            baseline = ContractRepository(args.compare_root)
            for message in compare_contract_roots(repository, baseline):
                print(message)
        print(f"PASS fixture-contracts count={len(contracts)}")
        return 0
    except ContractError as exc:
        print(f"FAIL fixture-contracts: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
