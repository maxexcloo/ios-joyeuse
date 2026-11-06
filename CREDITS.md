# Credits and licences

This repository is a fork of [ios-miatoll](https://github.com/olaffx/ios-miatoll), itself a fork of
[ios-sweet](https://github.com/dipa-studio/ios-sweet), and keeps ios-sweet's [MIT License](LICENSE). The miatoll
additions are under the same licence (Copyright (c) 2026 the ios-miatoll contributors), with these exceptions:

- `xnu/patches/` modify Apple's XNU, which is under the **Apple Public Source License 2.0**. The patched files stay
  under the APSL 2.0.
- Files that came from other projects keep their own licence, listed below.

Nothing from Apple's iOS or Qualcomm's firmware is in this repository; see the README for what you need to fetch
yourself.

## Projects this builds on

- **ios-sweet** (dipa-studio, <https://github.com/dipa-studio/ios-sweet>, MIT): the XNU port to the Redmi Note 10 Pro
  this is ultimately forked from. Patches 0001-0081, the shim and most of `tools/` started there.
- **ios-miatoll** (olaffx, <https://github.com/olaffx/ios-miatoll>, MIT): the Redmi Note 9 port. Patches 0082-0103
  and the miatoll device profile in `tools/mkadt.py` are its work; this fork adds the macOS build tooling, notes and
  research.
- **XNU** (Apple, APSL 2.0): xnu-8796.141.3.
- **ios-topaz** (MakrSas, <https://github.com/MakrSas/ios-topaz>): the Redmi Note 12 4G fork of ios-sweet. Patches
  0099-0103 (WCN3990 Wi-Fi/modem, firmware tables, rmtts, `en0`) came from there, with the miatoll hardware constants
  substituted.

## Reference ports (read, not vendored)

Not all of these are in the tree, but they are where the remaining features are solved or being solved:

- **ios-sweet `codex/native-adreno-metal`** (DC28088, <https://github.com/DC28088/ios-sweet>): Metal on the Adreno 618,
  working Wi-Fi, Bluetooth, battery/charging, live USB debugging, on the same iOS 16.7.16 + HFS+ root. The reference
  for the GPU and WLAN work described in `RESEARCH.md`.
- **ios-sweet-gpu** (limonetexd, <https://github.com/limonetexd/ios-sweet-gpu>): the Adreno ring brought up and
  instrumented under XNU, plus frame-pacing patches.
- **ios-flame / ios-redfin** (<https://github.com/denialofgravity/ios-redfin>): the Pixel 4 / Pixel 5 ports. Their
  `tools/build-root-mac.sh` and `tools/retweak-root.sh` are the same idea as this repo's macOS root tooling, and the
  redfin port is where `wland` and the `en0`/Apple80211 glue are known to work.
