#!/usr/bin/env python3
"""Pack an Android boot image header v2 -- the subset ABL on miatoll needs.

  mkbootimg.py OUT --kernel Image --ramdisk payload.bin --dtb miatoll.dtb
                [--base 0] [--kernel_offset 0x8000] [--ramdisk_offset 0x1000000]
                [--tags_offset 0x100] [--dtb_offset 0x1f00000] [--pagesize 4096]
                [--os_version 15.0.0] [--os_patch_level 2026-09]
                [--cmdline "console=null"] [--header_version 2]

Replaces AOSP's mkbootimg, whose Ubuntu package imports gki.* and does not run.
Field order and offsets match tools/unpack_bootv2.py and AOSP
system/tools/mkbootimg/include/bootimg/bootimg.h (v2 header is 1660 bytes,
padded to the page size).
"""

import argparse, hashlib, os, struct, sys

PAGE = 4096


def os_version_field(version, patch):
    """mkbootimg's encoding: a<<25 | b<<18 | c<<11 | y<<4 | m (patch year-2000)."""
    parts = [int(x) for x in version.split(".")] + [0, 0]
    a, b, c = parts[0], parts[1], parts[2]
    y, m = (int(x) for x in patch.split("-"))
    return (a << 25) | (b << 18) | (c << 11) | ((y - 2000) << 4) | m


def pad(data, page):
    return data + b"\0" * (-len(data) % page)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--ramdisk")
    ap.add_argument("--second")
    ap.add_argument("--dtb", required=True)
    ap.add_argument("--recovery_dtbo")
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--kernel_offset", type=lambda x: int(x, 0), default=0x8000)
    ap.add_argument("--ramdisk_offset", type=lambda x: int(x, 0), default=0x1000000)
    ap.add_argument("--second_offset", type=lambda x: int(x, 0), default=0xF00000)
    ap.add_argument("--tags_offset", type=lambda x: int(x, 0), default=0x100)
    ap.add_argument("--dtb_offset", type=lambda x: int(x, 0), default=0x1F00000)
    ap.add_argument("--pagesize", type=int, default=PAGE)
    ap.add_argument("--header_version", type=int, default=2, choices=(2,))
    ap.add_argument("--os_version", default="15.0.0")
    ap.add_argument("--os_patch_level", default="2026-09")
    ap.add_argument("--cmdline", default="")
    ap.add_argument("--name", default="")
    a = ap.parse_args()

    blob = lambda p: open(p, "rb").read() if p else b""
    kernel, ramdisk, second = blob(a.kernel), blob(a.ramdisk), blob(a.second)
    dtb, dtbo = blob(a.dtb), blob(a.recovery_dtbo)
    page = a.pagesize
    if page not in (2048, 4096, 8192, 16384):
        ap.error("page size must be 2048, 4096, 8192 or 16384")
    if not dtb:
        ap.error("DTB must not be empty")

    cmdline = a.cmdline.encode()
    if len(cmdline) > 512 + 1024:
        sys.exit("cmdline too long")
    cmd = (cmdline[:512]).ljust(512, b"\0")
    extra = cmdline[512:].ljust(1024, b"\0")
    name = a.name.encode()[:16].ljust(16, b"\0")

    # AOSP image ID: section bytes followed by their 32-bit length, including
    # recovery DTBO and DTB in header v2.
    h = hashlib.sha1()
    for part in (kernel, ramdisk, second, dtbo, dtb):
        h.update(part)
        h.update(struct.pack("<I", len(part)))
    digest = h.digest()

    hdr = struct.pack(
        "<8s10I16s512s32s1024s",
        b"ANDROID!",
        len(kernel),
        a.base + a.kernel_offset,
        len(ramdisk),
        a.base + a.ramdisk_offset if ramdisk else 0,
        len(second),
        a.base + a.second_offset if second else 0,
        a.base + a.tags_offset,
        page,
        a.header_version,
        os_version_field(a.os_version, a.os_patch_level),
        name,
        cmd,
        digest,
        extra,
    )
    assert len(hdr) == 1632, len(hdr)

    hdr += struct.pack(
        "<IQI", len(dtbo),
        page + sum(len(pad(p, page)) for p in (kernel, ramdisk, second)) if dtbo else 0,
        1660,
    )
    hdr += struct.pack("<IQ", len(dtb), a.base + a.dtb_offset)
    body = b"".join(pad(p, page) for p in (kernel, ramdisk, second, dtbo, dtb))

    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(pad(hdr, page) + body)
    print(
        f"{a.out}: header v{a.header_version} page {page} "
        f"kernel {len(kernel)} ramdisk {len(ramdisk)} dtb {len(dtb)} "
        f"os {a.os_version}/{a.os_patch_level} "
        f"total {len(pad(hdr, page) + body)}"
    )


if __name__ == "__main__":
    main()
