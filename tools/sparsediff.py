#!/usr/bin/env python3
"""Write an Android sparse image from a full image or an old/new diff.

Diff mode::
  sparsediff.py OLD.img NEW.img OUT.simg [--block 4096]

Full mode::
  sparsediff.py --full NEW.img OUT.simg [--block 4096]

Full mode emits RAW chunks for non-zero blocks and FILL-zero chunks for zero
blocks. Unlike DONT_CARE, FILL zeroes the destination, so the result describes
the complete image and does not depend on a previous partition contents.
"""

import argparse
import os
import struct
import sys

MAGIC = 0xED26FF3A
RAW, FILL, DONT_CARE = 0xCAC1, 0xCAC2, 0xCAC3
SPARSE_HEADER = struct.Struct("<IHHHHIIII")
CHUNK_HEADER = struct.Struct("<HHII")
FILL_VALUE = struct.pack("<I", 0)


def runs_for_full(path, bs, nblocks, max_raw_blocks):
    runs = []
    zero = b"\0" * bs
    with open(path, "rb") as f:
        for _ in range(nblocks):
            block = f.read(bs)
            kind = "fill" if block == zero else "raw"
            limit = max_raw_blocks if kind == "raw" else nblocks
            if runs and runs[-1][0] == kind and runs[-1][1] < limit:
                runs[-1][1] += 1
            else:
                runs.append([kind, 1])
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="OLD NEW OUT, or NEW OUT with --full")
    ap.add_argument("--block", type=int, default=4096)
    ap.add_argument(
        "--full", action="store_true", help="build a complete sparse image without OLD"
    )
    a = ap.parse_args()
    if a.full:
        if len(a.paths) != 2:
            ap.error("--full requires NEW.img OUT.simg")
        old = None
        new, out_path = a.paths
    else:
        if len(a.paths) != 3:
            ap.error("diff mode requires OLD.img NEW.img OUT.simg")
        old, new, out_path = a.paths

    bs = a.block
    size = os.path.getsize(new)
    if size % bs:
        sys.exit("image size must be a multiple of the block size")
    if old is not None and os.path.getsize(old) != size:
        sys.exit("images must have the same size")
    nblocks = size // bs
    max_raw_blocks = (0xFFFFFFFF - CHUNK_HEADER.size) // bs

    if a.full:
        runs = runs_for_full(new, bs, nblocks, max_raw_blocks)
    else:
        runs = []
        step = (8 << 20) // bs
        with open(old, "rb") as fo, open(new, "rb") as fn:
            for base in range(0, nblocks, step):
                n = min(step, nblocks - base)
                bo, bn = fo.read(n * bs), fn.read(n * bs)
                for i in range(n):
                    differs = bo[i * bs : (i + 1) * bs] != bn[i * bs : (i + 1) * bs]
                    limit = max_raw_blocks if differs else nblocks
                    if runs and runs[-1][0] == differs and runs[-1][1] < limit:
                        runs[-1][1] += 1
                    else:
                        runs.append([differs, 1])

    with open(new, "rb") as fn, open(out_path, "wb") as out:
        out.write(
            SPARSE_HEADER.pack(
                MAGIC,
                1,
                0,
                SPARSE_HEADER.size,
                CHUNK_HEADER.size,
                bs,
                nblocks,
                len(runs),
                0,
            )
        )
        pos = 0
        changed = 0
        for kind, count in runs:
            if a.full:
                if kind == "fill":
                    out.write(CHUNK_HEADER.pack(FILL, 0, count, CHUNK_HEADER.size + 4))
                    out.write(FILL_VALUE)
                else:
                    left = count * bs
                    out.write(
                        CHUNK_HEADER.pack(RAW, 0, count, CHUNK_HEADER.size + left)
                    )
                    fn.seek(pos * bs)
                    while left:
                        chunk = fn.read(min(left, 8 << 20))
                        out.write(chunk)
                        left -= len(chunk)
                    changed += count
            elif kind:
                left = count * bs
                out.write(CHUNK_HEADER.pack(RAW, 0, count, CHUNK_HEADER.size + left))
                fn.seek(pos * bs)
                while left:
                    chunk = fn.read(min(left, 8 << 20))
                    out.write(chunk)
                    left -= len(chunk)
                changed += count
            else:
                out.write(CHUNK_HEADER.pack(DONT_CARE, 0, count, CHUNK_HEADER.size))
            pos += count

    print(f"{out_path}: {changed} of {nblocks} blocks written, {len(runs)} chunks")


if __name__ == "__main__":
    main()
