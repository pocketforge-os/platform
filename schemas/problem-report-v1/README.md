# Problem report v1

The one record a PocketForge device may send about a crash, hang, out-of-memory kill, system
component failure or kernel oops (bead `tsp-ihne1.37`, plan key `cr-schema`, design
`mission-control/design/input-layer/problem-reports-design.md` §2). Zero personal data by
construction: every value comes from a closed vocabulary, our own build, the device descriptor
or a signed manifest. There is no field that can hold free text.

| File | What it is |
|---|---|
| `problem-report-v1.cddl` | The shape (RFC 8610). |
| this README | The rules CDDL cannot express; normative where they differ. |
| `problem_report.py` | Reference codec and validator, Python stdlib only. |
| `fixtures/valid/*.json` | `report` (JSON mapping) and `cbor_hex` (its exact wire bytes). |
| `fixtures/invalid/*.json` | `expected_reason` plus either `report` (generic value, `{"$bytes": hex}` for byte strings) or raw `cbor_hex`. Each breaks exactly one rule. |
| `test_contract.py` | Fixture and seeded property tests. |

The device and server share one validator, the runtime crate `pf-problem-report`. It reads
these fixtures from a platform checkout and must reach the same verdict, with the same reason,
as `problem_report.py`. Change both together.

## Wire format

- CBOR (RFC 8949), **at most 4096 bytes**. Larger input is refused before it is parsed.
- **Deterministic encoding** (RFC 8949 §4.2.1): definite lengths, shortest-form arguments, map
  keys sorted bytewise by their encoding (for text keys that is shorter first, then bytewise), no
  duplicate keys. The decoder refuses any other encoding, so the accepted bytes are the only
  bytes for that report. The queue, the "Exact data" view and the server all hash the same bytes.
- Only these items exist: unsigned integers, byte strings, UTF-8 text strings, arrays, maps with
  text keys, `false`, `true` and `null`. Negative integers, tags, floats, `undefined`, other
  simple values and indefinite lengths are refused. Nesting deeper than 8 is refused.
- Every map is closed. An unknown key is refused at both ends, at every level.

## Fields

| Field | crash | hang | oom | component | kernel | Value |
|---|---|---|---|---|---|---|
| `v` | R | R | R | R | R | `1` |
| `kind` | R | R | R | R | R | `crash` · `hang` · `oom` · `component` · `kernel` |
| `how` | R | R | R | R | R | per kind, below |
| `day` | R | R | R | R | R | `YYYY-MM-DD`, a real UTC calendar date, 2020 to 2099 |
| `build` | R | R | R | R | R | 12 lowercase hex: the `build=` value of `/etc/pocketforge-build-id` |
| `model` | R | R | R | R | R | device id, `[a-z0-9][a-z0-9-]{0,31}`. The server also checks it against `devices/catalog.toml`; the shared validator does not. |
| `app` | R | R | R | R (`origin` = `image`) | — | `{origin, id?, ver?}`, below |
| `uptime` | R | R | R | R | R | bucket |
| `session` | R | R | R | R | — | bucket |
| `mem` | R | R | R | R | — | `{pressure: bool, oom: bool}`: PSI pressure seen, cgroup OOM kill. `oom` kind requires `oom: true`. |
| `frames` | R | R | R | R | — | at most 48 frames, may be empty |
| `samples` | — | R | — | — | — | at most 2 counts, each 1 to 48, summing to the number of frames |
| `kframes` | — | — | — | — | R | at most 32 kernel call-trace frames, may be empty |
| `panic_at` | O | — | — | O | — | panic location, below |
| `del` | R | R | R | R | R | 32-byte SHA-256 of a random per-report deletion token |

R required, O optional, — forbidden (present is refused).

**`how`.** crash: `SIGSEGV` `SIGABRT` `SIGBUS` `SIGILL` `SIGFPE` `SIGTRAP` `SIGSYS` `SIGQUIT`
`SIGXCPU` `SIGXFSZ` (the core-dumping signals). hang: `no-reply-menu` (missed the system menu's
2 s ping, then force-closed), `stop-timeout`. oom: `oom-kill`. component: the crash signals,
`start-timeout`, `stop-timeout`, `no-reply-menu`. kernel: `oops`, `panic`, `watchdog`.

**Buckets.** `<1m`, `1-10m`, `10-60m`, `>1h`, with an ASCII hyphen.

**`app`.**
- `origin` is `image` (part of the OS image), `catalog` (installed from the signed catalog) or
  `sideloaded`.
- `catalog` requires `id` and `ver`. `image` requires `id`; `ver` is optional.
- `sideloaded` carries **no `id` and no `ver`**: both come from an unsigned manifest and could be
  anything the user typed.
- `id` follows pf-app-manifest `validate_app_id`: 3 to 200 ASCII bytes, two or more dot-separated
  labels, each label `[a-z0-9]`, or `[a-z0-9][a-z0-9_-]*[a-z0-9]`.
- `ver` is up to four dot-separated decimal numbers without leading zeros, each at most 9 digits,
  at most 32 bytes. A manifest version that does not fit is a collector error, not a free-text
  field.
- System components report as `kind=component` with `origin=image`.

**Frames.** A frame is `[build-id, offset]`: the module's GNU build-id note (8 to 32 bytes, a
byte string) and the PC offset into that module (below 2^48). A frame whose module is not in the
image's build-id manifest or a catalog app's signed manifest is the typed **unknown frame
`[null, null]`**: no module and no offset, so a sideloaded library cannot fingerprint anyone.
The string `?` is only how the UI renders an unknown frame; on the wire it is refused. A hang
report holds the main thread's frames from up to two samples, one after the other; `samples`
gives each sample's frame count. When the sampler runs out of time, `frames` and `samples` are
both empty.

**Kernel frames.** `[sym, off, size, module]` is the parsed form of a call-trace line matching
`^\s*\w+\+0x[0-9a-f]+/0x[0-9a-f]+( \[\w+\])?$`: symbol (`[A-Za-z0-9_]{1,48}`), offset and size
(below 2^32), and the module name (`[A-Za-z0-9_]{1,24}`) or `null` for built-in code. The bound
is 32 so a full trace still fits in 4096 bytes.

**`panic_at`.** A Rust panic `Location` from a platform crate, at most 128 bytes, matching
`crates/[A-Za-z0-9_/.-]+\.rs:[0-9]+:[0-9]+`. Allowed only when `app.origin` is `image` and `how`
is `SIGABRT` (runtime crates build with `panic = "abort"`). The panic *message* is never sent.

## Never collected

Memory, register values, panic messages, paths, command lines, the environment, open files,
hostname, network data (SSIDs, addresses), serial numbers, MACs, device or install IDs, the exact
time, locale, other apps, input and free text. None of these has a field, and unknown fields are
refused.

## JSON mapping

The "Exact data" view and the fixtures use JSON: the same keys, byte strings as lowercase hex
text, `null` for the unknown frame. The mapping is exact both ways, and `encode` refuses a JSON
report whose bytes do not decode back to the same JSON.

## Refusal reasons

Both implementations refuse with one of these names. When an input breaks several rules, the
reason is the first one hit in this order:

1. `too-large`: more than 4096 bytes.
2. While parsing, in byte order: `malformed` (truncated, trailing bytes, reserved additional-info
   values 28 to 30, an indefinite-length unsigned integer, invalid UTF-8), `unsupported` (an item
   outside the list above, a non-text map key, nesting deeper than 8) or `non-canonical` (an
   argument not in shortest form, map keys out of order or repeated). A simple or float item is
   classified by its first byte, before its payload is read.
3. `type`: the top level is not a map.
4. `unknown-field`: a top-level key not in the field table.
5. `v`: `missing-field`, `type`, then `version` if it is not 1.
6. `kind`: `missing-field`, `type`, then `vocabulary`.
7. Presence, field by field in canonical key order: `missing-field` for a required field,
   `forbidden-field` for a forbidden one.
8. Each present field, in canonical key order (`v app day del how mem kind build model frames
   uptime kframes samples session panic_at`): `type`, `unknown-field` or `missing-field` inside
   `app` and `mem`, `vocabulary`, `grammar` (text or byte-string format) and `range` (numbers and
   list lengths).
9. `inconsistent`: a component not from the image, an `oom` report without `mem.oom`, hang
   `samples` that do not add up to the frames, `panic_at` without `origin=image` and `SIGABRT`.
