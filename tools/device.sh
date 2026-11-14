#!/bin/bash
# Device-side helpers for the joyeuse iOS port. Nothing here runs by itself;
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
	mkdir -p "$(dirname "$dir")"
	mkdir "$dir"
	# persist/modemst1/modemst2/fsg/fsc carry per-device calibration: without
	# them the radio never works again even on stock Android.
	#
	# `adb exec-out "dd if=<missing>"` exits 0 and writes nothing, so a typo or
	# an A/B-only name silently produced a 0-byte "backup" that looks fine in
	# `ls`. Verify every dump against the size the kernel reports instead:
	# a partition that is absent here is reported as absent, never as empty.
	missing=""
	persist_missing=0
	for p in persist modemst1 modemst2 fsg fsc boot dtbo vbmeta modem; do
		# Partition names depend on the installed firmware; accept either form.
		dev=""
		for cand in "$p" "${p}_a"; do
			if adb shell "[ -e /dev/block/by-name/$cand ]" 2>/dev/null; then
				dev=$cand; break
			fi
		done
		if [ -z "$dev" ]; then
			echo "absent  $p (no /dev/block/by-name/$p or ${p}_a)"
			missing="$missing $p"
			[ "$p" = persist ] && persist_missing=1
			continue
		fi
		# `|| true`: under `set -e` a failing command substitution in an
		# assignment aborts the whole script before the error can be printed.
		want=$(adb shell "blockdev --getsize64 /dev/block/by-name/$dev" 2>/dev/null | tr -d '\r' || true)
		case $want in
		""|*[!0-9]*)
			echo "ERROR: cannot read the size of $dev (blockdev said: ${want:-nothing})." >&2
			echo "       adb must be root to read raw partitions: run 'adb root' (recovery or an" >&2
			echo "       eng/userdebug Android build; stock Android cannot). Nothing was written" >&2
			echo "       for $p, and an unverified dump is worse than none." >&2
			exit 1
			;;
		esac
		echo "pulling $dev ($want bytes)"
		adb exec-out "dd if=/dev/block/by-name/$dev 2>/dev/null" > "$dir/$p.img"
		got=$(stat -f %z "$dir/$p.img" 2>/dev/null || stat -c %s "$dir/$p.img" 2>/dev/null || echo 0)
		if [ -z "$want" ] || [ "$got" != "$want" ]; then
			echo "ERROR: $p dumped $got bytes, device reports ${want:-unknown}" >&2
			exit 1
		fi
	done
	if [ "$persist_missing" = 1 ]; then
		# persist is not optional: losing it costs the IMEI and the radio.
		echo "ERROR: persist not found; refusing to call this a backup" >&2
		exit 1
	fi
	if [ -n "$missing" ]; then
		echo "note: absent on this device:$missing"
	fi
	shasum -a 256 "$dir"/*.img > "$dir/SHA256SUMS"
	echo "backed up to $dir"
	;;
flash-root)
	img=${2:?usage: device.sh flash-root IMG}
	[[ -f $img ]] || { echo "no image: $img" >&2; exit 1; }
	devices=$(fastboot devices)
	[[ $(printf '%s\n' "$devices" | grep -c .) = 1 ]] || {
		echo "Need exactly one fastboot device; refusing to select another port's phone." >&2
		exit 1
	}
	device=$(printf '%s\n' "$devices" | awk '{print $1}')
	product=$(fastboot -s "$device" getvar product 2>&1 | awk '$1 == "product:" {print $2}')
	[[ $product = joyeuse ]] || {
		echo "Connected fastboot device reports product '$product', not joyeuse; refusing to flash." >&2
		exit 1
	}
	read -r -p "Erase Android user data and flash $img? Type ERASE: " answer
	[[ $answer = ERASE ]] || { echo "cancelled" >&2; exit 1; }
	# -S 512M: fastboot both splits the transfer and sparsifies the image.
	# Xiaomi's ABL often hangs after this finishes -> power + volume down.
	fastboot -s "$device" -S 512M flash userdata "$img"
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
