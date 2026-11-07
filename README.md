# iOS Miatoll

Experimental iOS 16.7.16 (20H392, iPhone X userland) on the Redmi Note 9 Pro (`joyeuse`, SM7125 / Snapdragon 720G).

## Status

**No iOS boot on the local phone.** Upstream patch 0098 reports SpringBoard, FT8756 touch, buttons, eight CPU cores, UFS and software rendering. The native shim and image packing have been checked offline. Wi-Fi association/DHCP/traffic, GPU acceleration and other hardware remain unverified here. The port disables substantial parts of Apple's security model.

## Build & Check

Host tools use Python's standard library and LLVM (`clang`, `ld.lld`, `llvm-objcopy`, `llvm-nm`, `llvm-readelf`). Homebrew LLVM is recognised; `CC`, `LD`, `OBJCOPY`, `NM` and `READELF` can select explicit tools.

```sh
mise run check
gh workflow run xnu.yaml
gh run download RUN_ID -n xnu-kernel -D xnu/out
```

Supply the phone's stock boot image, the unwrapped iPhone X `d22ap.adt`, and its FT8756 firmware in `fw/`. Hardware ADTs require these product/firmware inputs; QEMU diagnostic trees may omit them.

```sh
mkdir -p out
python3 tools/unpack_bootv2.py boot.img dtb/miatoll_unpacked
python3 tools/mkadt.py out/miatoll.adt --device miatoll --highmem --product d22ap.adt --touch-firmware fw/focaltech_ts_fw_huaxing.bin
tools/cmdline.sh good > out/cmdline.txt
python3 tools/mkpayload.py xnu/out/kernel.development.sweet out/miatoll.adt out/payload.bin --cmdline-file out/cmdline.txt
mise run build -- dtb/miatoll_unpacked/dtb out/payload.bin out/shim-boot.img
```

The shim build verifies relocation safety, the ARM64 header and packed sections. `cmdline.sh good` preserves upstream 0098 arguments; append `cpus=1` to override one. The experimental `wifi` profile needs patches 0099–0103. Put credentials in a private command-line file. This Ethernet interface does not provide Wi-Fi controls in Settings.

Build the root using the OS/SystemOS/AppOS DMGs named by the IPSW's D22AP `BuildManifest.plist`:

```sh
tools/mkiosroot-macos.sh OS.dmg SystemOS.dmg AppOS.dmg out/ios16-root.img 16G
```

The root tools enforce ownership, apply bring-up preferences, invalidate MobileGestalt's hardware cache and link the dyld cache. `root-resume.sh` resumes a copy; `root-variant.sh` clones an image; `mkiosroot.sh` is the Linux path.

## Device Workflow

Use an unlocked joyeuse and its own recovery image. Confirm the fitted touch controller; a stock `synaptics_tcm` node alone does not identify it. Back up first, then approve the `userdata` erase:

```sh
fastboot boot recovery.img
tools/device.sh backup backups/first
tools/device.sh flash-root out/ios16-root.img
```

Start logging in one terminal and boot in another:

```sh
tools/livelog.sh logs/first-boot.txt
tools/device.sh boot out/shim-boot.img
```

Logging needs sudo for the host USB address. If USB logging fails, boot recovery and run `tools/device.sh pull-log logs/first-boot.txt`. First boot reportedly takes several minutes upstream.

**Recovery:** hold Power + Volume Down for fastboot, including after a stalled root flash. `fastboot boot` preserves the boot chain, but Android needs a factory reset after its user data is replaced. With approval to erase data, use recovery's format-data action or `fastboot -w`, then reboot. If stock Android still fails, use the exact device's stock fastboot ROM. Preserve calibration backups and keep the bootloader unlocked until stock software is restored.

## Inputs Kept Locally

`fw/` holds the device's `/vendor/firmware/focaltech_ts_fw_huaxing.bin`; the ADT carries it to patch 0098. Apple inputs, stock DTBs, backups and phone logs stay in ignored `ipsw/`, `dtb/`, `backups/` and `logs/`. Generated images/kernels use `out/` and `xnu/out/`. Older local prebuilt kernels retain their original embedded firmware and provenance; filenames do not establish hardware support.

## Credits & Licences

Forked from [olaffx/ios-miatoll](https://github.com/olaffx/ios-miatoll) and [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet), retaining the [MIT License](LICENSE). The miatoll additions use the same licence (Copyright (c) 2026 the ios-miatoll contributors). Patches modify Apple's XNU 8796.141.3 under APSL 2.0; upstream files retain their own licences.

Patches 0001–0081, the shim and most tools originate in ios-sweet; the later miatoll work supplies the board profile and touch support. Networking imports use [MakrSas/ios-topaz](https://github.com/MakrSas/ios-topaz) with miatoll constants. This fork adds native host tooling and image checks. Vendor firmware and Apple's iOS files are supplied locally.

Reference work, not vendored: [DC28088's native Adreno/Metal branch](https://github.com/DC28088/ios-sweet), [ios-sweet-gpu](https://github.com/limonetexd/ios-sweet-gpu), and the [Pixel ports](https://github.com/denialofgravity/ios-redfin). Their hardware results are upstream reports.
