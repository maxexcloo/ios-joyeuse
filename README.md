# iOS Miatoll

Experimental iOS 16.7.16 (20H392, iPhone X userland) on the Redmi Note 9 Pro (`joyeuse`, SM7125 / Snapdragon 720G).

## Status

**Local phone reaches iOS userland; the graphical boot remains unconfirmed.** The verified root is installed in `userdata`; USB kernel logs show backboardd and SpringBoard starting, while the screen remains on a logo with the diagnostic console overlay. Upstream patch 0098 reports SpringBoard, FT8756 touch, buttons, eight CPU cores, UFS and software rendering. The native shim and image packing have been checked offline. QEMU runs the static PID 1 diagnostic, including dyld policy and non-root socket-delegation checks. A virtual HFS root runs Apple launchd, backboardd and SpringBoard and renders the iOS lock and home screens in QEMU, unlocks with synthetic button/touch input and opens stock Settings; first boot also seeds the application database. Wi-Fi association/DHCP/traffic, GPU acceleration and other hardware remain unverified here. The port disables substantial parts of Apple's security model.

Patches 0104–0105 correct the WLAN Ethernet/BPF receive contract and a 32-bit physical-page shift that truncated cache maintenance above 4 GiB. Both modified consumers compile locally for ARM64; neither establishes radio or GPU operation. Root preparation seeds an Ethernet DHCP service for the kernel-only `en0`, which configd cannot automatically name through IOKit. The service uses Apple's [PreferencesMonitor](https://github.com/apple-oss-distributions/configd/blob/585b7f2fca293f4642d21d15c5daf187f63c4796/Plugins/PreferencesMonitor/prefsmon.c) and [IPConfiguration](https://github.com/apple-oss-distributions/bootp/blob/63cb751ca6a4e148704a701090481fd9a895dda0/IPConfiguration.bproj/ipconfigd.c) schema.

The [native Adreno donor](https://github.com/DC28088/ios-sweet/tree/67448d2151ef7520a8c4417a62a85823c62b30b5) shares the A618 architecture, but its GPU support spans power, firmware, SMMU, kernel and userland changes. Its WLAN carve-outs and SMMU stream ID differ from the saved stock DTB (also described by Linux's [SM7125 board](https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/qcom/sm7125-xiaomi-common.dtsi) and [SC7180 base](https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/qcom/sc7180.dtsi)); importing that stack requires board validation. The software-rendered baseline remains the next boot experiment.

## Build & Check

Host tools use Python's standard library and LLVM (`clang`, `ld.lld`, `llvm-objcopy`, `llvm-nm`, `llvm-readelf`). Homebrew LLVM is recognised; `CC`, `LD`, `OBJCOPY`, `NM` and `READELF` can select explicit tools.

The shared checks compile the production WLAN packet callbacks from the numbered patches and exercise Ethernet/BPF delivery, chained buffers and allocation failures under address and undefined-behaviour sanitizers (using `CXX` or `c++`).

```sh
mise run check
gh workflow run xnu.yaml
gh run download RUN_ID -n xnu-kernel -D xnu/out
```

Supply the phone's stock boot image, the unwrapped iPhone X `d22ap.adt`, and its FT8756 firmware, all kept in ignored `fw/`. Hardware ADTs require these product/firmware inputs; QEMU diagnostic trees may omit them.

```sh
mkdir -p out
python3 tools/unpack_bootv2.py fw/boot.img out/stock
python3 tools/mkadt.py out/miatoll.adt --device miatoll --highmem --product fw/d22ap.adt --touch-firmware fw/focaltech_ts_fw_huaxing.bin
tools/cmdline.sh good > out/cmdline.txt
python3 tools/mkpayload.py xnu/out/kernel.development.sweet out/miatoll.adt out/payload.bin --cmdline-file out/cmdline.txt
mise run build -- out/stock/dtb out/payload.bin out/shim-boot.img
```

The shim build verifies relocation safety, the ARM64 header and packed sections. `cmdline.sh good` preserves upstream 0098 arguments; append `cpus=1` to override one. The experimental `wifi` profile needs patches 0099–0104. Put credentials in a private command-line file. This Ethernet interface does not provide Wi-Fi controls in Settings.

Build the root using the OS/SystemOS/AppOS DMGs named by the IPSW's D22AP `BuildManifest.plist`:

```sh
tools/mkiosroot-macos.sh OS.dmg SystemOS.dmg AppOS.dmg out/ios16-root.img 16G
```

The root tools enforce ownership, apply bring-up preferences, invalidate MobileGestalt's hardware cache and link the dyld cache. `root-resume.sh` resumes a copy; `root-variant.sh` clones an image; `mkiosroot.sh` is the Linux path.

For offline kernel diagnostics, `mkadt.py --qemu` selects the virtual GIC, marks the tree for QEMU-only storage and supplies synthetic MAC identities for MobileGestalt queries. `qemu-sweet.py --disk IMAGE` creates a separate `disk.qcow2` overlay in its output directory; `rd=rvblk0 virtio_blk=1` selects a read-only HFS root, or `virtio_blk=2` permits guest writes to the overlay. Supply the matching `--kernel` for full `console.txt` capture and `--expect TEXT` for required diagnostic markers. Use `--disk-format qcow2` with a previous overlay to preserve guest progress in a new output directory.

An explicit `sweetsample=SpringBoard,backboardd,lsd,installd` enables process-stack diagnostics for the virtual root. Add `sweetsamplewait=1` to include kernel wait metadata; selectors use the kernel's 16-character process names (`containermanager` for containermanagerd).

`sweethidtest=30` sends periodic Home-button events. `sweethidtest=30 sweethidswipe=1` tests side-button presses followed by swipes and requires the QEMU tree marker. Set both `sweethidtapx` and `sweethidtapy` to follow each swipe with a tap in panel pixels; `sweethidcycles=N` limits the sequence so an app can remain foreground. Hardware ADTs never enable the virtual storage driver or swipe test.

## Device Workflow

Use an unlocked joyeuse and its own recovery image. Confirm the fitted touch controller; a stock `synaptics_tcm` node alone does not identify it. Back up first, then approve the `userdata` erase:

```sh
fastboot boot recovery.img
tools/device.sh backup backups/first
img2simg out/ios16-root.img out/ios16-root.simg 4096
tools/device.sh flash-root out/ios16-root.simg
```

Use Android sparse format for large roots (`brew install simg2img` provides `img2simg` on macOS). Fastboot 37 can fail reading a large raw image before transfer; the equivalent sparse image avoids that path.

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

Patches 0001–0081, the shim and most tools originate in ios-sweet; the later miatoll work supplies the board profile and touch support. Networking imports use [MakrSas/ios-topaz](https://github.com/MakrSas/ios-topaz) with miatoll constants. The dyld policy follows [ios-flame](https://github.com/NWylynko/ios-flame/tree/745c4341af86089efb0df851fa8a27fb8face624); the QEMU virtio block transport derives from [HakiOS](https://github.com/oosexgang/hakios-xnu-kernel/tree/63fc2b4633bac3af8e57dadab9f5a8d4cb940438), retaining its APSL provenance. This fork adds native host tooling and image checks. Vendor firmware and Apple's iOS files are supplied locally.

Reference work, not vendored: [DC28088's native Adreno/Metal branch](https://github.com/DC28088/ios-sweet), [ios-sweet-gpu](https://github.com/limonetexd/ios-sweet-gpu), and the [Pixel ports](https://github.com/denialofgravity/ios-redfin). Their hardware results are upstream reports.
