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
import sys, os, json

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
FAMILIES = os.path.join(ROOT, "families")
LOCK = os.path.join(ROOT, "platform.lock")
REQUIRED_HOOKS = ["build-kernel.sh", "build-bootchain.sh", "assemble-image.sh", "flash.sh"]


def list_devices():
    if not os.path.isdir(DEVICES):
        return []
    return sorted(d for d in os.listdir(DEVICES)
                  if os.path.isfile(os.path.join(DEVICES, d, "profile.toml")))


def load_lock():
    if not os.path.isfile(LOCK):
        return {"seeded": False, "interim": False, "repos": {}}
    data = _load(LOCK)
    repos = {r["name"]: r for r in data.get("repos", []) if "name" in r}
    return {"seeded": bool(data.get("seeded", False)),
            "interim": bool(data.get("interim_seed", False)), "repos": repos}


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
    family_id = profile.get("device", {}).get("family")
    family = {}
    if family_id:
        fpath = os.path.join(FAMILIES, family_id, "family.toml")
        if os.path.isfile(fpath):
            family = _load(fpath)
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
    return merged, family


def validate(dev_id, lock):
    """Return (errors, warnings) lists for one device."""
    errs, warns = [], []
    try:
        merged, family = resolve(dev_id)
    except Exception as e:
        return ([f"{dev_id}: cannot load/parse: {e}"], [])

    dev = merged.get("device", {})
    is_example = dev.get("status") == "example"
    repo_sev = warns if not is_example else None  # example: repo-absence is INFO (silent)

    for key in ("id", "family", "arch"):
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

    k = merged.get("kernel", {})
    if not k.get("repo"):
        errs.append(f"{dev_id}: [kernel].repo is required")
    if not k.get("ref"):
        errs.append(f"{dev_id}: [kernel].ref is required")
    if not merged.get("container", {}).get("build_image"):
        errs.append(f"{dev_id}: [container].build_image is required")
    if not merged.get("flash", {}).get("method"):
        errs.append(f"{dev_id}: [flash].method is required (profile or family default)")
    if not merged.get("image", {}).get("image_name"):
        errs.append(f"{dev_id}: [image].image_name is required")

    # type checks
    grp = merged.get("blobs", {}).get("groups")
    if grp is not None and not isinstance(grp, list):
        errs.append(f"{dev_id}: [blobs].groups must be a list")
    mods = merged.get("gpu", {}).get("modules")
    if mods is not None and not isinstance(mods, list):
        errs.append(f"{dev_id}: [gpu].modules must be a list")

    # bootchain duality: either a source repo OR a blob group
    bc = merged.get("bootchain", {})
    has_src = bool(bc.get("uboot", {}).get("repo"))
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
    check_repo(merged.get("gpu", {}).get("repo"), "[gpu]")
    check_repo(bc.get("uboot", {}).get("repo"), "[bootchain].uboot")
    check_repo(bc.get("tfa", {}).get("repo"), "[bootchain].tfa")

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
    dev = merged["device"]
    bc = merged.get("bootchain", {})
    gpu = merged.get("gpu", {})
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
        "PF_GPU_REPO": gpu.get("repo"), "PF_GPU_REF": gpu.get("ref"),
        "PF_GPU_MODULES": " ".join(gpu.get("modules", []) or []),
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


def build_args(dev_id):
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
    bc = merged.get("bootchain", {})
    tc = merged.get("toolchain", {})
    img = merged.get("image", {})
    uboot_repo = bc.get("uboot", {}).get("repo", "") or ""

    args = {
        "PF_DEVICE_ID": dev.get("id", ""),
        "PF_FAMILY": dev.get("family", ""),
        "PF_ARCH": dev.get("arch", ""),
        "PF_KERNEL_REPO": k.get("repo", ""),
        "PF_KERNEL_REF": k.get("ref", ""),
        "PF_KERNEL_SHA": sha(k.get("repo")),
        "PF_KERNEL_DEFCONFIG": k.get("defconfig", ""),
        "PF_KERNEL_DTB": k.get("dtb", ""),
        "PF_GPU_REPO": gpu.get("repo", ""),
        "PF_GPU_REF": gpu.get("ref", ""),
        "PF_GPU_SHA": sha(gpu.get("repo")),
        "PF_GPU_MODULES": " ".join(gpu.get("modules", []) or []),
        "PF_LIBSDL3_SHA": sha("libsdl3-sunxifb"),
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
        "PF_UBOOT_SHA": sha(uboot_repo),
    }
    # Repos this device genuinely needs a SHA for (repo named, not the "none" sentinel).
    needed = [("PF_KERNEL_SHA", k.get("repo")), ("PF_IMAGE_SHA", "image"),
              ("PF_BLOBS_SHA", "blobs"), ("PF_VENDOR_MANIFEST_SHA", "vendor-manifest")]
    if (gpu.get("repo") or "none") != "none":
        needed.append(("PF_GPU_SHA", gpu.get("repo")))
    if uboot_repo:
        needed.append(("PF_UBOOT_SHA", uboot_repo))
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
        merged, _ = resolve(argv[1])
        print(json.dumps(merged, indent=2, sort_keys=True))
        return 0
    if cmd == "env":
        if len(argv) < 2:
            sys.stderr.write("env: give a device id\n"); return 2
        print("\n".join(env_lines(argv[1])))
        return 0
    if cmd == "buildargs":
        if len(argv) < 2:
            sys.stderr.write("buildargs: give a device id\n"); return 2
        args, state, missing = build_args(argv[1])
        for kk in sorted(args):
            print(f"{kk}={args[kk]}")
        print(f"PF_LOCK_STATE={state}")
        print(f"PF_LOCK_MISSING_SHAS={','.join(missing)}")
        return 0
    sys.stderr.write(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
