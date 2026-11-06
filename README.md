# ios-miatoll

**Apple's iOS 16 running on a Redmi Note 9 Pro.**

A port of [ios-sweet](https://github.com/dipa-studio/ios-sweet) to the Redmi Note 9 family (`miatoll`: curtana,
joyeuse, excalibur, gram — Qualcomm SM7125 / Snapdragon 720G, Adreno 618). Apple's open-source XNU kernel (xnu-8796,
the iOS 16 generation), with ios-sweet's patches and the miatoll ones on top, runs the **unmodified iOS 16.7.16 (20H392)
userland of the iPhone X**. The phone is booted with `fastboot boot` from the stock Xiaomi bootloader; nothing is
written to the boot chain, and the iOS root lives in `userdata`.

> Experimental bring-up, not a usable phone OS. It **erases Android's user data**, Apple's security model is mostly
> switched off, and most hardware drivers are missing. Do not put anything personal on it.

## What works (2026-10-21, kernel 0101)

| Area | State |
| --- | --- |
| Boot | Stock ABL (unlocked) -> `fastboot boot` of the shim -> XNU |
| CPU | All 8 cores (6x Cortex-A55 + 2x Cortex-A76), PSCI, 16K pages, GICv3 |
| Storage | UFS host driver; journaled HFS+ root in `userdata`, read/write |
| Display | 1080x2400 panel; iOS sees an iPhone X (1125x2436), CoreAnimation in software |
| Touch | FocalTech FT8756 over bit-banged SPI (QUP SE11), delivered as HID events |
| Buttons | Power and volume through PMIC/SPMI; lock and wake |
| GUI | SpringBoard, lock screen, home screen, Control Center, notifications, Settings |
| Navigation | Home gesture and app switcher (`pid_hibernate`, edge-tip events) |
| USB | Ethernet to the host for the live kernel log and a `ue0` interface |
| Wi-Fi | **Firmware only** — WCN3990 boots, WMI/HTC up, scans find networks, but there is no `en0` (0101); 0103 adds it, never booted |
| Battery | IOPMPowerSource, static 100 % |
| Identity | iPhone X (`iPhone10,3` / `D22AP`), gesture UI |

**Not working:** GPU/Metal (CPU drawing, ~20-30 fps), Wi-Fi as an iOS interface, Bluetooth, audio, camera, sensors, GPS,
cellular, NFC, fingerprint, SEP / Face ID. Phone, Photos and Messages open to a black screen.

## How it boots

```
ABL (stock Xiaomi bootloader, unlocked)
  -> fastboot boot shim-boot.img        RAM only; the boot chain stays stock
       shim (shim/): own MMU setup, reads the live FDT, loads the payload from the ramdisk
  -> XNU (xnu/patches): UFS, display, touch, keys, USB, RPMh, HID built in
  -> launchd and the iPhone X userland from userdata
```

There is no serial port (the debug UART is wired as SPI). The kernel draws its console into the framebuffer ABL leaves
at `0x9c000000`, keeps a persistent 4 MiB log ring at the end of `userdata`, and can stream the log over USB
(`tools/livelog.sh`) so a crash does not need a trip back to recovery.

## Repository

| Path | What |
| --- | --- |
| `xnu/patches/` | 0001-0103, applied in order ([how to build and add one](xnu/README.md)) |
| `shim/` | The bare-metal shim ABL boots |
| `tools/` | Host tools: device tree, payload, root images, boot image, the phone loop |
| [INSTALL.md](INSTALL.md) | Getting it onto a phone, step by step |
| [RECOVERY.md](RECOVERY.md) | Back to Android, and reading the log from recovery |
| [RESEARCH.md](RESEARCH.md) | Where each missing feature stands, and which port already solves it |
| [NOTES.md](NOTES.md) | The engineering log: hardware facts, every boot, what broke and why |
| [DEVICE.md](DEVICE.md) | Test device, BOM variants, stock boot header |

## Building on macOS

`tools/mkiosroot.sh` assumes Linux with `apfs-fuse`, `hfsprogs` and root loop mounts. macOS needs none of that: the DMGs
attach natively, `newfs_hfs` formats, and only the ownership-sensitive copy runs as root. See
[INSTALL.md](INSTALL.md) for the commands; the tools are:

| Tool | Purpose |
| --- | --- |
| `mkiosroot-macos.sh` | root image: `hdiutil` + `newfs_hfs` + one `sudo` |
| `mkbootimg.py` | boot image packer (AOSP's Ubuntu package imports `gki.*` and does not run) |
| `build-shim-docker.sh` | cross-compiles the shim in Ubuntu |
| `root-finalize.sh`, `root-resume.sh` | idempotent tail steps; resume without recopying 11 GiB |
| `root-variant.sh` | instant `cp -c` clones for userland experiments |
| `cmdline.sh`, `livelog.sh`, `device.sh`, `askpass.sh` | boot args, live log, phone loop, sudo dialog |

Two things silently produce an image that looks fine and cannot boot:

1. `diskutil mount` mounts HFS+ **`noowners`** by default, so every `chown` is discarded. Mount with
   `-mountOptions owners`; `root-finalize.sh` hard-fails if you forget.
2. The IPSW DMGs must be attached with `hdiutil -owners on`, or every file reads as `501/20` and `rsync --numeric-ids`
   copies that lie.

The dyld shared cache must also be **hard-linked** into `System/Library/Caches/com.apple.dyld`, because
`ignition_level=1` looks at the plain path and on a real device `/private/preboot` is a separate volume.

## Not in git

Everything below is gitignored and cannot be shared: it is Apple's, Qualcomm's, or from your own phone.

- **The stock DTB** — `python3 tools/unpack_bootv2.py boot.img dtb/miatoll_unpacked` on your phone's `boot.img`
- **The iOS root** — the iPhone X iOS 16.7.16 (20H392) IPSW from Apple
- **The kernel** — `gh run download -n xnu-kernel` from the workflow
- **Partition backups** — `persist`, `modemst1/2`, `fsg`, `fsc` (calibration and IMEI)
- **Firmware** for Wi-Fi/cellular work, from the phone's own `modem` partition

## Credits

Built on ios-sweet by dipa-studio, with Wi-Fi/modem from ios-topaz. Licences and provenance in [CREDITS.md](CREDITS.md).
