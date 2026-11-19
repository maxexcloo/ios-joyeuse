#!/bin/bash
# Build the iOS root image on macOS with only the tools macOS ships.
#
#   tools/mkiosroot-macos.sh OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.img [SIZE]
#
# The DMGs attach with hdiutil (native APFS) and the volume is made with
# newfs_hfs as an ordinary user. The copy and finalisation use sudo so
# owners and modes match iOS (root, _logd 272, mobile 501).
set -euo pipefail
[[ $# -ge 4 ]] || { sed -n '2,9p' "$0"; exit 2; }

os=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
sysos=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
appos=$(cd "$(dirname "$3")" && pwd)/$(basename "$3")
outdir=$(dirname "$4"); mkdir -p "$outdir"
out=$(cd "$outdir" && pwd)/$(basename "$4")
size=${5:-16G}
[[ ! -e $out ]] || { echo "refusing to overwrite $out" >&2; exit 1; }

repo=$(cd "$(dirname "$0")/.." && pwd)
rdev=()
detach_all() {
	# ${rdev[@]+...}: macOS ships bash 3.2, where "${rdev[@]}" on an empty
	# array is an unbound-variable error under `set -u`.
	for d in ${rdev[@]+"${rdev[@]}"}; do
		hdiutil detach "$d" -quiet -force 2>/dev/null || true
	done
}
trap detach_all EXIT

# Attach a source image and retain its device for cleanup.
attach_ro() {
	local dmg=$1 dev line
	# -owners on: without it every file reads as 501/20 and rsync's
	# --numeric-ids faithfully copies that lie onto the image.
	line=$(hdiutil attach -readonly -noverify -noautoopen -nobrowse -owners on "$dmg" 2>/dev/null |
		awk 'NF > 2 && $NF ~ /^\/Volumes\// {print; exit}')
	dev=$(echo "$line" | awk '{print $1}')
	[[ -n $dev ]] || { echo "hdiutil could not attach $dmg" >&2; exit 1; }
	rdev+=("$dev")
	vol=$(echo "$line" | awk '{print $NF}')
}

echo "== attaching the IPSW images (read-only, native APFS)"
attach_ro "$os"; osvol=$vol
attach_ro "$sysos"; sysvol=$vol
attach_ro "$appos"; appvol=$vol
echo "   OS       $osvol"
echo "   SystemOS $sysvol"
echo "   AppOS    $appvol"

echo "== creating a ${size} raw image and formatting it"
# mkfile -n preallocates without writing the blocks: the file grows as data
# lands, so a 16 GiB volume costs only the ~11 GiB it holds.
rm -f "$out"
mkfile -n "$size" "$out"
dev=$(hdiutil attach -imagekey diskimage-class=CRawDiskImage -nomount "$out" 2>/dev/null |
	awk 'NF && $1 ~ /^\/dev\/disk/ {print $1; exit}')
[[ -n $dev ]] || { echo "could not attach $out" >&2; exit 1; }
rdev+=("$dev")
# -s case-sensitive (the iOS root has names differing only by case), -J journaled
newfs_hfs -s -J -v iOSRoot "$dev" >/dev/null
# diskutil prints the device, not the path, so ask the mount table instead.
# -mountOptions owners is mandatory: a noowners mount discards every chown
# (silently), leaving the whole tree owned by the building user.
diskutil mount -mountOptions owners "$dev" >/dev/null
mnt=""
for _ in $(seq 30); do
	mnt=$(mount | awk -v d="$dev" '$1 == d { sub(/^.* on /, ""); sub(/ \(.*$/, ""); print; exit }')
	[[ -n $mnt && -d $mnt ]] && break
	sleep 1
done
[[ -n $mnt && -d $mnt ]] || { echo "could not mount $dev" >&2; exit 1; }
echo "   $dev -> $mnt"

echo "== the next step copies ~11 GiB as root (one sudo prompt)"
# The build runs detached, so sudo has no terminal. A native dialog collects
# the password once here.
if ! sudo -n true 2>/dev/null; then
	export SUDO_ASKPASS="$repo/tools/askpass.sh"
	sudo -A -v || { echo "no sudo: cannot set owners as root" >&2; exit 1; }
	echo "   sudo validated"
fi
SUDO="sudo"
sudo -n true 2>/dev/null || SUDO="sudo -A"

copy() {  # srcdir dstdir
	echo "   $1 -> ${2#"$mnt"}"
	$SUDO mkdir -p "$2"
	# -aH: owners, modes, symlinks, hard links; --numeric-ids stops rsync
	# mapping the source uids through the local passwd database.
	$SUDO rsync -aH --numeric-ids "$1/" "$2/"
}
copy "$osvol" "$mnt"
copy "$sysvol" "$mnt/private/preboot/Cryptexes/OS"
copy "$appvol" "$mnt/private/preboot/Cryptexes/App"
$SUDO "$repo/tools/root-finalize.sh" "$mnt"

sync
diskutil unmount "$dev" >/dev/null
$SUDO diskutil verifyVolume "$dev"
hdiutil detach "$dev" -quiet -force
unset "rdev[$((${#rdev[@]} - 1))]"
ls -lh "$out"
shasum -a 256 "$out"
echo "built: $out"
