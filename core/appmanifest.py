#!/usr/bin/env python3
"""core/appmanifest.py — the E8-side STATIC app.toml validator (tsp-ziac.1).

Validates an `app.toml` `[runtime]` platform pin against the frozen per-family ABI view
(`abi/platform-abi.json` / `abi/families.toml`) — the checks that structurally need
`platform.lock`, which the ON-DEVICE broker does NOT have. Run at PACKAGE/SIGN time.

WHY TWO VALIDATORS (one descriptor, two consumers — rationale recorded in the bead + docs):
  • THIS validator (platform, static, package-time) owns what needs the lock/registry:
      - `[runtime].family`   ∈ the family registry (canonical id OR accepted alias)  -> UnknownFamily
      - `[runtime].platform-version` is offered for that family in the view            -> OutOfLockVersion
      - `[runtime].abi`      is a supported contract version                           -> UnsupportedAbi
      - `[app].use` tokens are WELL-FORMED (parse, no dup, sane modifier)              -> Malformed/Duplicate/BadModifier
  • The runtime broker (`runtime/crates/pf-broker/src/manifest.rs`, cooperative, on-device,
    launch-time) owns the AUTHORITATIVE capability semantics it alone can see: the KNOWN_CAPS
    universe + the descriptor-backed DANGLING check (a REQUIRED hardware cap the device's
    descriptor cannot back) + family-MATCH against the running Platform. This validator does
    NOT re-implement that capability universe (it would rot across the language boundary) — it
    checks token STRUCTURE and defers capability SEMANTICS to the broker.
  Net: unknown-family + out-of-lock-version are rejected HERE (impossible on-device); dangling-use
  is rejected by manifest.rs (impossible off-device without the descriptor+cap universe). Together
  they cover the bead's "unknown family / dangling use / out-of-lock version" acceptance.

Usage:
  appmanifest.py validate <app.toml>     # exit 0 = valid; 1 = violations (printed); 2 = usage/IO
  appmanifest.py schema                   # print the path to the JSON Schema (abi/app.schema.json)
"""
import sys, os, json, re

try:
    import tomllib  # py3.11+
    def _load_toml_bytes(b):
        return tomllib.loads(b) if isinstance(b, str) else tomllib.load(b)
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
        def _load_toml_bytes(b):
            return tomllib.loads(b) if isinstance(b, str) else tomllib.load(b)
    except ModuleNotFoundError:
        sys.stderr.write("FATAL: need Python 3.11+ (tomllib) or the 'tomli' package.\n")
        sys.exit(3)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import abi_view  # noqa: E402  (core/abi_view.py — the family view)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "abi", "app.schema.json")

# Supported frozen contract versions (STABILITY.md: v1 is frozen; a v2 would coexist).
SUPPORTED_ABI = {"1"}

# Capability modifiers this validator recognises structurally (mirrors manifest.rs modifier_ok;
# the AUTHORITATIVE list is runtime-side — kept minimal + documented here to avoid divergence).
_MODIFIER_OK = {
    "location": {"approximate", "precise"},
    "gnss": {"approximate", "precise"},
    # egress:<host> — any non-empty host token is a valid modifier.
}


def _parse_use_token(token):
    """Parse `<cap>[:<modifier>][?]` -> (cap, modifier|None, optional, raw). Mirrors
    manifest.rs UseEntry::parse so a token this validator accepts parses identically on-device."""
    raw = token
    t = token.strip()
    optional = t.endswith("?")
    if optional:
        t = t[:-1]
    if ":" in t:
        cap, modifier = t.split(":", 1)
        cap, modifier = cap.strip().lower(), modifier.strip()
    else:
        cap, modifier = t.strip().lower(), None
    return cap, modifier, optional, raw


def validate_toml_text(text):
    """Return a list of human-readable violation strings ([] = valid)."""
    violations = []
    try:
        doc = _load_toml_bytes(text)
    except Exception as e:  # TOMLDecodeError et al.
        return [f"malformed TOML: {e}"]

    # ---- [runtime] platform pin (the checks that need the lock/registry) ----
    rt = doc.get("runtime")
    if not isinstance(rt, dict):
        violations.append("missing required [runtime] table (family + abi pin)")
        rt = {}

    view = abi_view.derive_view()
    fam_id = rt.get("family")
    fam = None
    if fam_id is None:
        if rt:
            violations.append("[runtime].family is required")
    else:
        fam = abi_view.find_family(view, str(fam_id))
        if fam is None:
            known = ", ".join(f["id"] for f in view["families"])
            violations.append(f"UnknownFamily: '{fam_id}' is not a known platform family (known: {known})")

    abi = rt.get("abi")
    if abi is None:
        if rt:
            violations.append("[runtime].abi is required")
    elif str(abi) not in SUPPORTED_ABI:
        violations.append(f"UnsupportedAbi: abi '{abi}' is not offered (supported: {', '.join(sorted(SUPPORTED_ABI))})")

    pv = rt.get("platform-version")
    if pv is not None and fam is not None:
        if str(pv) != str(fam.get("platform_version")):
            violations.append(
                f"OutOfLockVersion: platform-version '{pv}' is not offered for family "
                f"'{fam['id']}' (this family offers '{fam.get('platform_version')}' in the "
                f"frozen view abi/platform-abi.json)")

    # ---- [app] identity + use=[] token well-formedness (structure only) ----
    app = doc.get("app")
    if not isinstance(app, dict):
        violations.append("missing required [app] table")
        app = {}
    if not app.get("id"):
        violations.append("[app].id is required")

    uses = app.get("use", [])
    if uses and not isinstance(uses, list):
        violations.append("[app].use must be an array of strings")
        uses = []
    seen = set()
    for token in uses:
        if not isinstance(token, str):
            violations.append(f"malformed use entry (not a string): {token!r}")
            continue
        cap, modifier, _optional, raw = _parse_use_token(token)
        if not cap:
            violations.append(f"Malformed use entry '{raw}' (empty capability)")
            continue
        if cap in seen:
            violations.append(f"DuplicateCapability '{cap}'")
            continue
        seen.add(cap)
        if modifier is not None:
            if cap == "egress":
                if not modifier.strip():
                    violations.append(f"BadModifier: egress requires a host ('{raw}')")
            elif cap in _MODIFIER_OK:
                if modifier not in _MODIFIER_OK[cap]:
                    violations.append(f"BadModifier: capability '{cap}' rejects modifier '{modifier}'")
            else:
                violations.append(f"BadModifier: capability '{cap}' takes no modifier ('{raw}')")
        # NB: unknown-capability + descriptor-backed dangling-required are the runtime broker's
        # authoritative checks (manifest.rs) — deliberately NOT re-implemented here.

    return violations


def main(argv):
    if not argv:
        sys.stderr.write(__doc__); return 2
    cmd = argv[0]
    if cmd == "schema":
        print(SCHEMA)
        return 0
    if cmd == "validate":
        if len(argv) < 2:
            sys.stderr.write("validate: give an app.toml path\n"); return 2
        path = argv[1]
        try:
            with open(path, "r") as fh:
                text = fh.read()
        except OSError as e:
            sys.stderr.write(f"cannot read {path}: {e}\n"); return 2
        violations = validate_toml_text(text)
        if not violations:
            print(f"OK    {path}: app descriptor valid ([runtime] pin resolves; use=[] well-formed)")
            return 0
        for v in violations:
            print(f"ERROR {v}")
        return 1
    sys.stderr.write(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
