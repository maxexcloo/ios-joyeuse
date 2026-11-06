# ios-miatoll

**Apple's iOS 16 running on a Redmi Note 9 Pro.**

A port of [ios-sweet](https://github.com/dipa-studio/ios-sweet) to the Redmi Note 9 family (`miatoll`: curtana, joyeuse,
excalibur, gram — Qualcomm SM7125 / Snapdragon 720G, Adreno 618). Apple's open-source XNU kernel (xnu-8796, the iOS 16
generation), with ios-sweet's patches and the miatoll ones on top, runs the **unmodified iOS 16.7.16 (20H392) userland of
the iPhone X**. The phone is booted with `fastboot boot` from the stock Xiaomi bootloader. Nothing is flashed to the boot
chain; the iOS root lives in the `userdata` partition.

> Experimental bring-up, not a usable phone OS. It **erases Android's user data**, Apple's security model is mostly
> switched off (permissive AMFI and sandbox, stub keystore), and most hardware drivers are missing. Do not put anything
> personal on it.

## What works (2026-10-21, kernel 0101)

| Area | State |
| --- | --- |
| Boot | Stock ABL (unlocked) -> `fastboot boot` of the shim -> XNU. Nothing written to the boot chain |
| CPU | All 8 cores (6x Cortex-A55 + 2x Cortex-A76), PSCI, 16K pages, GICv3 |
| Storage | UFS host driver; the iOS root is a journaled HFS+ volume in `userdata`, read/write |
| Display | The 1080x2400 panel ABL leaves running. iOS sees an iPhone X (1125x2436); CoreAnimation renders in software and frames are copied into ABL's framebuffer |
| Touch | FocalTech FT8756 over bit-banged SPI (QUP SE11), delivered as HID digitizer events |
| Buttons | Power and volume keys through PMIC/SPMI; lock and wake work |
| GUI | backboardd, SpringBoard, lock screen, home screen, Control Center, notification center, Settings |
| Navigation | Home gesture and app switcher work (`pid_hibernate`, edge-tip events) |
| USB | Ethernet to the host: live kernel log, plus the kernel's own `ue0` interface |
| Wi-Fi | **Firmware only.** WCN3990 boots, WMI/HTC/HTT up, radio ready, passive scans find networks — but no `en0`, so iOS has no interface (0101) |
| Battery | IOPMPowerSource service, static 100 % |
| Device identity | iPhone X (`iPhone10,3` / `D22AP`): no Home button, gesture UI |

**Not working yet:** GPU/Metal (everything drawn on the CPU at roughly 20-30 fps), Wi-Fi as an iOS interface, Bluetooth,
audio, camera, sensors, GPS, cellular, NFC, fingerprint, SEP / Face ID. Several apps (Phone, Photos, Messages) open to a
black screen.

## How it boots

```
ABL (stock Xiaomi bootloader, unlocked)
  -> fastboot boot shim-boot.img          RAM only; the boot chain stays stock
       shim (shim/): own MMU setup, reads the live FDT, loads the payload from the ramdisk
  -> XNU (xnu/patches): UFS, display, touch, keys, USB, RPMh, HID all built in
  -> launchd and the iPhone X userland from userdata
```

There is no serial port (the debug UART is wired as SPI on this board). The kernel draws its console into the framebuffer
ABL leaves at `0x9c000000`, and keeps a persistent 4 MiB log ring at the end of `userdata`. It can also stream the log
over USB (`tools/livelog.sh`), so a crash does not need a trip back to recovery.

## Repository

| Path | What |
| --- | --- |
| `xnu/patches/` | 0001-0101 from ios-sweet and ios-topaz plus the miatoll ones ([list](NOTES.md)) |
| `shim/` | The bare-metal shim ABL boots (`shim/build.sh`) |
| `tools/` | Host tools: ADT and payload, the root-image builders, the boot-and-collect-logs loop, `device.sh` for the phone |
| [NOTES.md](NOTES.md) | The engineering log: hardware facts, every boot, what broke and why ([RESEARCH.md](RESEARCH.md) for where the missing pieces stand) |
| [INSTALL.md](INSTALL.md) | Getting it onto a phone |
| [RESEARCH.md](RESEARCH.md) | Per-feature state of the work that is left, with the reference ports that already solve it |

## Building on macOS

`tools/mkiosroot.sh` assumes a Linux host with `apfs-fuse`, `hfsprogs` and root loop mounts. macOS needs none of that: it
attaches APFS natively, formats with `newfs_hfs`, and only the ownership-sensitive copy runs as root.

| Tool | Replaces | Notes |
| --- | --- | --- |
| `tools/mkiosroot-macos.sh` | `mkiosroot.sh` | `hdiutil` + `newfs_hfs` + one `sudo` |
| `tools/mkbootimg.py` | `mkbootimg` | AOSP's Ubuntu package imports `gki.*` and does not run |
| `tools/build-shim-docker.sh` | `shim/build.sh` | cross-compiles the shim in Ubuntu |
| `tools/root-finalize.sh` | root tweaks | idempotent, safe to re-run |
| `tools/root-resume.sh` | — | finish an image whose copy already ran |
| `tools/root-variant.sh` | — | instant `cp -c` clones for userland experiments |
| `tools/cmdline.sh` | — | merge boot args by name, no duplicates |
| `tools/livelog.sh` | `sweet-usbnet.sh` | macOS side of the live kernel log |
| `tools/device.sh` | — | backup / flash-root / boot / pull-log |
| `tools/askpass.sh` | — | password dialog for `sudo` from a detached shell |

```sh
# root image (one sudo prompt, ~15 min)
tools/mkiosroot-macos.sh OS.dmg SystemOS.dmg AppOS.dmg out/ios16-root.img 16G

# boot image
python3 tools/mkadt.py out/miatoll.adt --device miatoll --highmem
python3 tools/mkpayload.py kernel.development.sweet out/miatoll.adt out/payload.bin \
    --cmdline "$(tools/cmdline.sh good)"
tools/build-shim-docker.sh dtb/miatoll_unpacked/dtb out/payload.bin out/shim-boot.img
```

Two things silently produce an image that looks fine and cannot boot:

1. `diskutil mount` mounts HFS+ **`noowners`** by default, so every `chown` is discarded and the tree ends up owned by
   the building user. Mount with `-mountOptions owners`; `root-finalize.sh` hard-fails if you forget.
2. The IPSW DMGs must be attached with `hdiutil -owners on`, or every file reads as `501/20` and `rsync --numeric-ids`
   faithfully copies that lie.

The dyld shared cache must also be **hard-linked** from
`private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld` to `System/Library/Caches/com.apple.dyld`, because
`ignition_level=1` looks at the plain path and on a real device `/private/preboot` is a separate volume.

## Not in git: what you need to get yourself

Scripts expect these at the paths shown (all gitignored). None can be shared: they are Apple's files, or data from your
own phone.

- **The phone**: a Redmi Note 9S / 9 Pro / Note 10 Lite / POCO M2 Pro with the bootloader unlocked. Back up the
  per-device partitions first (persist, modemst1/2, fsg, fsc, ...) into `backup/`; they hold calibration data.
- **The stock DTB**: unpack your phone's `boot.img` with `tools/unpack_bootv2.py boot.img dtb/boot_unpacked`, giving
  `dtb/miatoll_unpacked/dtb`. The shim boots whatever the ABL already left in the framebuffer, so this must match your
  firmware.
- **The iOS root**: the iPhone X iOS 16.7.16 (20H392) IPSW from Apple. `tools/mkiosroot-macos.sh` (or the Linux
  `tools/mkiosroot.sh`) builds the HFS+ image from its OS/SystemOS/AppOS DMGs.
- **The kernel**: built on GitHub's macOS runners by `.github/workflows/xnu.yml`; `gh run download -n xnu-kernel`.
- **Firmware** for Wi-Fi/cellular work comes from the phone's own `modem` partition; see RESEARCH.md. Keep it out of git.

## Run it

```sh
tools/device.sh status                                    # phone in adb, authorised
tools/device.sh backup backups/                           # calibration partitions, first
tools/device.sh flash-root out/ios16-root.img             # ERASES ANDROID, 7-10 min
tools/livelog.sh logs/boot.txt &                          # catch the first boot
tools/device.sh boot out/shim-boot.img
```

## Credits

Built on ios-sweet by dipa-studio, with Wi-Fi/modem from ios-topaz. Licences and provenance in [CREDITS.md](CREDITS.md).
