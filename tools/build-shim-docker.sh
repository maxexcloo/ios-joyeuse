#!/bin/bash
# Build shim-boot-miatoll.img without touching the host toolchain.
#
# aarch64-linux-gnu-gcc and the Android boot-image header are both awkward on
# macOS, so the shim is cross-compiled in an Ubuntu container and the image is
# packed here by tools/mkbootimg.py (AOSP's Ubuntu package imports gki.* and
# does not run).
#
#   tools/build-shim-docker.sh DTB PAYLOAD OUT.img
#
# Mirrors shim/build.sh: same CFLAGS, same link layout, same header fields
# (base 0, kernel 0x8000, ramdisk 0x1000000, tags 0x100, dtb 0x1f00000,
# pagesize 4096, os 15.0.0 / 2026-09 = the stock miatoll header).
set -euo pipefail
[[ $# -ge 3 ]] || { sed -n '2,12p' "$0"; exit 2; }
REPO=$(cd "$(dirname "$0")/.." && pwd)
dtb=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
payload=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
outdir=$(cd "$(dirname "$3")" && pwd)
out="$outdir/$(basename "$3")"
[[ -f $dtb ]] || { echo "no dtb: $dtb" >&2; exit 1; }
[[ -f $payload ]] || { echo "no payload: $payload" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

echo "cross-compiling the shim (ubuntu container)"
docker run --rm -v "$REPO/shim:/shim:ro" -v "$work:/w" ubuntu:24.04 bash -euc '
	apt-get update -qq >/dev/null 2>&1
	apt-get install -y -qq gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu binutils >/dev/null 2>&1
	cd /w
	cp /shim/*.c /shim/*.h /shim/*.S /shim/shim.ld .
	CC=aarch64-linux-gnu-gcc
	CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra"
	for f in start.S shim.c console.c mmu.c fdt.c loader.c ufs.c; do
		$CC $CFLAGS -c "$f" -o "${f%.*}.o"
	done
	# Only the header image_size (from start.o, linked at 0) may be absolute.
	abs=$(aarch64-linux-gnu-readelf -r shim.o console.o mmu.o fdt.o loader.o ufs.o | grep -c ABS64 || true)
	[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
	$CC $CFLAGS -static -T shim.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
		start.o shim.o console.o mmu.o fdt.o loader.o ufs.o -o shim.elf
	aarch64-linux-gnu-objcopy -O binary shim.elf Image
	end=$(aarch64-linux-gnu-nm shim.elf | awk "\$3==\"_end\"{print \$1}")
	printf "shim linked, _end=%s\n" "$end"
	# Pad to image_size so .bss/stacks exist as zeroed bytes: ABL copies exactly
	# this many bytes and the shim runs where it was placed.
	truncate -s "$((16#$end))" Image
	ls -l Image
'

python3 "$REPO/tools/mkbootimg.py" "$out" \
	--kernel "$work/Image" --ramdisk "$payload" --dtb "$dtb" \
	--base 0 --kernel_offset 0x8000 --ramdisk_offset 0x1000000 \
	--tags_offset 0x100 --dtb_offset 0x1f00000 --pagesize 4096 \
	--os_version 15.0.0 --os_patch_level 2026-09 \
	--cmdline "console=null"

# Round-trip through the repo's own unpacker: kernel == Image, ramdisk == payload.
python3 "$REPO/tools/unpack_bootv2.py" "$out" "$work/check" >/dev/null
cmp "$work/check/kernel" "$work/Image"  || { echo "kernel mismatch" >&2; exit 1; }
cmp "$work/check/ramdisk" "$payload"    || { echo "ramdisk mismatch" >&2; exit 1; }
cmp "$work/check/dtb" "$dtb"            || { echo "dtb mismatch" >&2; exit 1; }
echo "unpack verified: kernel == Image, ramdisk == payload, dtb == stock"
shasum -a 256 "$out"
