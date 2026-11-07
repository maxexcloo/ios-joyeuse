#!/usr/bin/env python3
"""Boot a SWEETXNU payload (tools/mkpayload.py) in QEMU's virt board.

  qemu-sweet.py PAYLOAD OUTDIR [--secs N] [--gdb]

Does what shim/loader.c does on the phone, but on the host: places the
kernel segments, ADT and boot_args at their physical addresses and starts
the CPU at a 6-instruction stub that jumps to the entry with x0 = boot_args.
virt RAM starts at 0x40000000; with 4G it covers the phone's framebuffer
(0x9c000000) and the kernel's phys_base (0xb0000000) as plain memory.

After N seconds (or when the guest stops) it writes into OUTDIR:
  fb.png     the 1080x2400 framebuffer (what the phone screen would show)
  regs.txt   QEMU's view of CPU state
  qemu.log   exceptions with ESR/FAR/ELR (-d int,guest_errors)

With --kernel KERNEL (the matching unstripped Mach-O), also decode the
framebuffer using its iso_font into fb.txt and write result.json. This is a
snapshot of the circular screen, not a complete boot log. --fail-on-panic
returns 2 when a panic is visible; absence of a panic does not prove boot.
An undecodable or blank screen returns 3 with --fail-on-panic when no kernel console is available.
The matching kernel also enables full circular-console capture in console.txt.
--expect TEXT requires a console marker and returns 4 when it is missing.
--disk IMAGE exposes a host HFS image through virtio using disk.qcow2 in OUTDIR;
all guest changes are confined to that overlay. Use a diagnostic ADT and
rd=rvblk0 virtio_blk=1 (read-only) or 2 (writable).
"""

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

FB_BASE, FB_W, FB_H = 0x9C000000, 1080, 2400
FB_STRIDE = FB_W * 4
PAGE = 0x4000
STUB_PA = 0x40200000  # above the dtb QEMU places at RAM base
BOOT_LINE_LENGTH = 608


def build_image(payload):
    """Return (phys_base, ram_image, boot_args_pa, entry_pa)."""
    magic, ver, nsegs = struct.unpack_from("<8sII", payload, 0)
    assert magic == b"SWEETXNU" and ver == 1, "not a SWEETXNU v1 payload"
    virt_base, entry_va, adt_off, adt_size, kernel_end, phys_base, mem_size = (
        struct.unpack_from("<7Q", payload, 0x10)
    )
    cmdline = payload[0x48 : 0x48 + BOOT_LINE_LENGTH]
    delta = phys_base - virt_base
    adt_pa = kernel_end + delta
    ba_pa = (adt_pa + adt_size + PAGE - 1) & ~(PAGE - 1)
    top = ba_pa + PAGE
    img = bytearray(top - phys_base)
    for i in range(nsegs):
        vmaddr, _vmsize, foff, fsize = struct.unpack_from(
            "<4Q", payload, 0x2A8 + 32 * i
        )
        o = vmaddr + delta - phys_base
        img[o : o + fsize] = payload[foff : foff + fsize]
    img[adt_pa - phys_base : adt_pa - phys_base + adt_size] = payload[
        adt_off : adt_off + adt_size
    ]
    ba = struct.pack(
        "<HH4x4Q6QI4xQI",
        2,
        2,
        virt_base,
        phys_base,
        mem_size,
        top,
        FB_BASE,
        1,
        FB_STRIDE,
        FB_W,
        FB_H,
        32,
        0,
        adt_pa - delta,
        adt_size,
    )
    ba += cmdline + b"\0" * 4 + struct.pack("<QQ", 0, mem_size)
    assert len(ba) == 736
    img[ba_pa - phys_base : ba_pa - phys_base + len(ba)] = ba
    return phys_base, bytes(img), ba_pa, entry_va + delta


def stub(ba_pa, entry_pa):
    # ldr x0, =ba ; ldr x1, =entry ; br x1 ; nop ; .quad ba ; .quad entry
    return struct.pack(
        "<4I2Q", 0x58000080, 0x580000A1, 0xD61F0020, 0xD503201F, ba_pa, entry_pa
    )


def write_png(path, raw):
    rows = []
    for y in range(FB_H):
        line = raw[y * FB_STRIDE : (y + 1) * FB_STRIDE]
        rgb = bytearray(FB_W * 3)  # a8r8g8b8 little endian = B G R A in memory
        rgb[0::3], rgb[1::3], rgb[2::3] = line[2::4], line[1::4], line[0::4]
        rows.append(b"\0" + bytes(rgb))
    chunk = lambda t, d: (
        struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    )
    png = b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR", struct.pack(">IIBBBBB", FB_W, FB_H, 8, 2, 0, 0, 0)
    )
    png += chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b"")
    Path(path).write_bytes(png)


def payload_data(payload, va, size):
    """Read initialized segment bytes by VA (the payload has no slide)."""
    nsegs = struct.unpack_from("<I", payload, 12)[0]
    for i in range(nsegs):
        vmaddr, _, foff, fsize = struct.unpack_from("<4Q", payload, 0x2A8 + 32 * i)
        if vmaddr <= va and va + size <= vmaddr + fsize:
            offset = foff + va - vmaddr
            return payload[offset : offset + size]
    raise ValueError(f"VA {va:#x}+{size:#x} not in initialized payload segments")


def decode_screen(raw, font):
    """Exact glyph matching for pe_serial.c's 2x, white-on-black fbcon."""
    glyphs = {font[c * 16 : (c + 1) * 16]: chr(c) for c in range(32, 127)}
    rows, unknown = [], 0
    for row in range(FB_H // 32):
        chars = []
        for col in range(FB_W // 16):
            glyph = bytearray(16)
            for y in range(16):
                offset = (row * 32 + y * 2) * FB_STRIDE + col * 16 * 4
                for x in range(8):
                    if raw[offset + x * 8 : offset + x * 8 + 4] == b"\xff" * 4:
                        glyph[y] |= 1 << x
            key = bytes(glyph)
            char = glyphs.get(key, "?")
            unknown += key not in glyphs
            chars.append(char)
        rows.append("".join(chars).rstrip())
    return "\n".join(rows).rstrip() + "\n", unknown


def screen_result(screen, unknown):
    if "panic(cpu " in screen or "SWEET EARLY PANIC:" in screen:
        status = "panic"
    elif unknown:
        status = "incomplete_decode"
    elif screen.strip():
        status = "no_panic_observed"
    else:
        status = "blank_screen"
    return {"status": status, "unknown_glyphs": unknown, "snapshot_only": True}


def console_ring(ring, total):
    """Decode the kernel's monotonically counted circular console buffer."""
    if total <= len(ring):
        return ring[:total]
    start = total % len(ring)
    return ring[start:] + ring[:start]


def qmp(sock_path, *cmds, pmemsaves=()):
    """Run QEMU human-monitor commands over QMP (synchronous, unlike the echoing HMP socket)."""
    s = socket.socket(socket.AF_UNIX)
    s.connect(sock_path)
    f = s.makefile("rw")
    f.readline()

    def call(execute, **args):
        f.write(json.dumps({"execute": execute, "arguments": args}) + "\n")
        f.flush()
        while True:
            r = json.loads(f.readline())
            if "return" in r or "error" in r:
                return r

    call("qmp_capabilities")
    out = []
    for c in cmds:
        r = call("human-monitor-command", **{"command-line": c})
        if "error" in r:
            print(f"qmp {c!r}: {r['error']}", file=sys.stderr)
        out.append(r.get("return", ""))
    for address, size, filename in pmemsaves:
        r = call("pmemsave", val=address, size=size, filename=filename)
        if "error" in r:
            raise RuntimeError(f"qmp pmemsave: {r['error']}")
    s.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("outdir")
    ap.add_argument("--secs", type=float, default=20)
    ap.add_argument(
        "--gdb", action="store_true", help="start halted, gdb stub on :1234, no timeout"
    )
    ap.add_argument(
        "--hmp",
        action="append",
        default=[],
        help='extra monitor command run after stop (repeatable), e.g. "x /8gx 0xfffffe..."',
    )
    ap.add_argument(
        "--cpu", default="cortex-a76"
    )  # ARMv8.2 like Kryo 470, same ID_AA64MMFR0
    ap.add_argument(
        "--kernel",
        help="matching unstripped kernel, for exact framebuffer text decoding (uses llvm-nm)",
    )
    ap.add_argument(
        "--fail-on-panic",
        action="store_true",
        help="exit 2 for a visible panic, 3 for incomplete/blank decoding; requires --kernel",
    )
    ap.add_argument(
        "--disk",
        type=Path,
        help="HFS image; guest writes use a new disk.qcow2 overlay in OUTDIR",
    )
    ap.add_argument(
        "--expect",
        action="append",
        default=[],
        help="require text in the captured kernel console ring; repeatable",
    )
    a = ap.parse_args()
    if (a.fail_on_panic or a.expect) and not a.kernel:
        ap.error("--fail-on-panic and --expect require --kernel")
    payload = Path(a.payload).read_bytes()
    font = None
    log_symbols = {}
    if a.kernel:
        symbols = subprocess.check_output(
            ["llvm-nm", "--defined-only", a.kernel], text=True
        )
        fonts = [
            int(line.split()[0], 16)
            for line in symbols.splitlines()
            if line.split()[-1:] == ["_iso_font"]
        ]
        if len(fonts) != 1:
            ap.error("kernel must contain exactly one _iso_font symbol")
        font = payload_data(payload, fonts[0], 256 * 16)
        for line in symbols.splitlines():
            fields = line.split()
            if fields[-1:] and fields[-1] in ("_sweet_log_ring", "_sweet_log_total"):
                log_symbols[fields[-1]] = int(fields[0], 16)
    os.makedirs(a.outdir, exist_ok=True)
    out = os.path.abspath(a.outdir)

    phys_base, img, ba_pa, entry_pa = build_image(payload)
    Path(f"{out}/ram.bin").write_bytes(img)
    Path(f"{out}/stub.bin").write_bytes(stub(ba_pa, entry_pa))
    print(
        f"phys_base={phys_base:#x} boot_args={ba_pa:#x} entry={entry_pa:#x}",
        file=sys.stderr,
    )

    mon = f"{out}/mon.sock"
    if os.path.exists(mon):
        os.unlink(mon)
    # virt RAM starts at 0x40000000: cover the payload's RAM (mkadt.py --highmem needs 8G).
    mem_size = struct.unpack_from("<Q", payload, 0x40)[0]
    ram_gib = max(4, -(-(phys_base + mem_size - 0x40000000) // (1 << 30)))
    cmd = [
        "qemu-system-aarch64",
        "-M",
        "virt,gic-version=3",
        "-cpu",
        a.cpu,
        "-smp",
        "1",
        "-m",
        f"{ram_gib}G",
        "-nographic",
        "-serial",
        f"file:{out}/serial.txt",
        "-qmp",
        f"unix:{mon},server,nowait",
        "-d",
        "int,guest_errors,unimp",
        "-D",
        f"{out}/qemu.log",
        "-no-reboot",
        "-device",
        f"loader,file={out}/ram.bin,addr={phys_base:#x},force-raw=on",
        "-device",
        f"loader,file={out}/stub.bin,addr={STUB_PA:#x},force-raw=on",
        "-device",
        f"loader,addr={STUB_PA:#x},cpu-num=0",
    ]
    if a.disk:
        overlay = Path(out) / "disk.qcow2"
        if overlay.exists():
            ap.error(
                f"{overlay} exists; use a new output directory to preserve guest writes"
            )
        subprocess.run(
            [
                "qemu-img",
                "create",
                "-q",
                "-f",
                "qcow2",
                "-F",
                "raw",
                "-b",
                str(a.disk.resolve(strict=True)),
                str(overlay),
            ],
            check=True,
        )
        cmd += [
            "-global",
            "virtio-mmio.force-legacy=false",
            "-blockdev",
            json.dumps(
                {"driver": "file", "filename": str(overlay), "node-name": "disk-file"}
            ),
            "-blockdev",
            json.dumps(
                {"driver": "qcow2", "file": "disk-file", "node-name": "disk-root"}
            ),
            "-device",
            "virtio-blk-device,drive=disk-root",
        ]
    if a.gdb:
        cmd += ["-S", "-gdb", "tcp::1234"]
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
    if a.gdb:
        print("gdb stub on :1234; QMP socket:", mon, file=sys.stderr)
        p.wait()
        return
    t0 = time.time()
    while p.poll() is None and time.time() - t0 < a.secs:
        time.sleep(0.2)
    result = {"status": "qemu_exited", "qemu_returncode": p.returncode}
    if p.poll() is None:
        saves = [(FB_BASE, FB_STRIDE * FB_H, f"{out}/fb.raw")]
        if len(log_symbols) == 2:
            virt_base = struct.unpack_from("<Q", payload, 0x10)[0]
            delta = phys_base - virt_base
            saves += [
                (log_symbols["_sweet_log_ring"] + delta, 4 << 20, f"{out}/console.raw"),
                (
                    log_symbols["_sweet_log_total"] + delta,
                    8,
                    f"{out}/console-total.raw",
                ),
            ]
        _, regs, *extra = qmp(
            mon,
            "stop",
            "info registers",
            *a.hmp,
            pmemsaves=saves,
        )
        Path(f"{out}/regs.txt").write_text(
            regs + "".join(f"\n(qemu) {c}\n{r}" for c, r in zip(a.hmp, extra))
        )
        p.kill()
        p.wait()
        raw = Path(f"{out}/fb.raw").read_bytes()
        write_png(f"{out}/fb.png", raw)
        result = {"status": "not_decoded"}
        if font is not None:
            screen, unknown = decode_screen(raw, font)
            Path(f"{out}/fb.txt").write_text(screen)
            result = screen_result(screen, unknown)
        os.unlink(f"{out}/fb.raw")
        if len(log_symbols) == 2:
            ring = Path(f"{out}/console.raw").read_bytes()
            total = struct.unpack("<Q", Path(f"{out}/console-total.raw").read_bytes())[
                0
            ]
            console = console_ring(ring, total).decode("utf-8", errors="replace")
            Path(f"{out}/console.txt").write_text(console)
            result["console_bytes"] = total
            result["console_truncated"] = total > len(ring)
            result["framebuffer_status"] = result["status"]
            if "panic(cpu " in console or "SWEET EARLY PANIC:" in console:
                result["status"] = "panic"
            elif total and result["status"] != "panic":
                result["status"] = "no_panic_observed"
            missing = [text for text in a.expect if text not in console]
            result["missing_expectations"] = missing
            os.unlink(f"{out}/console.raw")
            os.unlink(f"{out}/console-total.raw")
    else:
        print(f"qemu exited early: {p.returncode}", file=sys.stderr)
    for f in ("ram.bin",):
        os.unlink(f"{out}/{f}")
    Path(f"{out}/result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), file=sys.stderr)
    print(f"{out}/fb.png  {out}/regs.txt  {out}/qemu.log", file=sys.stderr)
    if a.expect and (len(log_symbols) != 2 or result.get("missing_expectations")):
        return 4
    if a.fail_on_panic and result["status"] == "panic":
        return 2
    if a.fail_on_panic and result["status"] in ("incomplete_decode", "blank_screen"):
        return 3
    if result["status"] == "qemu_exited":
        return 1


if __name__ == "__main__":
    sys.exit(main())
