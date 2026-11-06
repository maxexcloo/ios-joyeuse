# Where each missing feature actually stands

Research notes for taking the miatoll port further. Written 2026-11-06.
The point of this file: every "no" below has a known next step and a known
cost, so the work can be ordered instead of guessed at.

## The single biggest finding

[`DC28088/ios-sweet`](https://github.com/DC28088/ios-sweet), branch
**`codex/native-adreno-metal`**, is the same `sweet` port (SM7150, iOS
16.7.16 20H392, HFS+ root) taken much further. Its README claims, with
hardware in hand:

- **GPU/Metal works** — "Adreno 618 executes real GPU rendering for the iOS UI.
  Native Metal objects, AIR → NIR → freedreno/ir3 shader compilation, command
  submission and IOSurface integration are operational"
- **Wi-Fi works** — WCN3990 scans, joins WPA2, DHCP address, loads web pages
- **Bluetooth works** — pairing with laptop and headphones confirmed
- **Battery/charging** — real PM6150 fuel gauge, percentage, plug/unplug
- **Live USB debugging** — SSH + kernel file server for live userspace updates

`SM7150` and our `SM7125` both carry an **Adreno 618**, and both use the
**WCN3990**. That makes this branch the reference implementation for two of
our three "hard" items.

Related branches on the same repo, each one feature:
`claude/haptic-0198`, `claude/charge-0199`, `claude/audio-0195`/`0197`,
`claude/ipa-0192`, `claude/sleep-0200`, `codex/media-0211`,
`codex/cellular`, `codex/pm-merged`.

Also relevant: `limonetexd/ios-sweet-gpu` — the same port with the GPU ring
brought up and instrumented (`docs/GPU_BRINGUP.md`, patches 0097-0103 for
frame pacing). Its notes record the Adreno state after boot: GMU `0xbabeface`,
`CP_MEM_WRITE 0x5ee7c0de`, `IB FROM XNU MEMORY RAN` — i.e. **the GPU ring does
execute from XNU memory**. What was still missing there is presenting frames.

## Feature by feature

### backboardd 30 s stall — fixed, trivial
Patch **0102** in this repo publishes an empty `IOAcceleratorES` so
backboardd's `IOAccelerator -> 0 found` poll resolves instead of spinning
~358 times (~30–36 s) on every start. 42 lines, opt-out `sweetaccel=0`.
Never booted on miatoll. **Cost: one CI run.**

### Settings SIGTRAP — identified
`PodcastsUI` force-unwraps `URL.volumeTotalCapacity`, which is nil on HFS+.
Two ways out: report a capacity from the HFS+ volume (kernel `getattrlist`),
or patch the one binary. **Cost: half a day.**

### Wi-Fi — solved on sweet, needs porting
The chain is: RPMh/PMEM votes for the WLAN rails, SMMU stream mapping, WCN3990
firmware from the phone's own `modem` partition via rmtfs, a userspace
`wland` daemon, `en0`/Apple80211 glue, and a `preferences.plist` network
service or configd never DHCPs.

Our repo already has 0099 (WLAN/modem import from `ios-topaz`), 0100 (firmware
tables generated from *this phone's* modem partition) and 0101 (rmtfs
`hyp_assign` fix). 0101's log shows **firmware READY, WMI/HTC/HTT up, radio
ready, 3 scans finding ~7 networks**. What is missing is `en0` — patch 0103
writes it but was never booted.

So miatoll is arguably closer than sweet was: the firmware already runs. The
DC28088 branch tells us exactly what `en0` and the configd side need.
**Cost: days.** Highest value per unit effort.

### GPU / Metal — the big one, now de-risked
Needs, in order: Adreno SMMU (CB0 for GMU, CB1 for GPU), GMU firmware + HFI
(perf table in **kHz**, not MHz — a real bug they hit), CP/RB ring, then an
`IOGPUFamily`-shaped provider, then AIR→NIR→ir3 for shaders, then IOSurface
sharing with 64-byte-aligned rows.

`codex/native-adreno-metal` has all of this for a **618 on SM7150**. Our 618 on
SM7125 needs the SM7125 register window/clock/resource constants redone — the
same class of edit that produced 0099's miatoll constants from topaz's.
**Cost: weeks, but it is a port, not research.**

Caveat worth knowing: even with Metal, they measure 12–30 fps and user
feedback "under 30". GPU fixes *compositing and app rendering*, not raw speed;
the A76 core binding patches (0167/0176/0177/0178) exist for that.

### Audio — solved on sweet, ADSP-bound
`claude/audio-0195`/`0197`, plus `codex/media-0211` notes: ADSP runs, but the
sensor PD inside ADSP stalls and takes MODEM down with it. Same ADSP on
SM7125. **Cost: days-weeks.**

### Sensors / GPS — blocked behind ADSP
Same power domain as audio (SEE sensors PD). Not independent work.
`codex/cellular` notes list the user priority order: speaker → sensors → GPS.

### Bluetooth — solved on sweet
Patches 0154/0155 (WCN3990 UART transport + Skywalk privileges). Shares the
WCN3990 with Wi-Fi, so do Wi-Fi first and reuse the rails/firmware path.
**Cost: days.**

### Cellular — partial
`claude/ipa-0192` and `codex/cellular` exist. IPA v4.2 is the right block for
SM7125. Still gated on Apple's `CommCenter`, which the port deletes from
launchd because it crash-loops without a baseband interface.

## Suggested order

1. **0102 only** — the stall fix on top of the known-good 0098 kernel. One CI
   run, keeps the boot that works. Do this before anything else.
2. **Boot it, measure.** Live log over USB (`tools/livelog.sh`), fps counter,
   what actually feels broken.
3. **Wi-Fi** — port the DC28088 `en0`/wland/configd chain; miatoll's firmware
   already runs.
4. **GPU** — fork `codex/native-adreno-metal`, redo the SM7125 constants.
5. Everything else in dependency order (ADSP unlocks audio + sensors + GPS).

## Iteration cost, for planning

| Change | Cost |
| --- | --- |
| Root/userland tweak | ~2 min (`tools/root-variant.sh`, clonefile) |
| Kernel patch | ~8 min CI + boot + log pull |
| Rebuild root from IPSW | ~15 min (never needed after the first build) |
| Flash root (11 GiB) | ~7–10 min, only when the root changed |
| Boot + read log | live over USB, no reboot to recovery |
