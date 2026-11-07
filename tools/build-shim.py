#!/usr/bin/env python3
"""Build the miatoll ARM64 shim with LLVM and pack a verified boot image v2."""
import argparse
import hashlib
import os
from pathlib import Path
import struct
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parent.parent


def tool(name):
    if name in os.environ:
        return os.environ[name]
    executable = {"CC": "clang", "LD": "ld.lld", "NM": "llvm-nm",
                  "OBJCOPY": "llvm-objcopy", "READELF": "llvm-readelf"}[name]
    found = shutil.which(executable)
    if found:
        return found
    path = Path("/opt/homebrew/opt/llvm/bin") / executable
    if path.is_file():
        return str(path)
    raise FileNotFoundError(f"{executable}: set {name} or add LLVM to PATH")


def run(*args):
    return subprocess.check_output(args, cwd=REPO / 'shim', text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('dtb', type=Path)
    ap.add_argument('payload', type=Path)
    ap.add_argument('out', type=Path)
    a = ap.parse_args()
    dtb, payload, out = (p.resolve() for p in (a.dtb, a.payload, a.out))
    dtb.read_bytes()
    payload.read_bytes()
    out.parent.mkdir(parents=True, exist_ok=True)
    # Clang otherwise turns switch results into absolute string-pointer tables.
    flags = ('--target=aarch64-none-elf', '-O2', '-ffreestanding', '-nostdlib',
             '-fno-pic', '-fno-pie', '-mgeneral-regs-only', '-mstrict-align',
             '-fno-stack-protector', '-fno-jump-tables', '-Wall', '-Wextra', '-Werror')
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        objects = []
        for name in ('start.S', 'shim.c', 'console.c', 'mmu.c', 'fdt.c', 'loader.c', 'ufs.c'):
            obj = work / (Path(name).stem + '.o')
            run(tool('CC'), *flags, '-c', name, '-o', str(obj))
            objects.append(str(obj))
        if 'R_AARCH64_ABS64' in run(tool('READELF'), '-r', *objects[1:]):
            sys.exit('absolute pointers in C objects: shim must run without relocation')
        elf, image = work / 'shim.elf', work / 'Image'
        run(tool('LD'), '-m', 'aarch64elf', '-T', 'shim.ld', '--build-id=none', '-N',
            *objects, '-o', str(elf))
        run(tool('OBJCOPY'), '-O', 'binary', str(elf), str(image))
        symbols = run(tool('NM'), str(elf)).splitlines()
        size = next(int(line.split()[0], 16) for line in symbols if line.split()[-1] == '_end')
        with image.open('r+b') as f:
            f.truncate(size)
        data = image.read_bytes()
        if data[56:60] != b'ARM\x64' or struct.unpack_from('<Q', data, 16)[0] != size:
            sys.exit('ARM64 Image header does not match linked image')
        candidate = work / 'boot.img'
        run(sys.executable, str(REPO / 'tools/mkbootimg.py'), str(candidate),
            '--kernel', str(image), '--ramdisk', str(payload), '--dtb', str(dtb),
            '--cmdline', 'console=null')
        unpacked = work / 'unpacked'
        run(sys.executable, str(REPO / 'tools/unpack_bootv2.py'), str(candidate), str(unpacked))
        for name, expected in (('kernel', image), ('ramdisk', payload), ('dtb', dtb)):
            if (unpacked / name).read_bytes() != expected.read_bytes():
                sys.exit(f'boot image round trip failed: {name}')
        # Payloads can contain Wi-Fi credentials from --cmdline-file.
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'wb') as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(candidate.read_bytes())
    print(f'{out}: {size}-byte shim; kernel, payload and DTB verified')
    print(f'{hashlib.sha256(out.read_bytes()).hexdigest()}  {out.name}')


if __name__ == '__main__':
    main()
