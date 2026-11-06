#!/bin/bash
# Finish an existing root image in place, without recopying the filesystem.
#
#   sudo tools/root-resume.sh OUT.img
#
# For the case where the ~11 GiB copy already completed and a later step
# failed. Attaches the raw image, runs tools/root-finalize.sh on it, unmounts
# and runs fsck_hfs. Nothing is written outside the image file.
set -euo pipefail
[[ $# -eq 1 ]] || { sed -n '2,9p' "$0"; exit 2; }
[[ $(id -u) -eq 0 ]] || { echo "run as root (sudo $0 ...)" >&2; exit 1; }
repo=$(cd "$(dirname "$0")/.." && pwd)
img=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
[[ -f $img ]] || { echo "no such image: $img" >&2; exit 1; }

dev=$(hdiutil attach -imagekey diskimage-class=CRawDiskImage -nomount "$img" 2>/dev/null |
	awk 'NF && $1 ~ /^\/dev\/disk/ {print $1; exit}')
[[ -n $dev ]] || { echo "could not attach $img" >&2; exit 1; }
detach() { hdiutil detach "$dev" -quiet -force 2>/dev/null || true; }
trap detach EXIT

# -mountOptions owners: a noowners mount discards chown silently.
diskutil mount -mountOptions owners "$dev" >/dev/null
mnt=""
for _ in $(seq 30); do
	mnt=$(mount | awk -v d="$dev" '$1 == d { sub(/^.* on /, ""); sub(/ \(.*$/, ""); print; exit }')
	[[ -n $mnt && -d $mnt ]] && break
	sleep 1
done
[[ -n $mnt && -d $mnt ]] || { echo "could not mount $dev" >&2; exit 1; }
echo "== $img at $mnt"

"$repo/tools/root-finalize.sh" "$mnt"

echo "== unmounting and checking the volume"
sync
diskutil unmount "$dev" >/dev/null
hdiutil detach "$dev" -quiet -force
trap - EXIT
fsck_hfs -f -y "$img" 2>&1 | tail -3 || true
fsck_hfs -n "$img" >/dev/null && echo "   fsck: clean"
ls -lh "$img"
shasum -a 256 "$img"
