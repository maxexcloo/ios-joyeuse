# iOS Joyeuse

Experimental iOS 16.7.16 (`20H392`, iPhone X userland) on the Redmi Note 9 Pro (`joyeuse`, SM7125 / Snapdragon 720G), based on [olaffx/ios-miatoll](https://github.com/olaffx/ios-miatoll) and [ios-sweet](https://github.com/dipa-studio/ios-sweet).

## Status

**The local joyeuse reaches the iOS lock screen and clock, but touch is unresponsive and the wallpaper is blank.**

| Area           | Evidence & Remaining Work                                                                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Boot & root    | Prepared root in `userdata` reaches the lock screen; USB logs show a MobileGestalt Wi-Fi identity wait in LaunchServices and a PosterBoard wallpaper assertion, then a restart |
| Touch          | FT8756 touch unresponsive locally; upstream patch 0098 reports SpringBoard, touch, buttons, eight CPU cores, UFS and software rendering                                        |
| QEMU           | Virtual HFS root runs launchd, backboardd and SpringBoard, renders lock and home screens, unlocks with synthetic input and opens Settings                                      |
| Networking     | Patches 0099–0104 import Topaz WLAN and seed a DHCP service for the kernel-only `en0`; association, DHCP and traffic unverified                                                |
| GPU            | Software rendering only; the A618 [native Adreno donor](https://github.com/DC28088/ios-sweet/tree/67448d2151ef7520a8c4417a62a85823c62b30b5) needs board validation             |
| Other hardware | Audio, cameras, sensors, cellular and power management unverified; substantial parts of Apple's security model are disabled                                                    |

## Build & Check

Host tools use Python (activated by Mise), its standard library and LLVM (`clang`, `ld.lld`, `llvm-objcopy`, `llvm-nm`, `llvm-readelf`). Homebrew LLVM is recognised; `CC`, `CXX`, `LD`, `OBJCOPY`, `NM` and `READELF` select explicit tools.

```sh
mise run check
gh workflow run xnu.yaml
gh run download RUN_ID -n joyeuse-xnu -D xnu/out
```

Hardware ADTs need the stock boot image, the unwrapped iPhone X `d22ap.adt`, the phone's FT8756 firmware and its Wi-Fi and Bluetooth addresses (six raw bytes each), all in `fw/`. Keep these inputs and the generated ADT and payload private.

```sh
mkdir -p out
python tools/unpack_bootv2.py fw/boot.img out/stock
python tools/mkadt.py out/joyeuse.adt --device joyeuse --highmem --product fw/d22ap.adt --touch-firmware fw/focaltech_ts_fw_huaxing.bin --wifi-mac fw/wifi-mac.bin --bluetooth-mac fw/bluetooth-mac.bin
tools/cmdline.sh good > out/cmdline.txt
python tools/mkpayload.py xnu/out/kernel.development.sweet out/joyeuse.adt out/payload.bin --cmdline-file out/cmdline.txt
mise run build -- out/stock/dtb out/payload.bin out/shim-boot.img
```

`cmdline.sh good` prints the upstream 0098 arguments; later `NAME=VALUE` arguments replace them (for example `cpus=1`). The `wifi` profile adds the experimental radio from patches 0099–0104; keep credentials in a private command-line file.

Build the root from the OS, SystemOS and AppOS DMGs named by the IPSW's D22AP `BuildManifest.plist`:

```sh
tools/mkiosroot-macos.sh ipsw/OS.dmg ipsw/SystemOS.dmg ipsw/AppOS.dmg out/ios16-root.img 16G
```

`root-resume.sh` finishes an interrupted image in place, `root-variant.sh` makes copy-on-write variants of `out/ios16-root.img`, and `sparsediff.py OLD NEW OUT.simg` writes only the changed blocks for reflashing.

For offline diagnostics, `mkadt.py --qemu` builds a virtual tree and `qemu-sweet.py --disk IMAGE --kernel KERNEL` boots it with a separate `disk.qcow2` overlay; `rd=rvblk0 virtio_blk=1` selects a read-only HFS root and `virtio_blk=2` permits overlay writes.

## Device Workflow

Use an unlocked joyeuse and its own recovery image. Confirm the fitted touch controller; a stock `synaptics_tcm` node alone does not identify it. Back up first, then approve the `userdata` erase:

```sh
fastboot boot RECOVERY.img
tools/device.sh backup backups/first
img2simg out/ios16-root.img out/ios16-root.simg 4096
tools/device.sh flash-root out/ios16-root.simg
```

Fastboot 37 can fail reading a large raw image, so flash the sparse copy (`brew install simg2img` provides `img2simg`). Start logging in one terminal (needs sudo for the host USB address) and boot in another:

```sh
tools/livelog.sh logs/first-boot.txt
tools/device.sh boot out/shim-boot.img
```

If USB logging fails, boot recovery and run `tools/device.sh pull-log logs/first-boot.txt`.

**Recovery:** hold Power + Volume Down for fastboot, including after a stalled root flash. `fastboot boot` preserves the boot chain, but Android needs a factory reset after its user data is replaced: with approval to erase data, use recovery's format-data action or `fastboot -w`, then reboot. If stock Android still fails, use this device's stock fastboot ROM. Preserve calibration backups and keep the bootloader unlocked until stock software is restored.

## Inputs Kept Locally

Firmware inputs stay in `fw/` (the touch firmware comes from the phone's `/vendor/firmware/`), Apple's IPSW parts in `ipsw/`, partition backups in `backups/`, phone logs in `logs/` and fetched reference sources in `research/`. Generated images and kernels use `out/` and `xnu/out/`.

## Credits & Licences

Forked from [olaffx/ios-miatoll](https://github.com/olaffx/ios-miatoll) and [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet), retaining the [MIT License](LICENSE). The miatoll additions use the same licence (Copyright (c) 2026 the ios-miatoll contributors). Patches modify Apple's XNU 8796.141.3 under APSL 2.0; upstream files retain their own licences.

Patches 0001–0081, the shim and most tools originate in ios-sweet; the later miatoll work supplies the board profile and touch support. Networking imports use [MakrSas/ios-topaz](https://github.com/MakrSas/ios-topaz) with miatoll constants. The dyld policy follows [ios-flame](https://github.com/NWylynko/ios-flame/tree/745c4341af86089efb0df851fa8a27fb8face624); the QEMU virtio block transport derives from [HakiOS](https://github.com/oosexgang/hakios-xnu-kernel/tree/63fc2b4633bac3af8e57dadab9f5a8d4cb940438), retaining its APSL provenance. Vendor firmware and Apple's iOS files are supplied locally.

Reference work, not vendored: [DC28088's native Adreno/Metal branch](https://github.com/DC28088/ios-sweet), [ios-sweet-gpu](https://github.com/limonetexd/ios-sweet-gpu), the [Pixel ports](https://github.com/denialofgravity/ios-redfin) and Linux's [SM7125 board](https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/qcom/sm7125-xiaomi-common.dtsi) and [SC7180 base](https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/qcom/sc7180.dtsi) trees.
