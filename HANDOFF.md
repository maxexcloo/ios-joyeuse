# HANDOFF

State of the miatoll port at the end of 2026-11-06, newest first. Observations are marked; everything else is verified.

## Where things stand

**Nothing has been flashed to a phone.** The Redmi has not been connected. Everything below is built and verified on
disk only.

| Artifact | Path | sha256 |
| --- | --- | --- |
| iOS root, 16 GiB HFS+, fsck clean | `~/Downloads/ios-redmi/out/ios16-root-miatoll.img` | `73857f85…f370` (pre-docs build) |
| Boot image, kernel 0098 (known-good, touch verified) | `out/shim-boot-miatoll.img` | `d27b33ca…e56d` |
| Boot image, kernel 0102 (0098 + race/stall fix) | `out/shim-boot-miatoll-0102.img` | `108b7420…dbf3` |

The two boot images share the one root image, so trying 0102 costs nothing but a `fastboot boot`.

`0102` was built from this repo (`gh run 42157866108`, success, 9m21s on `macos-15`) and the
`SWEET FB: empty IOAcceleratorES published` string is confirmed present in the kernel binary. **It has never been
booted.**

## Repo state

`maxexcloo/ios-miatoll` @ `e998ae9`, fork of `olaffx/ios-miatoll` (which forks `dipa-studio/ios-sweet`). `main` carries
the port plus this session's work:

- `799a85e` — the 10 macOS tools (`mkiosroot-macos.sh`, `root-finalize.sh`, `root-resume.sh`, `root-variant.sh`,
  `mkbootimg.py`, `build-shim-docker.sh`, `cmdline.sh`, `livelog.sh`, `device.sh`, `askpass.sh`) and the two
  silent-failure notes
- `1a76791` — `RESEARCH.md`
- `366f267` — CI moved to `macos-15`
- `1347ce5` — LICENSE (the fork and its parent were both published without one)
- `656c718`, `e998ae9` — docs restructured to match `ios-redfin`, then tightened

Docs: `README.md` (what works), `INSTALL.md` (six steps), `RESEARCH.md` (what's left and what it costs), `RECOVERY.md`,
`CREDITS.md`, `DEVICE.md`, `AGENTS.md`, `NOTES.md` (upstream log, kept as the archive).

## The next USB session

Have the phone connected and unlocked with USB debugging on.

```sh
cd ~/Downloads/ios-redmi
export PATH="/opt/homebrew/opt/android-platform-tools/bin:$PATH"

tools/device.sh backup backups/                        # FIRST: persist, modemst1/2, fsg, fsc
tools/device.sh flash-root out/ios16-root-miatoll.img  # ERASES ANDROID, 7-10 min
tools/livelog.sh logs/boot-001.txt &                   # start before booting
tools/device.sh boot out/shim-boot-miatoll-0102.img
```

Then, in order of what to learn:

1. **Does 0102 boot?** The app under test is the one line
   `SWEET FB: empty IOAcceleratorES published (no 30 s wait in CAMetalContextCreate)`. Watch `backboardd` restarts:
   the gap should collapse from ~30 s to near zero. If it panics instead, `tools/cmdline.sh good sweetaccel=0` disables
   the patch with no rebuild.
2. **Fallback** if 0102 is bad: boot `shim-boot-miatoll.img` (0098, never failed on this phone).
3. **Measure the baseline** while it is up: `SWEET FPS` swap rate in the log, time-to-home-screen, which apps open to a
   black screen. This is the number every later change gets compared against.

Escape hatches: `cpus=1` if SMP misbehaves; `fastboot boot` writes nothing, so a bad boot costs a reboot; the log ring
survives for `tools/sweet-log-pull.sh` from OrangeFox.

## Then, in order

**Wi-Fi is the highest-value next step.** The firmware already runs on this port (0101: WMI/HTC/HTT up, radio ready,
three scans finding ~7 networks, `SCE assign` ret=0). Only `en0` is missing. `0103-sweet-en0-autojoin.patch` is already
in the tree, unrun, gated on `wifi_ssid`/`wifi_pass` boot args. It needs a build and a boot with credentials:

```sh
tools/cmdline.sh good wifi_ssid=... wifi_pass=...
```

If it associates but spins, the fix per `RESEARCH.md` is the network service in
`/Library/Preferences/SystemConfiguration/preferences.plist` (configd will not DHCP without it) — that is a
`root-variant.sh shell` edit, ~2 minutes, no reflash of the kernel.

**GPU is the big one.** `DC28088/ios-sweet` branch `codex/native-adreno-metal` has working Metal on an Adreno 618; our
SM7125 has the same GPU. The work is redoing its SM7125 register/clock/resource constants, the same class of edit that
produced 0099 from ios-topaz. Read `RESEARCH.md` before starting.

## Things that will bite

- **Never mount HFS+ without `-mountOptions owners`**, and never attach the IPSW DMGs without `-owners on`. Both fail
  silently and produce an image that boots to nothing. `root-finalize.sh` now checks, but hand-run `hdiutil` commands do
  not.
- The dyld cache must stay **hard-linked** into `System/Library/Caches/com.apple.dyld`. A fresh root build that skips
  it will not reach launchd.
- Xiaomi's ABL hangs after a large `userdata` flash. Power + Volume down. Not damage.
- `fastboot getvar` never answers on this ABL.
- The iOS root is 16 GiB while `userdata` is ~107 GiB; the rest is unused. Resizing is possible but untested here.

## Out of reach, do not spend time

Cellular (CommCenter wants an Apple baseband interface), camera (Apple ISP stack), SEP / Face ID / fingerprint (separate
silicon), App Store / Apple ID (needs Apple attestation).
