# iOS Miatoll

Experimental iOS 16.7.16 (20H392, iPhone X D22AP userland) on the Xiaomi Redmi Note 9 Pro (`joyeuse`, Snapdragon 720G / SM7125, Adreno 618). Based on [olaffx/ios-miatoll](https://github.com/olaffx/ios-miatoll), itself derived from ios-sweet. See [CREDITS.md](CREDITS.md) for provenance and licences.

**This checkout has not booted iOS on the local phone.** The parent port reports an interactive SpringBoard with FT8756 touch, hardware buttons, all eight CPU cores, UFS storage and software rendering at patch 0098. Those are upstream results, not local validation. Other miatoll variants and panel/controller combinations need their own verification.

| Area                  | Evidence & Remaining Work                                                                                                                                        |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Boot, display & touch | Upstream patch 0098 reports successful boots; local images still need a first boot                                                                               |
| Wi-Fi                 | Patches 0099–0103 contain modem firmware loading, an Ethernet interface and boot-argument autojoin; association, DHCP, DNS and traffic remain unverified locally |
| GPU                   | No accelerated renderer in this tree; related Adreno 618 work needs a board-specific port and on-device validation                                               |
| USB logging           | Code for CDC-ECM and UDP logging is present; the local USB path is unverified                                                                                    |
| Battery               | Static 100% indicator                                                                                                                                            |
| Other hardware        | No established Bluetooth, audio, camera, sensors, GPS, cellular, NFC or fingerprint support here                                                                 |
| Apps & Apple services | System apps have upstream failures; Apple ID/App Store support is not established                                                                                |

The root replaces `userdata`, erasing Android data. `fastboot boot` loads the shim into RAM and does not replace the boot chain. Rebooting selects the Android kernel again, but Android needs `userdata` reformatted before normal use. The port disables substantial parts of Apple's security model.

## Build & Check

Host tools use Python's standard library. The native shim build needs LLVM tools on `PATH`: `clang`, `ld.lld`, `llvm-objcopy`, `llvm-nm` and `llvm-readelf`. The builder recognises Homebrew’s keg-only LLVM directory; `CC`, `LD`, `OBJCOPY`, `NM` and `READELF` can select explicit executables. Run `mise run check` for Python/shell syntax and image-format tests, or `python3 tools/check.py` directly.

The XNU kernel builds through `.github/workflows/xnu.yaml`; its pinned build helper selects xnu-8796 with macOS 13.5 dependencies. Dispatch and download a specific run:

```sh
gh workflow run xnu.yaml
gh run download RUN_ID -n xnu-kernel -D xnu/out
```

Kernel changes are numbered patches under `xnu/patches/`, applied in order. `tools/xnu-cc.py` can replay a compile command against the workflow's `xnu-buildtree` artifact. The inherited patch sequence has no 0082 file; do not renumber it.

Extract the DTB from this phone's stock boot image and supply `d22ap.adt`, the unwrapped D22AP DeviceTree from your iPhone X IPSW. `--product` copies only its `/product` properties; a previous generated ADT containing that node is also accepted. Hardware builds fail without this input. QEMU diagnostic trees (`--qemu`) may omit it. Then build the device tree, payload and shim:

```sh
mkdir -p out
python3 tools/unpack_bootv2.py boot.img dtb/miatoll_unpacked
python3 tools/mkadt.py out/miatoll.adt --device miatoll --highmem --product d22ap.adt
tools/cmdline.sh good > out/cmdline.txt
python3 tools/mkpayload.py xnu/out/kernel.development.sweet out/miatoll.adt out/payload.bin --cmdline-file out/cmdline.txt
mise run build -- dtb/miatoll_unpacked/dtb out/payload.bin out/shim-boot.img
```

`mise run build` compiles the shim without a container, rejects absolute C pointers, checks the ARM64 Image header and round-trips the packed kernel, payload and DTB. It does not build XNU or prove the image boots. Direct equivalent: `python3 tools/build-shim.py DTB PAYLOAD OUT`.

`tools/cmdline.sh good` preserves the arguments from the parent's patch-0098 boot. `tools/cmdline.sh good cpus=1` overrides one argument. The `wifi` profile adds `modem=1 wifi=1`; it requires a matching kernel with patches 0099–0103. Store any experimental `wifi_ssid`/`wifi_pass` arguments in a private command-line file and use `--cmdline-file`; do not put credentials in shell commands or logs. Boot images and payloads containing them are secrets. This interface is not the Apple80211/wland stack and does not establish Wi-Fi controls in Settings.

## Root Image

Supply your own iPhone X IPSW. Obtain the OS, SystemOS and AppOS DMG names from its D22AP `BuildManifest.plist` identity. On macOS:

```sh
tools/mkiosroot-macos.sh OS.dmg SystemOS.dmg AppOS.dmg out/ios16-root.img 16G
```

The copy needs root permissions. Attach source DMGs with `-owners on` and mount HFS+ with `-mountOptions owners`; otherwise ownership is silently lost. `root-finalize.sh` applies the bring-up changes, invalidates cached MobileGestalt hardware answers and hard-links the dyld cache to its plain system path. `root-resume.sh` resumes a copy and `root-variant.sh` clones an image for experiments. `mkiosroot.sh` is the separate Linux path.

## Device Workflow

Use an unlocked joyeuse with its own recovery image. Keep calibration and partition backups off git. Confirm the actual phone/controller variant first: the upstream FT8756 uses SPI map `clk=55, mosi=54, miso=53, cs=56`; a `synaptics_tcm` node in a stock DT alone does not identify the fitted touch controller.

```sh
fastboot boot recovery.img
tools/device.sh backup backups/first
```

The backup command creates a new directory and verifies dump sizes. Preserve it before continuing. After the user approves erasing Android data, flash the root and start a separate terminal for logging:

```sh
tools/device.sh flash-root out/ios16-root.img
tools/livelog.sh logs/first-boot.txt
tools/device.sh boot out/shim-boot.img
```

`livelog.sh` waits for USB Ethernet and then listens on UDP 5140; its host address assignment requires sudo. Stop it with Ctrl-C. The boot command must run in another terminal while logging waits. First boot reportedly takes several minutes upstream; assess the panel and actual log rather than declaring success from a completed transfer. If USB logging never appears, boot recovery and run `tools/device.sh pull-log logs/first-boot.txt`.

For recovery and restoring Android, see [RECOVERY.md](RECOVERY.md). Do not relock the bootloader with modified software installed.

## Inputs Kept Locally

Apple images and caches, firmware, stock DTBs, device logs and partition backups are excluded from git. Kernel artifacts and built images live in `out/`, `xnu/out/` or the surrounding workspace. Existing outer-workspace patch-0098 artifacts came from upstream Actions run [39477434354](https://github.com/olaffx/ios-miatoll/actions/runs/39477434354); a newer filename or successful build is not a newer hardware result.
