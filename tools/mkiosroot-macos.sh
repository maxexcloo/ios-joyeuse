#!/bin/bash
# Build the iOS root image on macOS with only the tools macOS ships.
#
#   tools/mkiosroot-macos.sh OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.img [SIZE]
#
# The upstream tools/mkiosroot.sh assumes a Linux host with apfs-fuse, hfsprogs
# and root loop mounts. On macOS none of that is needed: the DMGs attach with
# hdiutil (native APFS) and the volume is made with newfs_hfs, both of which
# work as an ordinary user. The single privileged step is the copy itself, so
# that owners/modes match iOS (root, _logd 272, mobile 501); that is what the
# one sudo prompt is for.
#
# Produces a RAW HFS+ image, not a sparse one: `fastboot -S 512M flash
# userdata` sparsifies it during the transfer, so img2simg is not needed.
set -euo pipefail
[[ $# -ge 4 ]] || { sed -n '2,16p' "$0"; exit 2; }

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
	# array is an unbound-variable error under `set -u`. The EXIT trap runs
	# this at the end of a *successful* build too, which made every good run
	# exit 1 (logs/root-build-final.log ends that way, after the sha256).
	for d in ${rdev[@]+"${rdev[@]}"}; do
		hdiutil detach "$d" -quiet -force 2>/dev/null || true
	done
}
trap detach_all EXIT

# attach DMG read-only, print the mounted volume path
attach_ro() {
	local dmg=$1 dev line
	# -owners on: without it every file reads as 501/20 and rsync's
	# --numeric-ids faithfully copies that lie onto the image.
	line=$(hdiutil attach -readonly -noverify -noautoopen -nobrowse -owners on "$dmg" 2>/dev/null |
		awk 'NF > 2 && $NF ~ /^\/Volumes\// {print; exit}')
	dev=$(echo "$line" | awk '{print $1}')
	[[ -n $dev ]] || { echo "hdiutil could not attach $dmg" >&2; exit 1; }
	rdev+=("$dev")
	echo "$line" | awk '{print $NF}'
}

echo "== attaching the IPSW images (read-only, native APFS)"
osvol=$(attach_ro "$os")
sysvol=$(attach_ro "$sysos")
appvol=$(attach_ro "$appos")
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
# the password; this is the only privileged step and it validates once here.
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

echo "== linking cryptex extras at their root paths"
# dyld does not search the cryptexes at ignition level 1, so every cryptex file
# with no counterpart in the OS root gets a hard link at its normal location
# (libobjc-trampolines, libffi-trampolines, libstdc++, ...).
for c in OS App; do
	$SUDO bash -c '
		set -euo pipefail
		root=$1; name=$2
		cd "$root/private/preboot/Cryptexes/$name"
		find . ! -type d ! -path "./System/Library/Caches/com.apple.dyld/*" | while IFS= read -r f; do
			f=${f#./}
			[ -e "$root/$f" ] || [ -L "$root/$f" ] && continue
			mkdir -p "$root/$(dirname "$f")"
			src="$root/private/preboot/Cryptexes/$name/$f"
			if [ -L "$src" ]; then cp -P "$src" "$root/$f"; else ln "$src" "$root/$f"; fi
		done
	' _ "$mnt" "$c"
	echo "   $c"
done

# The ownership-sensitive surgery lives in root-finalize.sh: same code the
# resume path runs, so a part-built image finishes identically.
echo "== logd stores, keybag, bring-up tweaks"
$SUDO "$repo/tools/root-finalize.sh" "$mnt"

echo "== verifying ownership landed on disk"
$SUDO bash -euc '
	r=$1
	bad=0
	check() { # path want_uid label
		[ -e "$r/$1" ] || return 0
		got=$(stat -f %u "$r/$1")
		[ "$got" = "$2" ] || { echo "   MISMATCH $1: uid $got, want $2"; bad=1; }
	}
	check bin/ls 0 "system binary (root)"
	check private/var/keybags/systembag.kb 0 "keybag (root)"
	check private/var/db/diagnostics 272 "logd store (_logd)"
	check private/var/db/uuidtext 272 "logd uuidtext (_logd)"
	[ "$bad" = 0 ] && echo "   owners correct (root, _logd 272)"
	exit "$bad"
' _ "$mnt"

echo "== unmounting and checking the volume"
sync
diskutil unmount "$dev" >/dev/null
hdiutil detach "$dev" -quiet -force
rdev=()
# fsck_hfs cannot check a raw image FILE: it stats the path for a block device
# size, prints "Can't get device block size" and exits 8 without examining the
# volume, so `fsck_hfs ... $out` both repaired nothing and verified nothing
# (every build log shows that line and none ever printed "fsck: clean").
# Attach the image and verify the device node instead -- that is the check that
# actually reads the filesystem. -f -y is gone with it: repairing an image we
# just wrote, by an fsck that cannot read it, is not a repair.
chk=$(hdiutil attach -imagekey diskimage-class=CRawDiskImage -nomount "$out" 2>/dev/null |
	awk 'NF && $1 ~ /^\/dev\/disk/ {print $1; exit}')
if [ -n "$chk" ]; then
	if diskutil verifyVolume "$chk" >/tmp/ios-fsck.$$ 2>&1; then
		echo "   fsck: clean"
	else
		echo "   FSCK FAILED on $out:" >&2
		tail -5 /tmp/ios-fsck.$$ >&2
	fi
	rm -f /tmp/ios-fsck.$$
	hdiutil detach "$chk" -quiet -force 2>/dev/null || true
else
	echo "   ERROR: could not attach $out to verify it" >&2
	exit 1
fi

ls -lh "$out"
echo "built: $out"
shasum -a 256 "$out"
