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
| | `required_modules` | | list of canonical module names (without `.ko`); required for open profiles and must be non-empty, duplicate-free, and include `powervr` |
| `[gpu]` | `repo` | | repo name, or `"none"` (Adreno = in-tree msm + Mesa) |
| `[gpu]` | `model` | | `ddk` (default for legacy profiles), `open`, or `none` (intentional GPU-less bring-up) |
| `[gpu]` | `km_model` | open | `in-tree-6.x` or `in-tree-7.x`, selecting the open PowerVR kernel-module model for that kernel line |
| `[gpu]` | `km_repo`, `km_ref` | open | kernel-module source identity (lock pinned) |
| `[gpu]` | `um_repo`, `um_ref` | open | open userspace source identity (lock pinned) |
| | `ref`, `modules` | | `modules` is a list (`.ko` names) |
| | GPU source/ref/module fields | `none` | must all be empty; consumers must skip GPU KM, UM, firmware, and initramfs module work |
| | `kernel_driver`, `microcode_blob_group` | | (in-tree-driver families) |
| `[display]` | `pipeline` | ✅ | userspace display path: `fbdev`, `drm`, or `none`; independent of `[gpu].model`, exported as `PF_DISPLAY_PIPELINE` |
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

For an open profile, `[kernel].required_modules` is a list of canonical names matching
`[A-Za-z0-9][A-Za-z0-9_-]*`; entries such as `powervr.ko` are invalid. The established
Linux 6.x `a133-open` profile declares `["powervr", "videobuf2-dma-contig", "sun6i-csi", "xradio"]`,
while the Linux 7.x `a133-open-7x-gpu` profile declares `["powervr"]` only.
Both profiles keep `[gpu].modules = ["powervr.ko"]` for the GPU artifact filename.

**Reproducibility rule:** a profile `ref` of a *branch name* must never drive the build
directly — always resolve through `platform.lock` to a SHA. The `ref` is for humans +
`pf lock`; the byte-deterministic input is the `.lock` SHA.

See `devices/a523/profile.toml` (source-built bootchain), `devices/a133/profile.toml`
(blob-group bootchain), and `devices/sdm845/profile.toml` (a different family, same schema).
