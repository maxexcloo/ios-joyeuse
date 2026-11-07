# Recovery

The supported bring-up path starts the shim with `fastboot boot` and writes only `userdata` for the iOS root. Hold **Power + Volume Down** to enter fastboot if the running kernel is unresponsive. Xiaomi's ABL may also need this after a large root flash.

A normal reboot selects the Android kernel, but its user data has been replaced. To restore Android operation, approve a factory reset first, then format data from the phone's recovery or use:

```sh
fastboot -w
fastboot reboot
```

This erases the iOS root and any remaining user data. If Android still fails, use the correct stock fastboot ROM for the exact device and keep the bootloader unlocked until stock software is fully restored. Preserve partition backups; do not restore radio/calibration partitions merely because an experimental iOS boot failed.

## Read The Kernel Log

Patch 0047 stores a console ring in the last 1025 4 KiB blocks of `userdata`. Boot the phone's own recovery temporarily, then read it:

```sh
fastboot boot recovery.img
tools/device.sh pull-log logs/boot.txt
```

The pull checks the byte count before decoding. Treat the result as private device data. When USB Ethernet works, `tools/livelog.sh` captures UDP logs without entering recovery.
