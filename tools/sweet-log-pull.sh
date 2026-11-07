#!/bin/sh
# Read the SWEET console log (kernel patch 0047) from a phone booted into
# OrangeFox recovery (fastboot boot recovery/recovery.img; adb root shell).
#   tools/sweet-log-pull.sh OUT.txt
# Only reads: the last 1025 blocks (4 KiB) of the userdata partition.
set -eu
out=${1:?usage: sweet-log-pull.sh OUT.txt}
dev=$(adb shell 'for d in /dev/block/by-name/userdata /dev/block/bootdevice/by-name/userdata; do [ -e $d ] && readlink -f $d && break; done' | tr -d '\r')
[ -n "$dev" ] || { echo "userdata block device not found" >&2; exit 1; }
bytes=$(adb shell blockdev --getsize64 "$dev" | tr -d '\r')
mkdir -p "$(dirname "$out")"
skip=$((bytes / 4096 - 1025))
adb exec-out "dd if=$dev bs=4096 skip=$skip count=1025 2>/dev/null" > "$out.bin"
# macOS stat is BSD (`-f %z`); GNU is `-c %s`. This script runs on the host.
got=$(stat -f %z "$out.bin" 2>/dev/null || stat -c %s "$out.bin" 2>/dev/null || echo "?")
[ "$got" = 4198400 ] || { echo "incomplete log read: $got bytes, expected 4198400" >&2; exit 1; }
echo "$dev: $bytes bytes, read blocks $skip.. ($got bytes)" >&2
python3 "$(dirname "$0")/sweet-log.py" "$out.bin" "$out"
