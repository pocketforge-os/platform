# Device profile schema (`devices/<id>/profile.toml`)

Declarative **data**, not code. The validator + merge live in `core/profile.py`
(`pf validate <id>`, `pf resolve <id>`). Merge order (Armbian "board sourced first,
family fills unset"): **core defaults < `families/<family>/family.toml` < this profile**.
The schema is **family-extensible**: a family's plugin reads whatever keys it understands
under `[bootchain]`/`[flash]`; keys another family uses are simply absent (the
postmarketOS `flash_method`-scoped-keys discipline applied to the whole profile).

| table | key | required | notes |
|---|---|---|---|
| `[device]` | `id` | ✅ | canonical id; names artifacts, build dirs, blob groups |
| | `family` | ✅ | selects `families/<family>/` (the plugin) |
| | `arch` | ✅ | `aarch64` |
| | `soc`, `name`, `soc_friendly` | | descriptive |
| | `status` | | `example` ⇒ validator treats absent repos as INFO (paper proof) |
| `[kernel]` | `repo`, `ref` | ✅ | repo name (in `platform.lock`) + branch/tag (`.lock` → SHA) |
| | `defconfig`, `dtb`, `dts_source` | | `dts_source` = `owned`\|`vendor-rebuilt` |
| `[gpu]` | `repo` | | repo name, or `"none"` (Adreno = in-tree msm + Mesa) |
| | `ref`, `modules` | | `modules` is a list (`.ko` names) |
| | `kernel_driver`, `microcode_blob_group` | | (in-tree-driver families) |
| `[bootchain]` | `model`, `boot_proto` | | family-shaped; `boot_proto` may come from family default |
| | **either** `uboot.repo`/`tfa.repo`(+refs) **or** `blob_group` | ✅ (one of) | source-built vs vendor blob — the duality |
| | `spl_offset_kib`, `*.defconfig`, `tfa.plat` | | source-built sunxi |
| `[image]` | `image_name` | ✅ | artifact base name |
| | `partition_table`, `assembler`, `boot_fs`/`boot_label`, `root_fs`/`root_label` | | `partition_table` may come from family default |
| | `fs_uuids_file` | | repro anchors (USERDATA_FS_UUID / HASH_SEED / DISK_UUID) |
| `[console]` | `dev`, `baud`, `earlycon`, `cmdline_extra` | | serial/boot |
| `[blobs]` | `groups` | | list of vendor-manifest group names (never a CID) |
| `[container]` | `build_image` | ✅ | the OWNED build container (`@sha256:` seeded in tsp-1dl.1.1) |
| | `app_base` | | apko/OCI app base (B5) |
| `[flash]` | `method` | ✅ (or family default) | `dd-sd`\|`fastboot`\|`edl-firehose`\|... |
| | `slot` | | sunxi: Dell two-LUN reader (`base`\|`pros`) |
| | `fastboot.*`, `edl.*` | | snapdragon-scoped (sunxi never reads them) |

**Reproducibility rule:** a profile `ref` of a *branch name* must never drive the build
directly — always resolve through `platform.lock` to a SHA. The `ref` is for humans +
`pf lock`; the byte-deterministic input is the `.lock` SHA.

See `devices/a523/profile.toml` (source-built bootchain), `devices/a133/profile.toml`
(blob-group bootchain), and `devices/sdm845/profile.toml` (a different family, same schema).
