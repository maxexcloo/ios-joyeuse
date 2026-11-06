# Back to stock Android

The port never writes to the boot chain. `fastboot boot` loads the shim into RAM; the iOS root occupies `userdata` and
nothing else. So going back is: format `userdata`, and Android comes up as it was on its first day.

```sh
# hold Power + Volume down to reach fastboot
fastboot devices
fastboot -w reboot            # wipes userdata; stock boot chain boots Android
```

If the phone will not boot Android after the wipe, or the radio is misbehaving, restore the calibration partitions you
backed up first:

```sh
fastboot flash modemst1 backups/modemst1.img
fastboot flash modemst2 backups/modemst2.img
fastboot flash fsg     backups/fsg.img
fastboot flash fsc     backups/fsc.img
fastboot flash persist backups/persist.img
```

A full reflash from the stock MIUI/Android fastboot ROM also restores everything, including the boot chain.

## Things that persist

- **`userdata` is erased** by anything that installed iOS. That data is gone; the backup list in the README is for the
  calibration partitions, not for your photos.
- The ABL sometimes hangs right after a large `fastboot flash userdata`. That is a known Xiaomi behaviour, not damage:
  hold **Power + Volume down** and it recovers into fastboot.
- Never relock the bootloader while a non-stock image is anywhere on the device.

## Reading the kernel log

The port keeps a 4 MiB console ring at the end of `userdata` (patch 0047). After a crash:

```sh
fastboot boot recovery.img            # OrangeFox for miatoll, temporary
tools/sweet-log-pull.sh logs/boot.txt
adb reboot bootloader
```

While the phone is running iOS, the same log streams over USB instead (`tools/livelog.sh`), which avoids the round trip.
