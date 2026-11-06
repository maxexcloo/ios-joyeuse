#!/bin/bash
# Fast root-image iteration: clone the built image, change it, unmount, done.
#
#   tools/root-variant.sh clone NAME              apfs/hfs clone of the base
#   tools/root-variant.sh shell NAME              mount it and give a root shell
#   tools/root-variant.sh tweak NAME SCRIPT...    run tweak scripts against it
#   tools/root-variant.sh list                    what variants exist
#   tools/root-variant.sh rm NAME
#
# Why: building the root from the IPSW takes ~15 minutes (11 GiB copy). Once
# built, a variant is a copy-on-write clone (`cp -c` clonefile, instant, no
# extra space until something changes) plus whatever you want to edit. Editing
# a file in the iOS root is the fastest experiment loop for userland problems
# (a plist, a daemon, a binary patch) — no kernel build, no reflash of 11 GiB
# if you flash only the changed image.
#
# Variants live in out/variants/NAME.img and are RAW HFS+ images, flashable
# exactly like out/ios16-root-miatoll.img.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
baseimg=$repo/../out/ios16-root-miatoll.img
vdir=$repo/../out/variants
cmd=${1:-}; name=${2:-}

need_name() { [[ -n $name ]] || { echo "give a variant name" >&2; exit 2; }; }

case $cmd in
clone)
	need_name; mkdir -p "$vdir"
	[[ -f $baseimg ]] || { echo "no base image: $baseimg" >&2; exit 1; }
	[[ ! -e $vdir/$name.img ]] || { echo "$vdir/$name.img exists; rm it first" >&2; exit 1; }
	# -c = clonefile: copy-on-write, so this is instant and costs nothing
	# until blocks are rewritten.
	cp -c "$baseimg" "$vdir/$name.img"
	echo "cloned $vdir/$name.img ($(du -h "$vdir/$name.img" | cut -f1) on disk)"
	;;
mount|shell|tweak)
	need_name
	img=$vdir/$name.img
	[[ -f $img ]] || { echo "no such variant: $img" >&2; exit 1; }
	dev=$(hdiutil attach -imagekey diskimage-class=CRawDiskImage -nomount "$img" 2>/dev/null |
		awk 'NF && $1 ~ /^\/dev\/disk/ {print $1; exit}')
	[[ -n $dev ]] || { echo "could not attach $img" >&2; exit 1; }
	finish() {
		sync
		diskutil unmount "$dev" >/dev/null 2>&1 || true
		hdiutil detach "$dev" -quiet -force 2>/dev/null || true
	}
	trap finish EXIT
	# owners is mandatory: a noowners mount silently discards chown.
	diskutil mount -mountOptions owners "$dev" >/dev/null
	mnt=""
	for _ in $(seq 30); do
		mnt=$(mount | awk -v d="$dev" '$1 == d { sub(/^.* on /, ""); sub(/ \(.*$/, ""); print; exit }')
		[[ -n $mnt && -d $mnt ]] && break
		sleep 1
	done
	[[ -n $mnt && -d $mnt ]] || { echo "could not mount $dev" >&2; exit 1; }
	echo "== $img at $mnt" >&2
	if [ "$cmd" = shell ]; then
		echo "   root shell on $mnt; exit when done (it syncs and unmounts)" >&2
		(cd "$mnt" && sudo -s)
	else
		shift 2
		for s in "$@"; do
			echo "== $s $mnt" >&2
			(cd "$repo/.." && sudo "$repo/tools/$s" "$mnt") || exit 1
		done
	fi
	;;
list)
	[[ -d $vdir ]] && ls -lh "$vdir" || echo "no variants yet"
	;;
rm)
	need_name
	rm -f "$vdir/$name.img"
	echo "removed $vdir/$name.img"
	;;
*)
	sed -n '2,20p' "$0"; exit 2
	;;
esac
