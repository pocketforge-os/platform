# GE8300 closed-UM HWRT build and capture

This is the coordinator recipe for `tsp-mc9m.41.598`. It uses
`test-node-farm` commit `2b920973d24afce530e7c3f897a0a7ceb630ba55`
(`tsp-mc9m.41.597`) and the platform commit produced from this branch. That
platform commit pins the `[[repos]] name = "gpu-km-tsp"` **`sha` field** to
`c1ec369a23ee68aa5e170afa689e7ac13316024d`; `ref = "main"` is descriptive and
unchanged. Replace `PLATFORM_LOCK_COMMIT` below with the full commit printed by
the commit/push harness for branch `tsp-mc9m.41.598`. The build script rejects
a branch name, so the value must be that immutable 40-hex commit, not the branch.

These commands deliberately stop short of running themselves here. The build
belongs on modelmaker and the capture belongs behind pf-redfish.

## 1. Prepare the exact sources on modelmaker

```bash
ssh mm@10.0.40.90
set -euo pipefail

PLATFORM_LOCK_COMMIT=<full-40-hex-platform-commit-from-tsp-mc9m.41.598>
TNF_COMMIT=2b920973d24afce530e7c3f897a0a7ceb630ba55
PLATFORM_REPO="$HOME/platform"
IMAGE_REPO="$HOME/image"
TNF_REPO="$HOME/test-node-farm-tsp-mc9m.41.597"
ROOTFS_STAGING="$HOME/recovery/odyssey-rootfs-tsp-mc9m.41.598"
BUNDLE="$HOME/recovery/staging/closed-hwrt-640x480"
FULL_IMAGE_OUT="$HOME/pf-artifacts/tsp-mc9m.41.598-closed-hwrt"

test "$(git -C "$PLATFORM_REPO" rev-parse "$PLATFORM_LOCK_COMMIT^{commit}")" = "$PLATFORM_LOCK_COMMIT"
git -C "$PLATFORM_REPO" show "$PLATFORM_LOCK_COMMIT:platform.lock" |
  awk '/^name = "gpu-km-tsp"/{f=1} f&&/^sha/{print; exit}' |
  grep -F 'c1ec369a23ee68aa5e170afa689e7ac13316024d'

if test ! -d "$TNF_REPO/.git"; then
  git clone https://github.com/pocketforge-os/test-node-farm.git "$TNF_REPO"
fi
git -C "$TNF_REPO" fetch origin tsp-mc9m.41.597
git -C "$TNF_REPO" checkout --detach "$TNF_COMMIT"
test "$(git -C "$TNF_REPO" rev-parse HEAD)" = "$TNF_COMMIT"
test -x "$PLATFORM_REPO/pf"
test -f "$IMAGE_REPO/build/Dockerfile.pf"
mkdir -p "$ROOTFS_STAGING" "$BUNDLE" "$FULL_IMAGE_OUT"
```

`build-odyssey-rootfs.sh` checks out `PLATFORM_LOCK_COMMIT` itself, exports
`PF_ODYSSEY_CAPTURE=1`, and runs the real hermetic `pf build`. It also compiles
and stages `/opt/pocketforge/bin/pf-closed-hwrt-640x480` before publishing the
canonical rootfs tar.

## 2. Build the pinned rootfs and select the 640x480 init

```bash
cd "$TNF_REPO/spike/odyssey"
./build-odyssey-rootfs.sh \
  --image-repo "$PLATFORM_REPO" \
  --pf-image-repo "$IMAGE_REPO" \
  --platform-lock-ref "$PLATFORM_LOCK_COMMIT" \
  --staging-root "$ROOTFS_STAGING"

ROOTFS_SHA=$(awk -F= '$1=="rootfs_sha256"{print $2}' odyssey-rootfs.pin)
test "$ROOTFS_SHA" = "$(printf %s "$ROOTFS_SHA" | grep -Eo '^[0-9a-f]{64}$')"
ROOTFS_TAR="$ROOTFS_STAGING/$ROOTFS_SHA/odyssey-rootfs@sha256:$ROOTFS_SHA.tar"
test "$(sha256sum "$ROOTFS_TAR" | awk '{print $1}')" = "$ROOTFS_SHA"
test -x "$ROOTFS_STAGING/$ROOTFS_SHA/rootfs/opt/pocketforge/bin/pf-closed-hwrt-640x480"
test -f "$ROOTFS_STAGING/$ROOTFS_SHA/rootfs/lib/modules/4.9.191/pvrsrvkm.ko"

# Obtain the script-pinned static AArch64 BusyBox on the build host.
BUSYBOX_WORK=$(mktemp -d)
curl --fail --location --output "$BUSYBOX_WORK/busybox-static.deb" \
  https://deb.debian.org/debian/pool/main/b/busybox/busybox-static_1.38.0-3_arm64.deb
echo '632371234bdd7cb12a8e6d60d38e922e6cf6a1d72df15ea17220a18f929dc1c5  '"$BUSYBOX_WORK/busybox-static.deb" | sha256sum -c -
dpkg-deb -x "$BUSYBOX_WORK/busybox-static.deb" "$BUSYBOX_WORK/root"
BUSYBOX="$BUSYBOX_WORK/root/usr/bin/busybox"
echo '1ea2dcadfeac37b6413a167288dadebc51988749d80bc838622097e5850eb724  '"$BUSYBOX" | sha256sum -c -

./assemble-closed-capture-initramfs.sh \
  --rootfs-artifact "capture-rootfs-a133@sha256:$ROOTFS_SHA" \
  --rootfs-tar "$ROOTFS_TAR" \
  --busybox "$BUSYBOX" \
  --init "$TNF_REPO/spike/odyssey/closed-capture-init-hwrt-640x480" \
  --out "$BUNDLE/initramfs.cpio.gz"
```

The `--init` argument is the only variant-selection mechanism. The assembler
installs that file as archive `/init`. Its first pass sets
`PF_CLOSED_HWRT_RENDER_COMMAND` and delegates to `/closed-capture-init`; the
second pass runs `/opt/pocketforge/bin/pf-closed-hwrt-640x480`. There is no
apphint, symlink, boot environment, or `OdysseyCapture` body parameter that
selects this variant.

## 3. Add the known-good boot bytes and assemble the preserved full image

The known-good Odyssey boot-byte pin records:

```text
Image  sha256=9a4c609b77b6cba35cf454cba6d1d697ca6e3449f8948800c89ec3c67c3edeb7
DTB    sha256=39e9504734166244dbf0f810fcc17b871936662dfba56792b827da9922a2eeed
```

Set these three paths to existing modelmaker artifacts; the prerequisites note
below explains why their origin cannot be filled in by this repository.

```bash
KNOWN_GOOD_IMAGE=/path/to/sha256-9a4c609b77b6cba35cf454cba6d1d697ca6e3449f8948800c89ec3c67c3edeb7/Image
KNOWN_GOOD_DTB=/path/to/sha256-39e9504734166244dbf0f810fcc17b871936662dfba56792b827da9922a2eeed/odyssey.dtb
KNOWN_GOOD_BASE_IMAGE=/path/to/known-good-a133-full-card.img.xz

echo '9a4c609b77b6cba35cf454cba6d1d697ca6e3449f8948800c89ec3c67c3edeb7  '"$KNOWN_GOOD_IMAGE" | sha256sum -c -
echo '39e9504734166244dbf0f810fcc17b871936662dfba56792b827da9922a2eeed  '"$KNOWN_GOOD_DTB" | sha256sum -c -
install -m 0644 "$KNOWN_GOOD_IMAGE" "$BUNDLE/Image"
install -m 0644 "$KNOWN_GOOD_DTB" "$BUNDLE/odyssey.dtb"

sha256sum "$BUNDLE/Image" "$BUNDLE/odyssey.dtb" \
  "$BUNDLE/initramfs.cpio.gz" "$ROOTFS_TAR" \
  "$ROOTFS_STAGING/$ROOTFS_SHA/rootfs/lib/modules/4.9.191/pvrsrvkm.ko" |
  tee "$BUNDLE/SHA256SUMS"

./assemble-sd-ramfs-image.sh \
  --u-boot-source "$HOME/u-boot-tsp-a133" \
  --u-boot-ref 1c8cce64a68a \
  --base-image "$KNOWN_GOOD_BASE_IMAGE" \
  --bundle "$BUNDLE" \
  --dtb "$BUNDLE/odyssey.dtb" \
  --preserve-initramfs \
  --out-dir "$FULL_IMAGE_OUT"

# The assembler already emits <image>.sha256 and <image>.provenance. Select its sole output:
mapfile -t FULL_IMAGES < <(find "$FULL_IMAGE_OUT" -maxdepth 1 -type f -name 'odyssey-sd-*.img.xz' -print)
test "${#FULL_IMAGES[@]}" -eq 1
FULL_IMAGE=${FULL_IMAGES[0]}
sha256sum -c "$FULL_IMAGE.sha256"
grep -Fx 'initramfs_mode=preserve' "$FULL_IMAGE.provenance"
INITRAMFS_SHA=$(sha256sum "$BUNDLE/initramfs.cpio.gz" | awk '{print $1}')
grep -Fx "initramfs_input_sha256=$INITRAMFS_SHA" "$FULL_IMAGE.provenance"
grep -Fx "initramfs_output_sha256=$INITRAMFS_SHA" "$FULL_IMAGE.provenance"
```

## 4. Stage the bundle and run `OdysseyCapture` from tsp-base

Run this section on the coordinator host, where `pf-secret` and the lease client
are installed. Copy the three bundle components from modelmaker without changing
their bytes, then stage them through pf-redfish. The full image from step 3 is a
separately verified transport artifact; `OdysseyCapture` consumes the staged
Image/DTB/initramfs triplet.

```bash
set -euo pipefail
NODE=http://pf-node-01.lan:8095
SYSTEM="$NODE/redfish/v1/Systems/tsp-base"
ME=tsp-mc9m.41.598
TOK=$(pf-secret get lab/pf-redfish-node-01)
LOCAL_BUNDLE="$PWD/tsp-mc9m.41.598-closed-hwrt-640x480"
mkdir -p "$LOCAL_BUNDLE"
scp mm@10.0.40.90:/home/mm/recovery/staging/closed-hwrt-640x480/Image "$LOCAL_BUNDLE/Image"
scp mm@10.0.40.90:/home/mm/recovery/staging/closed-hwrt-640x480/odyssey.dtb "$LOCAL_BUNDLE/odyssey.dtb"
scp mm@10.0.40.90:/home/mm/recovery/staging/closed-hwrt-640x480/initramfs.cpio.gz "$LOCAL_BUNDLE/initramfs.cpio.gz"
IMAGE="$LOCAL_BUNDLE/Image"
DTB="$LOCAL_BUNDLE/odyssey.dtb"
INITRD="$LOCAL_BUNDLE/initramfs.cpio.gz"

IMAGE_SHA=$(sha256sum "$IMAGE" | awk '{print $1}')
DTB_SHA=$(sha256sum "$DTB" | awk '{print $1}')
INITRD_SHA=$(sha256sum "$INITRD" | awk '{print $1}')
test "$IMAGE_SHA" = 9a4c609b77b6cba35cf454cba6d1d697ca6e3449f8948800c89ec3c67c3edeb7
test "$DTB_SHA" = 39e9504734166244dbf0f810fcc17b871936662dfba56792b827da9922a2eeed
BUNDLE_DIGEST=$(printf '%s\n' "$IMAGE_SHA" "$DTB_SHA" "$INITRD_SHA" | sha256sum | awk '{print $1}')

PF_BEAD="$ME" /home/matt/pocketforge-automation/scripts/pf-device.sh acquire tsp

stage() {
  artifact=$1 path=$2 sha=$(sha256sum "$2" | awk '{print $1}')
  curl --fail-with-body -sS -X POST \
    -H "Authorization: Bearer $TOK" \
    -H "X-PocketForge-Agent: $ME" \
    -H 'Content-Type: application/octet-stream' \
    -H "X-PocketForge-SHA256: $sha" \
    -H "X-PocketForge-Bundle-SHA256: $BUNDLE_DIGEST" \
    -H "X-PocketForge-Artifact-Name: $artifact" \
    --data-binary "@$path" \
    "$SYSTEM/Actions/Oem/PocketForge.StageImage"
}
stage Image "$IMAGE"
stage dtb "$DTB"
stage initramfs.cpio.gz "$INITRD"

curl --fail-with-body -sS "$SYSTEM/Oem/PocketForge/StagedBundles" |
  jq -e --arg digest "$BUNDLE_DIGEST" '.Bundles[] | select(.Digest == $digest and .Ready == true)'

HEADERS=$(mktemp)
BODY=$(mktemp)
curl --fail-with-body -sS -D "$HEADERS" -o "$BODY" -X POST \
  -H "Authorization: Bearer $TOK" \
  -H "X-PocketForge-Agent: $ME" \
  -H 'Content-Type: application/json' \
  --data "$(jq -cn --arg root "/home/matt/recovery/staging/$BUNDLE_DIGEST" \
    '{Image:($root+"/Image"),Dtb:($root+"/dtb"),Initramfs:($root+"/initramfs.cpio.gz")}')" \
  "$SYSTEM/Actions/Oem/PocketForge.OdysseyCapture"
TASK_PATH=$(awk 'BEGIN{IGNORECASE=1} /^Location:/ {gsub("\\r", "", $2); print $2}' "$HEADERS")
test -n "$TASK_PATH"

while :; do
  curl --fail-with-body -sS -H "Authorization: Bearer $TOK" "$NODE$TASK_PATH" > "$BODY"
  STATE=$(jq -r '.TaskState' "$BODY")
  case "$STATE" in
    Running|Starting|Pending|New) sleep 5 ;;
    Completed) break ;;
    Exception|Killed|Cancelled|Suspended) jq . "$BODY"; exit 1 ;;
    *) echo "unexpected TaskState=$STATE" >&2; jq . "$BODY"; exit 1 ;;
  esac
done
jq -e '.TaskState == "Completed" and .TaskStatus == "OK"' "$BODY"
jq '{TaskState,TaskStatus,Messages,Oem}' "$BODY" | tee tsp-mc9m.41.598-task.json
jq -r '.Oem.PocketForge.SerialTail // .Oem.PocketForge.Result // empty' "$BODY" \
  >tsp-mc9m.41.598-fresh-serial-or-dmesg.txt
test -s tsp-mc9m.41.598-fresh-serial-or-dmesg.txt
```

Release the held place after evidence collection, including on a failed task:

```bash
PF_BEAD="$ME" /home/matt/pocketforge-automation/scripts/pf-device.sh release tsp
```

## 5. Extract the fresh marker and compare with r528

Use the `SerialTail`/`Result` evidence retained by this Task only, extracted in
step 4; do not grep the unbounded persistent ring. Then run:

```bash
grep -a '^.*PF-VENDOR-HWRT ' tsp-mc9m.41.598-fresh-serial-or-dmesg.txt |
  tee tsp-mc9m.41.598-vendor-hwrt.txt
test -s tsp-mc9m.41.598-vendor-hwrt.txt
test "$(cut -d' ' -f2- tsp-mc9m.41.598-vendor-hwrt.txt | sort -u | wc -l)" -eq 1

cat >tsp-mc9m.41.598-r528.expected <<'EOF'
screen_pmax=0x01df027f te_screen=0x0001d027 te_mtile1=0x00a00000 te_mtile2=0x00780000 mtile_stride=1200 rgnhdr=6016 isp_mtile=0x0028001e
EOF
sed -E 's/^.*PF-VENDOR-HWRT //' tsp-mc9m.41.598-vendor-hwrt.txt | sort -u >tsp-mc9m.41.598-r528.actual
diff -u tsp-mc9m.41.598-r528.expected tsp-mc9m.41.598-r528.actual
```

## Missing prerequisites

The commands expose, rather than guess, three external inputs:

1. The platform commit SHA cannot be written into the commit that creates it.
   Use the full SHA printed by the branch commit/push harness and verify its
   `platform.lock` as step 1 does.
2. `odyssey-boot-bundle.pin` says the known-good Image and DTB are dd-carved,
   node-local ground-truth artifacts. Their SHA-256 values are pinned above,
   but the repository supplies neither reproducible source nor a download URL.
   They must already exist on modelmaker (or be copied there byte-exactly).
3. `assemble-sd-ramfs-image.sh` requires an explicit known-good A133 base image;
   the historical default was deleted. Set `KNOWN_GOOD_BASE_IMAGE` to a locally
   retained artifact and record its SHA-256. This is an unresolved artifact
   availability prerequisite, not an owner/product decision.

The coordinator must retain the Task JSON and its extracted fresh
`Oem.PocketForge.SerialTail`/`Result` evidence; never substitute a whole-ring
grep.
