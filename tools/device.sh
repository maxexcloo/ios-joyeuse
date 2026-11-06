#!/bin/bash
# Device-side helpers for the miatoll iOS port. Nothing here runs by itself;
# the destructive steps (flash userdata, boot) are separate commands.
#
#   device.sh status            fastboot/adb visibility
#   device.sh backup DIR        pull the per-device calibration partitions
#   device.sh flash-root IMG    fastboot flash userdata  (ERASES ANDROID DATA)
#   device.sh boot IMG          fastboot boot (RAM only, writes nothing)
#   device.sh pull-log FILE     read the 4 MiB console ring from userdata
#
# ADB/fastboot come from the Android platform-tools already on PATH.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)

case ${1:-} in
status)
	adb devices -l || true
	fastboot devices || true
	;;
backup)
	dir=${2:?usage: device.sh backup DIR}
	mkdir -p "$dir"
	# persist/modemst1/modemst2/fsg/fsc carry per-device calibration: without
	# them the radio never works again even on stock Android.
	for p in persist modemst1 modemst2 fsg fsc boot dtbo vbmeta modem; do
		echo "pulling $p"
		adb exec-out "dd if=/dev/block/by-name/$p 2>/dev/null" > "$dir/$p.img"
		ls -l "$dir/$p.img"
	done
	shasum -a 256 "$dir"/*.img > "$dir/SHA256SUMS"
	echo "backed up to $dir"
	;;
flash-root)
	img=${2:?usage: device.sh flash-root IMG}
	[[ -f $img ]] || { echo "no image: $img" >&2; exit 1; }
	# -S 512M: fastboot both splits the transfer and sparsifies the image.
	# Xiaomi's ABL often hangs after this finishes -> power + volume down.
	fastboot -S 512M flash userdata "$img"
	;;
boot)
	img=${2:?usage: device.sh boot IMG}
	# RAM only: nothing is written, the stock boot chain stays in charge.
	fastboot boot "$img"
	;;
pull-log)
	out=${2:?usage: device.sh pull-log FILE}
	"$REPO/tools/sweet-log-pull.sh" "$out"
	;;
*)
	sed -n '2,12p' "$0"
	exit 2
	;;
esac
