#!/usr/bin/env python3
"""core/profile.py — SoC-AGNOSTIC profile parser, family-merge, validator, resolver.

The ONLY place that reads a device profile. Loads devices/<id>/profile.toml, merges
the family defaults (families/<family>/family.toml) under it, validates the schema +
the family seam + the platform.lock references, and emits the resolved profile (JSON)
or flattened PF_* env for the family hooks.

Merge order (Armbian "board sourced first, family fills unset"): core defaults
< families/<family>/family.toml < devices/<id>/profile.toml.

This file is CORE and MUST stay SoC-agnostic: it may not contain any family
vocabulary (the banned token list lives in ci/core-purity-check.sh, which enforces
this; B8 makes it a CI gate).

Usage:
  profile.py list
  profile.py validate <id|--all>
  profile.py resolve  <id>            # merged profile as JSON
  profile.py env      <id>            # `export PF_*=...` lines for the dispatcher
  profile.py buildargs <id>           # docker `--build-arg` surface (lock-pinned SHAs)
  profile.py repos                    # platform.lock repo names + seeded state
"""
import sys, os, json, re, hashlib

try:
    import tomllib  # py3.11+
    def _load(p):
        with open(p, "rb") as f:
            return tomllib.load(f)
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
        def _load(p):
            with open(p, "rb") as f:
                return tomllib.load(f)
    except ModuleNotFoundError:
        sys.stderr.write("FATAL: need Python 3.11+ (tomllib) or the 'tomli' package.\n")
        sys.exit(3)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEVICES = os.path.join(ROOT, "devices")
# Lock selectors are repository-wide declarations. Keep their membership source
# canonical even when a caller temporarily redirects DEVICES to validate one
# synthetic profile tree.
LOCK_PROFILE_DEVICES = DEVICES
FAMILIES = os.path.join(ROOT, "families")
LOCK = os.path.join(ROOT, "platform.lock")
ABI_FAMILIES = os.path.join(ROOT, "abi", "families.toml")
PLATFORM_SUPPORT_SCHEMA = os.path.join(ROOT, "abi", "platform-capabilities.schema.json")
REQUIRED_HOOKS = ["build-kernel.sh", "build-bootchain.sh", "assemble-image.sh", "flash.sh"]
PROFILE_TABLE_SECTIONS = (
    "device", "kernel", "container", "flash", "image", "blobs", "gpu",
    "display", "bootchain", "toolchain",
)
PROFILE_PIN_KEYS = ("kernel", "uboot")
DEVICE_DESCRIPTOR_FILE = "capabilities.toml"
DEVICE_DESCRIPTOR_ID = re.compile(r"[a-z0-9][a-z0-9-]*")


class ProfileSchemaError(ValueError):
    """A loaded TOML document has the wrong schema shape."""


def _require_tables(data, sections):
    """Reject scalar/array sections before resolver code can dereference them."""
    for section in sections:
        if section in data and not isinstance(data[section], dict):
            raise ProfileSchemaError(f"[{section}] must be a table")


def _reject_derived_sections(data):
    """Keep ABI-registry-derived data out of device profiles."""
    if "app_runtime" in data:
        raise ProfileSchemaError(
            "[app_runtime] is derived from abi/families.toml and must not be declared in a profile")


def _platform_capability_names():
    """Return the runtime-known capability names admitted by the support-file schema."""
    try:
        with open(PLATFORM_SUPPORT_SCHEMA, encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
        names = schema["properties"]["supported_capabilities"]["items"]["enum"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ProfileSchemaError(
            f"cannot load platform support schema {PLATFORM_SUPPORT_SCHEMA}: {exc}") from exc
    if (not isinstance(names, list) or not names
            or any(not isinstance(name, str) or not name for name in names)
            or names != sorted(names) or len(names) != len(set(names))):
        raise ProfileSchemaError(
            "platform support schema capability enum must be a non-empty sorted unique string list")
    return set(names)


def _resolve_app_runtime_support(merged):
    """Resolve the optional launcher-facing support contract from the ABI registry.

    The registry family id and platform version remain the single source for those
    values. A family-local declaration selects the GPU models that receive the
    contract and supplies only the schema version, runtime ABI, and capability set.
    """
    try:
        registry = _load(ABI_FAMILIES)
    except (OSError, ValueError) as exc:
        raise ProfileSchemaError(
            f"cannot load ABI family registry {ABI_FAMILIES}: {exc}") from exc
    families = registry.get("family")
    if not isinstance(families, list) or not families:
        raise ProfileSchemaError("ABI family registry must contain [[family]] entries")

    device = merged.get("device", {})
    device_ids = set(_device_profile_lineage(device))
    matches = [family for family in families
               if isinstance(family, dict) and family.get("device") in device_ids]
    if len(matches) > 1:
        raise ProfileSchemaError(
            f"device '{device.get('id', '')}' matches multiple ABI family declarations")
    if not matches:
        return None

    family = matches[0]
    declaration = family.get("app_runtime")
    if declaration is None:
        return None
    if not isinstance(declaration, dict):
        raise ProfileSchemaError(
            f"ABI family '{family.get('id', '')}' app_runtime must be a table")
    allowed = {"schema_version", "gpu_models", "runtime_abi", "supported_capabilities"}
    unknown = sorted(set(declaration) - allowed)
    if unknown:
        raise ProfileSchemaError(
            f"ABI family '{family.get('id', '')}' app_runtime has unknown keys: "
            f"{', '.join(unknown)}")

    gpu_models = declaration.get("gpu_models")
    if (not isinstance(gpu_models, list) or not gpu_models
            or any(not isinstance(model, str) or not model for model in gpu_models)
            or gpu_models != sorted(gpu_models) or len(gpu_models) != len(set(gpu_models))):
        raise ProfileSchemaError(
            f"ABI family '{family.get('id', '')}' app_runtime.gpu_models must be "
            "a non-empty sorted unique string list")
    if merged.get("gpu", {}).get("model", "ddk") not in gpu_models:
        return None

    schema_version = declaration.get("schema_version")
    runtime_abi = declaration.get("runtime_abi")
    runtime_family = family.get("id")
    platform_version = family.get("platform_version")
    capabilities = declaration.get("supported_capabilities")
    if schema_version != 1:
        raise ProfileSchemaError(
            f"ABI family '{runtime_family}' app_runtime.schema_version must be 1")
    if not isinstance(runtime_family, str) or not re.fullmatch(r"pocketforge/[a-z0-9-]+", runtime_family):
        raise ProfileSchemaError("app runtime family must be a canonical pocketforge family id")
    if not isinstance(runtime_abi, str) or not re.fullmatch(r"[1-9][0-9]*", runtime_abi):
        raise ProfileSchemaError(
            f"ABI family '{runtime_family}' app_runtime.runtime_abi must be a positive integer string")
    if (not isinstance(platform_version, str)
            or not re.fullmatch(r"[1-9][0-9]*", platform_version)):
        raise ProfileSchemaError(
            f"ABI family '{runtime_family}' platform_version must be a positive integer string")
    if (not isinstance(capabilities, list)
            or any(not isinstance(capability, str) or not capability for capability in capabilities)):
        raise ProfileSchemaError(
            f"ABI family '{runtime_family}' app_runtime.supported_capabilities must be a string list")
    if capabilities != sorted(capabilities):
        raise ProfileSchemaError(
            f"ABI family '{runtime_family}' app_runtime.supported_capabilities must be sorted")
    if len(capabilities) != len(set(capabilities)):
        raise ProfileSchemaError(
            f"ABI family '{runtime_family}' app_runtime.supported_capabilities must be unique")
    unknown_capabilities = sorted(set(capabilities) - _platform_capability_names())
    if unknown_capabilities:
        raise ProfileSchemaError(
            f"ABI family '{runtime_family}' app_runtime.supported_capabilities contains "
            f"runtime-unknown values: {', '.join(unknown_capabilities)}")

    return {
        "schema_version": schema_version,
        "runtime_family": runtime_family,
        "runtime_abi": runtime_abi,
        "platform_version": platform_version,
        "supported_capabilities": capabilities,
    }


def _resolve_device_descriptor(merged):
    """Resolve the device capability descriptor staged alongside the app-runtime contract.

    Only a profile that receives the launcher-facing app-runtime contract stages a
    descriptor: the app facade reads it at runtime (PF_DESCRIPTOR). Every other profile
    returns None, so its build-arg surface stays byte-identical. The descriptor is joined
    by device id, a variant without its own file inherits its base device's file, and its
    [identity].id must equal the directory it came from (that id is also the install
    directory). Returns {"id", "path", "sha256"}; the bytes are staged verbatim, never
    re-rendered, so the SHA-256 pins exactly what the image installs.
    """
    if merged.get("app_runtime") is None:
        return None
    device = merged.get("device", {})
    candidates = _device_profile_lineage(device)
    for descriptor_id in candidates:
        if not isinstance(descriptor_id, str) or not descriptor_id:
            continue
        rel = f"devices/{descriptor_id}/{DEVICE_DESCRIPTOR_FILE}"
        path = os.path.join(ROOT, rel)
        if os.path.lexists(path):
            break
    else:
        raise ProfileSchemaError(
            f"device '{device.get('id', '')}' receives the app runtime contract but has no "
            f"devices/<id|base>/{DEVICE_DESCRIPTOR_FILE} device descriptor")
    if not DEVICE_DESCRIPTOR_ID.fullmatch(descriptor_id):
        raise ProfileSchemaError(
            f"device descriptor id '{descriptor_id}' is not a lowercase path-safe token")
    if os.path.islink(path) or not os.path.isfile(path):
        raise ProfileSchemaError(f"device descriptor {rel} must be a regular file")
    with open(path, "rb") as descriptor_file:
        data = descriptor_file.read()
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProfileSchemaError(f"device descriptor {rel} does not parse: {exc}") from exc
    identity = document.get("identity")
    if not isinstance(identity, dict) or identity.get("id") != descriptor_id:
        raise ProfileSchemaError(
            f"device descriptor {rel} [identity].id must be '{descriptor_id}'")
    return {"id": descriptor_id, "path": rel, "sha256": hashlib.sha256(data).hexdigest()}


def _list_devices_at(devices):
    if not os.path.isdir(devices):
        return []
    return sorted(d for d in os.listdir(devices)
                  if os.path.isfile(os.path.join(devices, d, "profile.toml")))


def list_devices():
    return _list_devices_at(DEVICES)


def _device_profile_lineage(device):
    """Return a profile id followed by its declared base chain, fail-closed on cycles."""
    device_id = device.get("id")
    base_id = device.get("base")
    lineage = []
    if isinstance(device_id, str) and device_id:
        lineage.append(device_id)
    seen = set(lineage)
    while isinstance(base_id, str) and base_id:
        if base_id in seen:
            raise ProfileSchemaError(
                f"device profile inheritance cycle at '{base_id}'")
        lineage.append(base_id)
        seen.add(base_id)
        base_path = os.path.join(DEVICES, base_id, "profile.toml")
        if not os.path.isfile(base_path):
            raise FileNotFoundError(
                f"device '{device_id}' base '{base_id}' has no profile at {base_path}")
        base = _load(base_path)
        base_id = base.get("device", {}).get("base")
    return lineage


def load_lock():
    if not os.path.isfile(LOCK):
        return {"seeded": False, "interim": False, "repos": {}, "profile_pins": {},
                "platform_runtime": {}, "platform_payload": {}}
    data = _load(LOCK)
    profile_pins = data.get("profile_pins", {})
    if not isinstance(profile_pins, dict):
        raise ProfileSchemaError("[profile_pins] must be a table")
    for profile_id, pins in profile_pins.items():
        if not isinstance(profile_id, str) or not profile_id:
            raise ProfileSchemaError("[profile_pins] keys must be non-empty profile IDs")
        if not isinstance(pins, dict):
            raise ProfileSchemaError(f"[profile_pins.{profile_id}] must be a table")
        unknown = sorted(set(pins) - set(PROFILE_PIN_KEYS))
        if unknown:
            raise ProfileSchemaError(
                f"[profile_pins.{profile_id}] unknown pin keys: {', '.join(unknown)}")
        for source, pin in pins.items():
            if not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{40}", pin):
                raise ProfileSchemaError(
                    f"[profile_pins.{profile_id}].{source} must be a full 40-hex SHA")
    repos = {r["name"]: r for r in data.get("repos", []) if "name" in r}
    platform_runtime = data.get("platform_runtime", {})
    if not isinstance(platform_runtime, dict):
        raise ProfileSchemaError("[platform_runtime] must be a table")
    profile_ids = set(_list_devices_at(LOCK_PROFILE_DEVICES))
    runtime_keys = {
        "schema_version", "profile", "mode_arg", "mode_value", "source_repo",
        "source_sha", "runtime_path", "build_args",
    }
    for runtime_id, runtime in platform_runtime.items():
        where = f"[platform_runtime.{runtime_id}]"
        if (not isinstance(runtime_id, str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9_]*", runtime_id)):
            raise ProfileSchemaError("[platform_runtime] keys must be lowercase path-safe IDs")
        if not isinstance(runtime, dict):
            raise ProfileSchemaError(f"{where} must be a table")
        unknown = sorted(set(runtime) - runtime_keys)
        if unknown:
            raise ProfileSchemaError(f"{where} unknown keys: {', '.join(unknown)}")
        if runtime.get("schema_version") != 1:
            raise ProfileSchemaError(f"{where}.schema_version must be 1")
        for key in ("profile", "mode_value", "source_repo"):
            if not isinstance(runtime.get(key), str) or not runtime[key]:
                raise ProfileSchemaError(f"{where}.{key} must be a non-empty string")
        if runtime["profile"] not in profile_ids:
            raise ProfileSchemaError(
                f"{where}.profile '{runtime['profile']}' is not a device profile")
        mode_arg = runtime.get("mode_arg")
        if not isinstance(mode_arg, str) or not re.fullmatch(r"PF_[A-Z0-9_]+", mode_arg):
            raise ProfileSchemaError(f"{where}.mode_arg must be a PF_* build-arg name")
        source_sha = runtime.get("source_sha")
        if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
            raise ProfileSchemaError(f"{where}.source_sha must be a full 40-hex SHA")
        runtime_path = runtime.get("runtime_path")
        if (not isinstance(runtime_path, str) or not runtime_path.startswith("/usr/lib/")
                or "/../" in runtime_path or not runtime_path.endswith("/v1")):
            raise ProfileSchemaError(f"{where}.runtime_path must be an absolute /usr/lib/.../v1 path")
        runtime_args = runtime.get("build_args")
        if not isinstance(runtime_args, dict) or not runtime_args:
            raise ProfileSchemaError(f"{where}.build_args must be a non-empty table")
        if mode_arg in runtime_args:
            raise ProfileSchemaError(f"{where}.build_args must not repeat mode_arg")
        for arg, value in runtime_args.items():
            if not isinstance(arg, str) or not re.fullmatch(r"PF_[A-Z0-9_]+", arg):
                raise ProfileSchemaError(f"{where}.build_args keys must be PF_* names")
            if not isinstance(value, str) or not value:
                raise ProfileSchemaError(f"{where}.build_args.{arg} must be a non-empty string")
        source = repos.get(runtime["source_repo"])
        if source is None:
            raise ProfileSchemaError(
                f"{where}.source_repo '{runtime['source_repo']}' is not in platform.lock")
        if source.get("sha") != source_sha:
            raise ProfileSchemaError(
                f"{where}.source_sha must equal the canonical {runtime['source_repo']} pin")
    platform_payload = data.get("platform_payload", {})
    if not isinstance(platform_payload, dict):
        raise ProfileSchemaError("[platform_payload] must be a table")
    payload_keys = {
        "schema_version", "profile", "variants", "mode_arg", "mode_value",
        "artifact_url_arg", "artifact_url", "artifact_sha256_arg",
        "artifact_sha256", "build_args",
    }
    for payload_id, payload in platform_payload.items():
        where = f"[platform_payload.{payload_id}]"
        if (not isinstance(payload_id, str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9_]*", payload_id)):
            raise ProfileSchemaError("[platform_payload] keys must be lowercase path-safe IDs")
        if not isinstance(payload, dict):
            raise ProfileSchemaError(f"{where} must be a table")
        unknown = sorted(set(payload) - payload_keys)
        if unknown:
            raise ProfileSchemaError(f"{where} unknown keys: {', '.join(unknown)}")
        if payload.get("schema_version") != 1:
            raise ProfileSchemaError(f"{where}.schema_version must be 1")
        for key in ("profile", "mode_value", "artifact_url", "artifact_sha256"):
            if not isinstance(payload.get(key), str) or not payload[key]:
                raise ProfileSchemaError(f"{where}.{key} must be a non-empty string")
        if payload["profile"] not in profile_ids:
            raise ProfileSchemaError(
                f"{where}.profile '{payload['profile']}' is not a device profile")
        variants = payload.get("variants")
        if variants != ["dev"]:
            raise ProfileSchemaError(f"{where}.variants must be exactly ['dev']")
        for key in ("mode_arg", "artifact_url_arg", "artifact_sha256_arg"):
            value = payload.get(key)
            if not isinstance(value, str) or not re.fullmatch(r"PF_[A-Z0-9_]+", value):
                raise ProfileSchemaError(f"{where}.{key} must be a PF_* build-arg name")
        selector_args = {
            payload["mode_arg"], payload["artifact_url_arg"],
            payload["artifact_sha256_arg"],
        }
        if len(selector_args) != 3:
            raise ProfileSchemaError(f"{where} selector build-arg names must be unique")
        digest = payload["artifact_sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ProfileSchemaError(f"{where}.artifact_sha256 must be a full SHA-256")
        url_pattern = rf"http://[^/?#]+/artifacts/sha256/{digest}/[A-Za-z0-9._-]+"
        if not re.fullmatch(url_pattern, payload["artifact_url"]):
            raise ProfileSchemaError(
                f"{where}.artifact_url must be a content-addressed HTTP artifact URL")
        payload_args = payload.get("build_args")
        if not isinstance(payload_args, dict) or not payload_args:
            raise ProfileSchemaError(f"{where}.build_args must be a non-empty table")
        collisions = sorted(selector_args & set(payload_args))
        if collisions:
            raise ProfileSchemaError(
                f"{where}.build_args repeats selector args: {', '.join(collisions)}")
        for arg, value in payload_args.items():
            if not isinstance(arg, str) or not re.fullmatch(r"PF_[A-Z0-9_]+", arg):
                raise ProfileSchemaError(f"{where}.build_args keys must be PF_* names")
            if not isinstance(value, str) or not value:
                raise ProfileSchemaError(f"{where}.build_args.{arg} must be a non-empty string")
    return {"seeded": bool(data.get("seeded", False)),
            "interim": bool(data.get("interim_seed", False)), "repos": repos,
            "profile_pins": profile_pins, "platform_runtime": platform_runtime,
            "platform_payload": platform_payload}


def _deep_fill(dst, src):
    """Fill keys present in src but absent in dst (src = lower precedence)."""
    for k, v in src.items():
        if isinstance(v, dict):
            dst.setdefault(k, {})
            if isinstance(dst[k], dict):
                _deep_fill(dst[k], v)
        else:
            dst.setdefault(k, v)


def resolve(dev_id):
    """Return (merged_profile_dict, family_dict)."""
    ppath = os.path.join(DEVICES, dev_id, "profile.toml")
    if not os.path.isfile(ppath):
        raise FileNotFoundError(f"no profile for device '{dev_id}' at {ppath}")
    profile = _load(ppath)
    _require_tables(profile, PROFILE_TABLE_SECTIONS + ("gamescope",))
    _reject_derived_sections(profile)
    # Device-level inheritance (tsp-147u.13): a VARIANT profile may declare
    # [device].base = "<other-device-id>" to inherit that device's ENTIRE profile,
    # restating only the sections it needs to differ (e.g. a133-owned inherits a133
    # wholesale, restating only [bootchain]). _deep_fill fills the base's keys UNDER
    # the variant (variant wins per-key), so the variant is provably identical to its
    # base except the sections/keys it explicitly restates — no drift, and the eventual
    # default-flip is a crisp "repoint the base's [bootchain]" diff, not a divergent
    # profile re-review. Bases are followed transitively so a narrowly scoped
    # child can extend an existing variant without losing that variant's family
    # defaults; cycles and missing links fail before any build args are emitted.
    base_id = profile.get("device", {}).get("base")
    seen = {dev_id}
    while base_id:
        if base_id in seen:
            raise ValueError(
                f"device '{dev_id}' profile inheritance cycle at '{base_id}'")
        seen.add(base_id)
        base_path = os.path.join(DEVICES, base_id, "profile.toml")
        if not os.path.isfile(base_path):
            raise FileNotFoundError(
                f"device '{dev_id}' base '{base_id}' has no profile at {base_path}")
        base = _load(base_path)
        _require_tables(base, PROFILE_TABLE_SECTIONS + ("gamescope",))
        _reject_derived_sections(base)
        _deep_fill(profile, base)  # variant wins; base fills absent keys
        base_id = base.get("device", {}).get("base")
    family_id = profile.get("device", {}).get("family")
    family = {}
    if family_id:
        fpath = os.path.join(FAMILIES, family_id, "family.toml")
        if os.path.isfile(fpath):
            family = _load(fpath)
            _require_tables(family, ("defaults", "flash", "toolchain"))
    # Merge family defaults UNDER the profile (profile wins).
    merged = json.loads(json.dumps(profile))  # deep copy
    fam_defaults = family.get("defaults", {})
    merged.setdefault("bootchain", {}).setdefault("boot_proto", fam_defaults.get("boot_proto"))
    merged.setdefault("image", {}).setdefault("partition_table", fam_defaults.get("partition_table"))
    merged.setdefault("flash", {}).setdefault("method", family.get("flash", {}).get("method"))
    merged["toolchain"] = {**family.get("toolchain", {}), **merged.get("toolchain", {})}
    # prune Nones introduced by setdefault
    for sect in ("bootchain", "image", "flash"):
        merged[sect] = {k: v for k, v in merged.get(sect, {}).items() if v is not None}
    app_runtime = _resolve_app_runtime_support(merged)
    if app_runtime is not None:
        merged["app_runtime"] = app_runtime
    return merged, family


def validate(dev_id, lock):
    """Return (errors, warnings) lists for one device."""
    errs, warns = [], []
    try:
        merged, family = resolve(dev_id)
    except ProfileSchemaError as e:
        return ([f"{dev_id}: {e}"], [])
    except Exception as e:
        return ([f"{dev_id}: cannot load/parse: {e}"], [])
    try:
        _resolve_device_descriptor(merged)
    except ProfileSchemaError as e:
        return ([f"{dev_id}: {e}"], [])

    def table(section, value):
        if isinstance(value, dict):
            return value
        errs.append(f"{dev_id}: {section} must be a table")
        return {}

    dev = table("[device]", merged.get("device", {}))
    is_example = dev.get("status") == "example"
    repo_sev = warns if not is_example else None  # example: repo-absence is INFO (silent)

    for key in ("id", "family", "arch", "soc"):
        if not dev.get(key):
            errs.append(f"{dev_id}: [device].{key} is required")

    fam = dev.get("family")
    if fam:
        fdir = os.path.join(FAMILIES, fam)
        if not os.path.isdir(fdir):
            errs.append(f"{dev_id}: family '{fam}' has no plugin dir families/{fam}/")
        else:
            if not os.path.isfile(os.path.join(fdir, "family.toml")):
                errs.append(f"{dev_id}: families/{fam}/family.toml missing")
            for h in REQUIRED_HOOKS:
                if not os.path.isfile(os.path.join(fdir, h)):
                    errs.append(f"{dev_id}: family '{fam}' missing hook {h}")

    k = table("[kernel]", merged.get("kernel", {}))
    if not k.get("repo"):
        errs.append(f"{dev_id}: [kernel].repo is required")
    if not k.get("ref"):
        errs.append(f"{dev_id}: [kernel].ref is required")
    container = table("[container]", merged.get("container", {}))
    flash = table("[flash]", merged.get("flash", {}))
    image = table("[image]", merged.get("image", {}))
    blobs = table("[blobs]", merged.get("blobs", {}))
    gpu = table("[gpu]", merged.get("gpu", {}))
    display = table("[display]", merged.get("display", {}))
    gamescope = table("[gamescope]", merged.get("gamescope", {}))
    bc = table("[bootchain]", merged.get("bootchain", {}))

    if not container.get("build_image"):
        errs.append(f"{dev_id}: [container].build_image is required")
    if not flash.get("method"):
        errs.append(f"{dev_id}: [flash].method is required (profile or family default)")
    if not image.get("image_name"):
        errs.append(f"{dev_id}: [image].image_name is required")

    # type checks
    grp = blobs.get("groups")
    if grp is not None and not isinstance(grp, list):
        errs.append(f"{dev_id}: [blobs].groups must be a list")
    mods = gpu.get("modules")
    if mods is not None and not isinstance(mods, list):
        errs.append(f"{dev_id}: [gpu].modules must be a list")
    required_modules = k.get("required_modules")
    if required_modules is not None and not isinstance(required_modules, list):
        errs.append(f"{dev_id}: [kernel].required_modules must be a list")

    # Display availability is independent of GPU acceleration. A framebuffer
    # may be provided by a display controller with no GPU stack at all.
    pipeline = display.get("pipeline")
    if pipeline not in ("fbdev", "drm", "none"):
        errs.append(
            f"{dev_id}: [display].pipeline is required and must be 'fbdev', 'drm', or 'none'")

    if gamescope:
        allowed = {
            "mode", "repo", "ref", "upstream_base", "present_head", "staging_head",
            "rotation_head", "required_patch_ids", "patch_series_sha256",
            "dependency_manifest_sha256", "source_tree_sha256",
            "license_sha256", "diagnostics",
        }
        unknown = sorted(set(gamescope) - allowed)
        if unknown:
            errs.append(f"{dev_id}: [gamescope] unknown keys: {', '.join(unknown)}")
        for key in ("repo", "ref"):
            if not isinstance(gamescope.get(key), str) or not gamescope[key]:
                errs.append(f"{dev_id}: [gamescope].{key} is required")
        if gamescope.get("mode") != "g1":
            errs.append(f"{dev_id}: [gamescope].mode must be 'g1'")
        for key in ("upstream_base", "present_head", "staging_head", "rotation_head"):
            if not isinstance(gamescope.get(key), str) or not re.fullmatch(
                    r"[0-9a-f]{40}", gamescope[key]):
                errs.append(f"{dev_id}: [gamescope].{key} must be a full 40-hex SHA")
        for key in ("patch_series_sha256", "dependency_manifest_sha256",
                    "source_tree_sha256", "license_sha256"):
            if not isinstance(gamescope.get(key), str) or not re.fullmatch(
                    r"[0-9a-f]{64}", gamescope[key]):
                errs.append(f"{dev_id}: [gamescope].{key} must be a full SHA-256")
        patch_ids = gamescope.get("required_patch_ids")
        if (not isinstance(patch_ids, list) or not patch_ids
                or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value)
                       for value in patch_ids)
                or len(patch_ids) != len(set(patch_ids))):
            errs.append(
                f"{dev_id}: [gamescope].required_patch_ids must be unique stable patch IDs")
        if not isinstance(gamescope.get("diagnostics"), bool):
            errs.append(f"{dev_id}: [gamescope].diagnostics must be boolean")

    # GPU stack selection is explicit.  Legacy profiles remain the closed/DDK
    # model, open profiles must completely describe both halves of the ABI, and
    # "none" profiles deliberately build without a GPU stack.  Never let a
    # GPU-less bring-up profile inherit source/module inputs from its base.
    model = gpu.get("model", "ddk")
    if model not in ("ddk", "open", "none"):
        errs.append(f"{dev_id}: [gpu].model must be 'ddk', 'open', or 'none'")
    if model == "open":
        required = ("km_model", "km_repo", "km_ref", "um_repo", "um_ref")
        for key in required:
            if not gpu.get(key):
                errs.append(f"{dev_id}: open [gpu].{key} is required")
        if gpu.get("km_model") not in ("in-tree-6.x", "in-tree-7.x"):
            errs.append(
                f"{dev_id}: open [gpu].km_model must be 'in-tree-6.x' or 'in-tree-7.x'")
        if gpu.get("repo") or gpu.get("ref"):
            errs.append(f"{dev_id}: open [gpu] is ambiguous: legacy repo/ref must be cleared")
        if not required_modules:
            errs.append(f"{dev_id}: open [kernel].required_modules must be a non-empty list")
        elif isinstance(required_modules, list):
            invalid = [name for name in required_modules
                       if not isinstance(name, str)
                       or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name)]
            if invalid:
                errs.append(
                    f"{dev_id}: [kernel].required_modules entries must be canonical module names")
            if len(required_modules) != len(set(
                    name for name in required_modules if isinstance(name, str))):
                errs.append(f"{dev_id}: [kernel].required_modules must not contain duplicates")
            if "powervr" not in required_modules:
                errs.append(f"{dev_id}: open [kernel].required_modules must include 'powervr'")
    elif model == "none":
        forbidden = ("repo", "ref", "km_model", "km_repo", "km_ref",
                     "um_repo", "um_ref")
        populated = [key for key in forbidden if gpu.get(key)]
        if populated or gpu.get("modules"):
            errs.append(
                f"{dev_id}: none [gpu] must not select repos, refs, KM/UM models, or modules")

    # bootchain duality: either a source repo OR a blob group
    uboot = table("[bootchain.uboot]", bc.get("uboot", {}))
    tfa = table("[bootchain.tfa]", bc.get("tfa", {}))
    has_src = bool(uboot.get("repo"))
    has_blob = bool(bc.get("blob_group"))
    if not (has_src or has_blob):
        errs.append(f"{dev_id}: [bootchain] needs either uboot.repo (source) or blob_group")

    # platform.lock references (repo must be listed; example devices exempt)
    def check_repo(name, where):
        if not name or name == "none":
            return
        if name not in lock["repos"]:
            msg = f"{dev_id}: {where} repo '{name}' not in platform.lock"
            if repo_sev is not None:
                repo_sev.append(msg)
    check_repo(k.get("repo"), "[kernel]")
    check_repo(gpu.get("repo"), "[gpu]")
    check_repo(gpu.get("km_repo"), "[gpu].km")
    check_repo(gpu.get("um_repo"), "[gpu].um")
    check_repo(uboot.get("repo"), "[bootchain].uboot")
    check_repo(tfa.get("repo"), "[bootchain].tfa")
    check_repo(gamescope.get("repo"), "[gamescope]")

    if not lock["seeded"] and not is_example:
        if lock.get("interim"):
            warns.append(f"{dev_id}: platform.lock is INTERIM-seeded (dev-only, non-authoritative) — "
                         f"dev builds resolve real SHAs; RELEASE builds blocked until the authoritative "
                         f"re-seed (post-B2 hardware retest, tsp-1dl.1.1)")
        else:
            warns.append(f"{dev_id}: platform.lock not seeded (SHAs empty) — builds cannot resolve SHAs "
                         f"until seeded (`pf lock --interim`, tsp-1dl.1.1)")
    return errs, warns


def env_lines(dev_id):
    merged, family = resolve(dev_id)
    repos = load_lock()["repos"]
    sha = lambda name: (repos.get(name or "", {}) or {}).get("sha", "") or ""
    dev = merged["device"]
    bc = merged.get("bootchain", {})
    gpu = merged.get("gpu", {})
    display = merged.get("display", {})
    img = merged.get("image", {})
    flash = merged.get("flash", {})
    tc = merged.get("toolchain", {})
    out = {
        "PF_DEVICE_ID": dev.get("id"), "PF_DEVICE_NAME": dev.get("name"),
        "PF_SOC": dev.get("soc"), "PF_ARCH": dev.get("arch"), "PF_FAMILY": dev.get("family"),
        "PF_KERNEL_REPO": merged.get("kernel", {}).get("repo"),
        "PF_KERNEL_REF": merged.get("kernel", {}).get("ref"),
        "PF_KERNEL_DEFCONFIG": merged.get("kernel", {}).get("defconfig"),
        "PF_KERNEL_DTB": merged.get("kernel", {}).get("dtb"),
        "PF_KERNEL_REQUIRED_MODULES": " ".join(
            merged.get("kernel", {}).get("required_modules", []) or []),
        "PF_GPU_MODEL": gpu.get("model", "ddk"),
        "PF_GPU_REPO": gpu.get("repo"), "PF_GPU_REF": gpu.get("ref"),
        "PF_GPU_KM_MODEL": gpu.get("km_model", "out-of-tree-ddk"),
        "PF_GPU_KM_REPO": gpu.get("km_repo", gpu.get("repo", "")),
        "PF_GPU_KM_REF": gpu.get("km_ref", gpu.get("ref", "")),
        "PF_GPU_KM_SHA": sha(gpu.get("km_repo", gpu.get("repo"))),
        "PF_GPU_UM_REPO": gpu.get("um_repo", ""),
        "PF_GPU_UM_REF": gpu.get("um_ref", ""),
        "PF_GPU_UM_SHA": sha(gpu.get("um_repo")),
        "PF_GPU_MODULES": " ".join(gpu.get("modules", []) or []),
        "PF_DISPLAY_PIPELINE": display.get("pipeline", ""),
        "PF_BOOTCHAIN_MODEL": bc.get("model"), "PF_BOOT_PROTO": bc.get("boot_proto"),
        "PF_BOOTCHAIN_BLOB_GROUP": bc.get("blob_group", ""),
        "PF_UBOOT_REPO": bc.get("uboot", {}).get("repo", ""),
        "PF_SPL_OFFSET_KIB": bc.get("spl_offset_kib", ""),
        "PF_IMAGE_ASSEMBLER": img.get("assembler"), "PF_IMAGE_NAME": img.get("image_name"),
        "PF_PART_TABLE": img.get("partition_table"),
        "PF_BOOT_LABEL": img.get("boot_label"), "PF_ROOT_LABEL": img.get("root_label"),
        "PF_BLOB_GROUPS": " ".join(merged.get("blobs", {}).get("groups", []) or []),
        "PF_BUILD_IMAGE": merged.get("container", {}).get("build_image"),
        "PF_FLASH_METHOD": flash.get("method"), "PF_FLASH_SLOT": flash.get("slot", ""),
        "PF_TOOLCHAIN_CC": tc.get("cc", ""),
        "PF_TOOLCHAIN_GCC_VERSION": tc.get("gcc_version", ""),
        "PF_TOOLCHAIN_CFLAGS_EXTRA": tc.get("cflags_extra", ""),
    }
    lines = []
    for kk, vv in out.items():
        if vv is None:
            vv = ""
        lines.append(f"export {kk}={json.dumps(str(vv))}")
    return lines


def build_args(dev_id, variant="dev"):
    """Resolve a device's `docker build --build-arg` surface: every source repo the
    multistage os-image build consumes, pinned to its platform.lock SHA (never a branch
    tip). Returns (args_dict, lock). The build must use these SHAs, not the profile ref
    (B4 / tsp-1dl.4). Emitted by `profile.py buildargs <id>` for core/pf-build.sh."""
    merged, _family = resolve(dev_id)
    lock = load_lock()
    repos = lock["repos"]

    def sha(name):
        return (repos.get(name or "", {}) or {}).get("sha", "") or ""

    dev = merged["device"]
    k = merged.get("kernel", {})
    gpu = merged.get("gpu", {})
    display = merged.get("display", {})
    gamescope = merged.get("gamescope", {})
    bc = merged.get("bootchain", {})
    tc = merged.get("toolchain", {})
    img = merged.get("image", {})
    uboot_repo = bc.get("uboot", {}).get("repo", "") or ""
    tfa_repo = bc.get("tfa", {}).get("repo", "") or ""
    kernel_repo = k.get("repo", "") or ""
    canonical_kernel_sha = sha(kernel_repo)
    canonical_uboot_sha = sha(uboot_repo)
    # A profile pin selects a revision of the declared, canonically pinned source;
    # it must never make a missing repo or missing normal pin look complete to the
    # existing needed/missing-pin gate.
    uboot_sha = (
        lock["profile_pins"].get(dev_id, {}).get("uboot", canonical_uboot_sha)
        if canonical_uboot_sha else ""
    )
    kernel_sha = (
        lock["profile_pins"].get(dev_id, {}).get("kernel", canonical_kernel_sha)
        if canonical_kernel_sha else ""
    )
    gpu_km_repo = gpu.get("km_repo", gpu.get("repo", "")) or ""
    gpu_km_sha = kernel_sha if gpu_km_repo == kernel_repo else sha(gpu_km_repo)

    args = {
        "PF_DEVICE_ID": dev.get("id", ""),
        "PF_FAMILY": dev.get("family", ""),
        "PF_ARCH": dev.get("arch", ""),
        # Declarative device-family discriminator (tsp-mc9m.41.924.2 / B1): the ONLY
        # sanctioned "is this an a133" build-arg — replaces the PF_GPU_REPO proxy that
        # broke under the a133-open profile (gpu.repo == "" there). Base-inherited, so
        # every a133 variant (closed/open/owned) resolves the same value.
        "PF_SOC": dev.get("soc", ""),
        "PF_KERNEL_REPO": k.get("repo", ""),
        "PF_KERNEL_REF": k.get("ref", ""),
        "PF_KERNEL_SHA": kernel_sha,
        "PF_KERNEL_DEFCONFIG": k.get("defconfig", ""),
        "PF_KERNEL_DTB": k.get("dtb", ""),
        "PF_KERNEL_REQUIRED_MODULES": " ".join(k.get("required_modules", []) or []),
        "PF_GPU_MODEL": gpu.get("model", "ddk"),
        "PF_GPU_REPO": gpu.get("repo", ""),
        "PF_GPU_REF": gpu.get("ref", ""),
        "PF_GPU_SHA": sha(gpu.get("repo")),
        "PF_GPU_MODULES": " ".join(gpu.get("modules", []) or []),
        "PF_DISPLAY_PIPELINE": display.get("pipeline", ""),
        "PF_GPU_KM_MODEL": gpu.get("km_model", "out-of-tree-ddk"),
        "PF_GPU_KM_REPO": gpu_km_repo,
        "PF_GPU_KM_REF": gpu.get("km_ref", gpu.get("ref", "")),
        "PF_GPU_KM_SHA": gpu_km_sha,
        "PF_GPU_UM_REPO": gpu.get("um_repo", ""),
        "PF_GPU_UM_REF": gpu.get("um_ref", ""),
        "PF_GPU_UM_SHA": sha(gpu.get("um_repo")),
        "PF_LIBSDL3_SHA": sha("libsdl3-sunxifb"),
        "PF_WPA_SHA": sha("wpa-supplicant-tsp"),
        # E2 runtime layer (tsp-e1b.11): the image's `runtime` Dockerfile.pf stage cross-builds
        # pf-input-decode from this SHA. Literal-name lookup like libsdl3/wpa — not-per-device, so
        # it is not driven off a profile section. Missing SHA fails at pf_stage_sources (not in the
        # `needed` list below — same as libsdl3/wpa, which are also universal userspace repos).
        "PF_RUNTIME_SHA": sha("runtime"),
        # pf-shell launcher (tsp-mc9m.41.924.4 / top-coord RULING B): OPEN-ONLY. Emitted with the
        # real platform.lock SHA for PF_GPU_MODEL=open; resolves EMPTY for the ddk path (closed a133
        # + a523), exactly as PF_GPU_UM_SHA is empty for non-open. The Dockerfile launcher stage's
        # ARG-selected model-selector routes ddk to a NOT-SHIPPED stub that never COPYs launcher-src,
        # so the ddk images stay byte-identical (the launcher is source-built ONLY on a133-open).
        "PF_LAUNCHER_REPO": "launcher" if gpu.get("model") == "open" else "",
        "PF_LAUNCHER_REF": ((repos.get("launcher", {}) or {}).get("ref", "")
                            if gpu.get("model") == "open" else ""),
        "PF_LAUNCHER_SHA": sha("launcher") if gpu.get("model") == "open" else "",
        # recovery entry (tsp-mc9m.41.924.4 / top-coord RULING B): OPEN-ONLY, same op5a userspace
        # wave as the launcher. Real SHA for PF_GPU_MODEL=open; empty for the ddk path (closed a133
        # + a523) so the Dockerfile recovery-ddk NOT-SHIPPED stub never references recovery-src and
        # the ddk images stay byte-identical (no pocketforge-recovery-entry).
        "PF_RECOVERY_REPO": "recovery" if gpu.get("model") == "open" else "",
        "PF_RECOVERY_REF": ((repos.get("recovery", {}) or {}).get("ref", "")
                            if gpu.get("model") == "open" else ""),
        "PF_RECOVERY_SHA": sha("recovery") if gpu.get("model") == "open" else "",
        "PF_SIM_SHA": sha("sim") if variant == "dev" else "",
        "PF_HWPROBE_SHA": sha("pf-hwprobe") if variant == "dev" else "",
        # Poolsuite is a dev-image-only source context. Release still emits the build arg,
        # deliberately empty, so the image Dockerfile can select a NOT-SHIPPED stage without
        # making the build-argument surface variant-dependent.
        "PF_POOLSUITE_SHA": sha("poolsuite") if variant == "dev" else "",
        "PF_IMAGE_SHA": sha("image"),
        "PF_IMAGE_NAME": img.get("image_name", ""),
        "PF_IMAGE_ASSEMBLER": img.get("assembler", ""),
        "PF_BLOBS_SHA": sha("blobs"),
        "PF_VENDOR_MANIFEST_SHA": sha("vendor-manifest"),
        "PF_BLOB_GROUPS": " ".join(sorted(merged.get("blobs", {}).get("groups", []) or [])),
        "PF_BOOTCHAIN_MODEL": bc.get("model", ""),
        "PF_BOOT_PROTO": bc.get("boot_proto", ""),
        "PF_BOOTCHAIN_BLOB_GROUP": bc.get("blob_group", "") or "",
        "PF_TOOLCHAIN_GCC_VERSION": tc.get("gcc_version", ""),
        "PF_UBOOT_REPO": uboot_repo,
        "PF_UBOOT_SHA": uboot_sha,
        "PF_UBOOT_DEFCONFIG": bc.get("uboot", {}).get("defconfig", "") or "",
        "PF_TFA_REPO": tfa_repo,
        "PF_TFA_SHA": sha(tfa_repo),
        "PF_TFA_PLAT": bc.get("tfa", {}).get("plat", "") or "",
        # SPL raw offset for the owned-SPL assemble path (a133 = 128 KiB / 0x20000, a523 = 8;
        # emitted by env_lines() but was DEAD for the container path — the assemble stage's
        # owned-SPL branch consumes it to place u-boot-sunxi-with-spl.bin. tsp-147u.13).
        "PF_SPL_OFFSET_KIB": str(bc.get("spl_offset_kib", "") or ""),
    }
    if gamescope:
        gamescope_repo = gamescope.get("repo", "")
        source = repos.get(gamescope_repo, {}) or {}
        if source.get("url") != "https://github.com/pocketforge-os/gamescope.git":
            raise ProfileSchemaError(
                "[gamescope] source must be the governed PocketForge Gamescope fork")
        args.update({
            "PF_GAMESCOPE_MODE": gamescope["mode"],
            "PF_GAMESCOPE_REPO": gamescope_repo,
            "PF_GAMESCOPE_REPO_URL": source["url"],
            "PF_GAMESCOPE_REF": gamescope["ref"],
            "PF_GAMESCOPE_SHA": sha(gamescope_repo),
            "PF_GAMESCOPE_UPSTREAM_BASE": gamescope["upstream_base"],
            "PF_GAMESCOPE_PRESENT_HEAD": gamescope["present_head"],
            "PF_GAMESCOPE_STAGING_HEAD": gamescope["staging_head"],
            "PF_GAMESCOPE_ROTATION_HEAD": gamescope["rotation_head"],
            "PF_GAMESCOPE_REQUIRED_PATCH_IDS": " ".join(gamescope["required_patch_ids"]),
            "PF_GAMESCOPE_PATCH_SERIES_SHA256": gamescope["patch_series_sha256"],
            "PF_GAMESCOPE_DEPENDENCY_MANIFEST_SHA256":
                gamescope["dependency_manifest_sha256"],
            "PF_GAMESCOPE_SOURCE_TREE_SHA256": gamescope["source_tree_sha256"],
            "PF_GAMESCOPE_LICENSE_SHA256": gamescope["license_sha256"],
            "PF_GAMESCOPE_DIAGNOSTICS":
                "1" if variant == "dev" and gamescope["diagnostics"] else "0",
        })
    app_runtime = merged.get("app_runtime")
    if app_runtime is not None:
        args.update({
            "PF_APP_RUNTIME_FAMILY": app_runtime["runtime_family"],
            "PF_APP_RUNTIME_ABI": app_runtime["runtime_abi"],
            "PF_APP_PLATFORM_VERSION": app_runtime["platform_version"],
            "PF_APP_CAPABILITIES": " ".join(app_runtime["supported_capabilities"]),
        })
    # Platform-owned device descriptor (tsp-f3fm.202.1 R1): emitted ONLY with the app-runtime
    # contract, so every other profile's build-arg surface is byte-identical (no empty keys).
    # core/pf-build.sh stages the verbatim bytes as the `platform-inputs-src` named context at
    # devices/<PF_DEVICE_DESCRIPTOR_ID>/capabilities.toml; the image verifies the SHA-256 and
    # installs it at /usr/share/pocketforge/devices/<PF_DEVICE_DESCRIPTOR_ID>/capabilities.toml.
    descriptor = _resolve_device_descriptor(merged)
    if descriptor is not None:
        args.update({
            "PF_DEVICE_DESCRIPTOR_ID": descriptor["id"],
            "PF_DEVICE_DESCRIPTOR_SHA256": descriptor["sha256"],
        })
    # Optional platform-owned compatibility payloads are selected by a profile
    # in the explicit inheritance lineage. The lock describes their build-arg
    # surface generically so core does not learn a consumer, codec, or hardware
    # implementation. Siblings do not inherit a payload accidentally. A
    # payload that consumes kernel source must match both the selected repo and
    # the profile-resolved revision.
    profile_lineage = set(_device_profile_lineage(merged["device"]))
    for runtime_id, runtime in lock["platform_runtime"].items():
        if runtime["profile"] not in profile_lineage:
            continue
        if not kernel_sha:
            # Preserve the existing missing-pin diagnostic surface. The payload
            # cannot be selected until the normal source gate has a revision.
            continue
        if runtime["source_repo"] != kernel_repo or runtime["source_sha"] != kernel_sha:
            raise ProfileSchemaError(
                f"platform runtime '{runtime_id}' source does not match profile '{dev_id}' kernel")
        selected_args = {runtime["mode_arg"]: runtime["mode_value"], **runtime["build_args"]}
        collisions = sorted(set(args) & set(selected_args))
        if collisions:
            raise ProfileSchemaError(
                f"platform runtime '{runtime_id}' build-arg collisions: {', '.join(collisions)}")
        args.update(selected_args)
    # Immutable external payloads use the same exact-profile selection model,
    # but are content-addressed artifacts rather than source-coupled runtimes.
    # They are intentionally dev-only so a release build cannot acquire test
    # payload bytes through a profile selector.
    for payload_id, payload in lock["platform_payload"].items():
        if payload["profile"] != dev_id or variant not in payload["variants"]:
            continue
        selected_args = {
            payload["mode_arg"]: payload["mode_value"],
            payload["artifact_url_arg"]: payload["artifact_url"],
            payload["artifact_sha256_arg"]: payload["artifact_sha256"],
            **payload["build_args"],
        }
        collisions = sorted(set(args) & set(selected_args))
        if collisions:
            raise ProfileSchemaError(
                f"platform payload '{payload_id}' build-arg collisions: "
                f"{', '.join(collisions)}")
        args.update(selected_args)
    # Repos this device genuinely needs a SHA for (repo named, not the "none" sentinel).
    needed = [("PF_KERNEL_SHA", k.get("repo")), ("PF_IMAGE_SHA", "image"),
              ("PF_BLOBS_SHA", "blobs"), ("PF_VENDOR_MANIFEST_SHA", "vendor-manifest")]
    if (gpu.get("repo") or "none") != "none":
        needed.append(("PF_GPU_SHA", gpu.get("repo")))
    if gpu.get("model") == "open":
        needed.extend((("PF_GPU_KM_SHA", gpu.get("km_repo")),
                       ("PF_GPU_UM_SHA", gpu.get("um_repo"))))
        # OPEN builds source-build pf-shell + the recovery entry — both SHAs mandatory (tsp-mc9m.41.924.4).
        needed.append(("PF_LAUNCHER_SHA", "launcher"))
        needed.append(("PF_RECOVERY_SHA", "recovery"))
    if uboot_repo:
        needed.append(("PF_UBOOT_SHA", uboot_repo))
    if tfa_repo:
        needed.append(("PF_TFA_SHA", tfa_repo))
    if gamescope:
        needed.append(("PF_GAMESCOPE_SHA", gamescope.get("repo")))
    missing = [ak for ak, rn in needed if rn and not args.get(ak)]
    state = "authoritative" if lock["seeded"] else ("interim" if lock.get("interim") else "unseeded")
    return args, state, missing


def main(argv):
    if not argv:
        sys.stderr.write(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "list":
        print("\n".join(list_devices()))
        return 0
    if cmd == "repos":
        lock = load_lock()
        state = "authoritative" if lock["seeded"] else ("interim" if lock.get("interim") else "unseeded")
        print(f"seeded={lock['seeded']} state={state}")
        for n, r in sorted(lock["repos"].items()):
            print(f"  {n}\t{r.get('ref','')}\t{r.get('sha','') or '(unseeded)'}")
        return 0
    if cmd == "validate":
        lock = load_lock()
        targets = list_devices() if (len(argv) > 1 and argv[1] == "--all") else argv[1:]
        if not targets:
            sys.stderr.write("validate: give a device id or --all\n")
            return 2
        total_err = 0
        for d in targets:
            errs, warns = validate(d, lock)
            for w in warns:
                print(f"WARN  {w}")
            for e in errs:
                print(f"ERROR {e}")
            if not errs:
                print(f"OK    {d}: profile valid")
            total_err += len(errs)
        return 1 if total_err else 0
    if cmd == "resolve":
        if len(argv) < 2:
            sys.stderr.write("resolve: give a device id\n"); return 2
        errors, _ = validate(argv[1], load_lock())
        if errors:
            print("\n".join(f"ERROR {e}" for e in errors), file=sys.stderr)
            return 1
        merged, _ = resolve(argv[1])
        print(json.dumps(merged, indent=2, sort_keys=True))
        return 0
    if cmd == "env":
        if len(argv) < 2:
            sys.stderr.write("env: give a device id\n"); return 2
        errors, _ = validate(argv[1], load_lock())
        if errors:
            print("\n".join(f"ERROR {e}" for e in errors), file=sys.stderr)
            return 1
        print("\n".join(env_lines(argv[1])))
        return 0
    if cmd == "buildargs":
        if len(argv) < 2:
            sys.stderr.write("buildargs: give a device id\n"); return 2
        errors, _ = validate(argv[1], load_lock())
        if errors:
            print("\n".join(f"ERROR {e}" for e in errors), file=sys.stderr)
            return 1
        variant = argv[2] if len(argv) > 2 else "dev"
        if variant not in ("dev", "release"):
            sys.stderr.write("buildargs: variant must be dev or release\n"); return 2
        args, state, missing = build_args(argv[1], variant)
        for kk in sorted(args):
            print(f"{kk}={args[kk]}")
        print(f"PF_LOCK_STATE={state}")
        print(f"PF_LOCK_MISSING_SHAS={','.join(missing)}")
        return 0
    sys.stderr.write(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
