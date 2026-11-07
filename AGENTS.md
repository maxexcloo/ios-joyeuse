# iOS Miatoll

- Scope is joyeuse/SM7125. The parent port's hardware results are upstream evidence; this checkout has not booted the local phone. Update README status only from identified device observations.
- `xnu/patches/` is the kernel source of truth; CI applies patches in numeric order. Add a numbered patch rather than editing a disposable build tree. Keep original patch numbers and provenance.
- Device tests use `fastboot boot`; installing the root writes `userdata`. Never write the bootloader, recovery, modem, persist or calibration partitions for bring-up. Get explicit approval immediately before each data-erasing action.
- Source DMGs require `-owners on`; mounted HFS+ requires `-mountOptions owners`. Do not bypass the ownership checks in the root tools.
- Keep Apple material, vendor firmware, partition dumps, DTBs, device logs and credential-bearing payloads/images out of git and output.
- Verify host changes with `mise run check`. Build the shim with `mise run build -- DTB PAYLOAD OUT` when relevant; a host build does not establish on-device behaviour.
