# iOS Miatoll

- Target joyeuse/SM7125. Hardware results inherited from the parent port are upstream evidence; the local phone reaches the iOS lock screen and clock, with touch unresponsive and a blank background.
- `xnu/patches/` is the source of truth. Add numbered patches rather than editing a disposable build tree; preserve the inherited numbering, including its missing 0082.
- Hardware ADTs require explicit D22AP `/product` input. QEMU diagnostic ADTs may omit it.
- Bring-up uses `fastboot boot` and writes only `userdata` for the root. Preserve the bootloader, recovery, modem and calibration partitions.
- Source DMGs require `-owners on`; HFS+ mounts require `-mountOptions owners`. Preserve the root tools' ownership checks.
- Run `mise run check`; rebuild the shim with `mise run build -- DTB PAYLOAD OUT` after relevant changes.
- FT8756 firmware is an external `--touch-firmware` input carried in `/chosen/focaltech-firmware`; do not embed vendor firmware in a kernel patch.
