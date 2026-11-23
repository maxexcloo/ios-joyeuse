#!/usr/bin/env python3
"""Write an Android sparse image holding only the blocks where NEW differs from OLD.

  sparsediff.py OLD.img NEW.img OUT.simg [--block 4096]

OLD must match the partition byte for byte. After booting a writable root,
use a full image. Differing blocks become RAW chunks, everything else
DONT_CARE, so `fastboot flash PART OUT.simg` rewrites only the changes
instead of the whole image. Both images must be the same size.
"""

import argparse
import os
import struct
import sys

MAGIC = 0xED26FF3A
RAW, DONT_CARE = 0xCAC1, 0xCAC3
SPARSE_HEADER = struct.Struct("<IHHHHIIII")
CHUNK_HEADER = struct.Struct("<HHII")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("out")
    ap.add_argument("--block", type=int, default=4096)
    a = ap.parse_args()
    bs = a.block
    size = os.path.getsize(a.new)
    if os.path.getsize(a.old) != size or size % bs:
        sys.exit("images must have the same size, a multiple of the block size")
    nblocks = size // bs
    # The 32-bit chunk size includes the header and raw data.
    max_raw_blocks = (0xFFFFFFFF - CHUNK_HEADER.size) // bs

    # Pass 1: runs of (differs, count) at block granularity, streamed in 8 MiB reads.
    runs = []
    step = (8 << 20) // bs
    with open(a.old, "rb") as fo, open(a.new, "rb") as fn:
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

    # Pass 2: emit chunks, copying the differing blocks from NEW.
    changed = sum(c for d, c in runs if d)
    with open(a.new, "rb") as fn, open(a.out, "wb") as out:
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
        for differs, count in runs:
            left = count * bs if differs else 0
            out.write(
                CHUNK_HEADER.pack(
                    RAW if differs else DONT_CARE, 0, count, CHUNK_HEADER.size + left
                )
            )
            if differs:
                fn.seek(pos * bs)
                while left:
                    chunk = fn.read(min(left, 8 << 20))
                    out.write(chunk)
                    left -= len(chunk)
            pos += count
    print(
        f"{a.out}: {changed} of {nblocks} blocks changed "
        f"({changed * bs >> 20} MiB) in {sum(1 for d, _ in runs if d)} raw chunks"
    )


if __name__ == "__main__":
    main()
