#!/usr/bin/env python3
"""Pack an Android boot image header v2 -- the subset ABL on joyeuse needs.

  mkbootimg.py OUT --kernel Image --ramdisk payload.bin --dtb joyeuse.dtb
                [--cmdline "console=null"]

Replaces AOSP's mkbootimg, whose Ubuntu package imports gki.* and does not run.
Field order and offsets match tools/unpack_bootv2.py and AOSP
system/tools/mkbootimg/include/bootimg/bootimg.h (v2 header is 1660 bytes,
padded to the page size).
"""

import argparse
import hashlib
import os
import struct
import sys
from pathlib import Path

OS_PATCH_LEVEL = "2026-09"
OS_VERSION = "15.0.0"
PAGE = 4096


def os_version_field(version, patch):
    """mkbootimg's encoding: a<<25 | b<<18 | c<<11 | y<<4 | m (patch year-2000)."""
    parts = [int(x) for x in version.split(".")] + [0, 0]
    a, b, c = parts[0], parts[1], parts[2]
    y, m = (int(x) for x in patch.split("-"))
    return (a << 25) | (b << 18) | (c << 11) | ((y - 2000) << 4) | m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--ramdisk")
    ap.add_argument("--dtb", required=True)
    ap.add_argument("--cmdline", default="")
    a = ap.parse_args()

    blob = lambda p: Path(p).read_bytes() if p else b""
    kernel, ramdisk, dtb = blob(a.kernel), blob(a.ramdisk), blob(a.dtb)
    if not dtb:
        ap.error("DTB must not be empty")

    cmdline = a.cmdline.encode()
    if len(cmdline) > 512 + 1024:
        sys.exit("cmdline too long")
    cmd = (cmdline[:512]).ljust(512, b"\0")
    extra = cmdline[512:].ljust(1024, b"\0")

    # AOSP image ID: section bytes followed by their 32-bit length, including
    # recovery DTBO and DTB in header v2.
    h = hashlib.sha1()
    for part in (kernel, ramdisk, b"", b"", dtb):
        h.update(part)
        h.update(struct.pack("<I", len(part)))
    digest = h.digest()

    hdr = struct.pack(
        "<8s10I16s512s32s1024s",
        b"ANDROID!",
        len(kernel),
        0x8000,
        len(ramdisk),
        0x1000000 if ramdisk else 0,
        0,
        0,
        0x100,
        PAGE,
        2,
        os_version_field(OS_VERSION, OS_PATCH_LEVEL),
        b"\0" * 16,
        cmd,
        digest,
        extra,
    )
    assert len(hdr) == 1632, len(hdr)

    hdr += struct.pack("<IQI", 0, 0, 1660)
    hdr += struct.pack("<IQ", len(dtb), 0x1F00000)

    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        os.fchmod(f.fileno(), 0o600)
        for part in (hdr, kernel, ramdisk, dtb):
            f.write(part)
            f.write(b"\0" * (-len(part) % PAGE))
        size = f.tell()
    print(
        f"{a.out}: header v2 page {PAGE} "
        f"kernel {len(kernel)} ramdisk {len(ramdisk)} dtb {len(dtb)} "
        f"os {OS_VERSION}/{OS_PATCH_LEVEL} "
        f"total {size}"
    )


if __name__ == "__main__":
    main()
