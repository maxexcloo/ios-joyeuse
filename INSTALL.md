# Installing

iOS 16.7.16 (20H392, iPhone X userland) on the Redmi Note 9 Pro. See
[README.md](README.md) for what works and what does not.

> **This erases Android's user data.** The boot chain is never written to, so the phone cannot be bricked by this,
> but your Android data does not survive.

## 0. Back up the phone

The per-device calibration partitions cannot be recreated. Boot OrangeFox (or any recovery with `adb root`) and dump
them before anything else:

```sh
fastboot boot recovery.img
tools/device.sh backup backups/          # persist, modemst1/2, fsg, fsc, boot, dtbo, vbmeta, modem
```

Keep `backup/` out of git: it carries your IMEI and calibration data.

## 1. Build the kernel

The kernel builds on GitHub's macOS runners (~8 min). Fork this repo, then:

```sh
gh workflow run xnu.yml -R YOU/ios-miatoll
gh run download RUN_ID -R YOU/ios-miatoll -n xnu-kernel -D xnu/out
```

Check a patch locally before spending a run with `tools/xnu-cc.py`.

## 2. Build the root image

Needs the iPhone X iOS 16.7.16 (20H392) IPSW. On macOS, with no extra packages (one `sudo` prompt, ~15 min):

```sh
tools/mkiosroot-macos.sh OS.dmg SystemOS.dmg AppOS.dmg out/ios16-root.img 16G
```

The DMG names are in the IPSW's `BuildManifest.plist`, keyed by the `d22ap` identity. `tools/mkiosroot.sh` is the
Linux equivalent (apfs-fuse, hfsprogs, root loop mounts).

## 3. Build the boot image

Needs the stock miatoll DTB: `python3 tools/unpack_bootv2.py boot.img dtb/miatoll_unpacked`.

```sh
python3 tools/mkadt.py out/miatoll.adt --device miatoll --highmem
python3 tools/mkpayload.py xnu/out/kernel.development.sweet out/miatoll.adt out/payload.bin \
    --cmdline "$(tools/cmdline.sh good)"
tools/build-shim-docker.sh dtb/miatoll_unpacked/dtb out/payload.bin out/shim-boot.img
```

`tools/cmdline.sh good` prints the proven boot arguments. To change one, name it: `tools/cmdline.sh good cpus=1`.

## 4. Flash the root, boot iOS

```sh
tools/device.sh flash-root out/ios16-root.img     # ~7-10 min, do not unplug
tools/livelog.sh logs/boot.txt &                  # catch the first boot's log
tools/device.sh boot out/shim-boot.img
```

The first boot takes ~4-5 minutes on the Apple logo, then the lock screen. Every later iOS session starts with the same
`fastboot boot`; a plain reboot returns to Android. Get to fastboot with **Power + Volume down**.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `fastboot getvar ...` hangs | This ABL never answers it; do not use it |
| `Sending 'boot.img'` never finishes | Ctrl-C, re-enter fastboot, retry; the link recovers |
| fastboot hangs after the userdata flash | Known Xiaomi behaviour; re-enter fastboot and continue |
| Boots Android instead | The RAM boot was lost on reboot; run `fastboot boot` again |
| Black screen or panic | Pull the log; try `cpus=1` |
| Touch dead but GUI up | Kernel older than 0098; rebuild from `main` |
| Console text over the GUI | Drop `sweetfb_noconsole=1` from the cmdline |

Back to Android, and how to read the log from recovery: [RECOVERY.md](RECOVERY.md).
