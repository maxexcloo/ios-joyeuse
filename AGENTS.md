# iOS Joyeuse

- Scope is Redmi Note 9 Pro / joyeuse / SM7125. README owns observed status; hardware results inherited from the parent ports are upstream evidence, not local results.
- `xnu/patches/` owns kernel changes. Add numbered patches rather than editing a disposable build tree; preserve the inherited numbering, including its missing 0082. `tools/mkadt.py` owns the ADT and device profiles, `shim/` the native loader and `tools/sweet-root-tweaks.py` the root changes.
- Keep upstream identifiers such as `xiaomi,miatoll`, the `SWEET` machine config and `sweet*` boot arguments; patches match on them.
- Hardware ADTs require explicit D22AP `/product` input. QEMU diagnostic ADTs may omit it.
- FT8756 firmware is an external `--touch-firmware` input carried in `/chosen/focaltech-firmware`; do not embed vendor firmware in a kernel patch.
- Bring-up uses `fastboot boot` and writes only `userdata` for the root. Preserve the bootloader, recovery, modem and calibration partitions.
- Source DMGs require `-owners on`; HFS+ mounts require `-mountOptions owners`. Preserve the root tools' ownership checks.
- Run `mise run check`; rebuild the shim with `mise run build -- DTB PAYLOAD OUT` after relevant changes.
