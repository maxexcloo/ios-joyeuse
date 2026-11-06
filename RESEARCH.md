# Where the missing features stand

Every gap in the README has a known next step and a known cost, so the work can be ordered instead of guessed at.
Written 2026-11-06.

## The reference port

[`DC28088/ios-sweet`](https://github.com/DC28088/ios-sweet), branch **`codex/native-adreno-metal`**, is the same
`sweet` port (SM7150, iOS 16.7.16 20H392, HFS+ root) taken much further. Hardware-confirmed on that device:

- **GPU / Metal** — "Adreno 618 executes real GPU rendering for the iOS UI. Native Metal objects, AIR → NIR →
  freedreno/ir3 shader compilation, command submission and IOSurface integration are operational"
- **Wi-Fi** — WCN3990 scans, joins WPA2, DHCP address, loads web pages
- **Bluetooth** — pairing with laptop and headphones confirmed
- **Battery / charging** — real PM6150 fuel gauge, percentage, plug/unplug

`SM7125` and `SM7150` share the **Adreno 618** and the **WCN3990**, so the first and third are ports, not research.
Per-feature branches on the same repo: `claude/haptic-0198`, `claude/charge-0199`, `claude/audio-0195`/`0197`,
`claude/ipa-0192`, `claude/sleep-0200`, `codex/cellular`, `codex/media-0211`.

[`limonetexd/ios-sweet-gpu`](https://github.com/limonetexd/ios-sweet-gpu) is the second-most useful: the Adreno ring
brought up and instrumented. Its notes record GMU `0xbabeface`, `CP_MEM_WRITE 0x5ee7c0de` and `IB FROM XNU MEMORY RAN`
after boot — the ring does execute from XNU memory. What was missing there is presenting frames.

## Feature by feature

### backboardd 30 s stall — fixed in this repo, unrun
Patch 0102 publishes an empty `IOAcceleratorES` so backboardd's `IOAccelerator -> 0 found` poll resolves instead of
spinning ~358 times (~30-36 s) on every start. 42 lines, opt-out `sweetaccel=0`. **Cost: one CI run.**

### Settings crash — identified
`PodcastsUI` force-unwraps `URL.volumeTotalCapacity`, which is nil on HFS+. Either report a capacity from the HFS+
volume (kernel `getattrlist`) or patch the one binary. **Cost: half a day.**

### Wi-Fi — solved on sweet, needs porting
The chain is: RPMh/PMEM votes for the WLAN rails, SMMU stream mapping, WCN3990 firmware from the phone's own `modem`
partition via rmtfs, a userspace `wland` daemon, `en0`/Apple80211 glue, and a `preferences.plist` network service (or
configd never DHCPs).

This repo already has 0099 (WLAN/modem import from ios-topaz), 0100 (firmware tables generated from *this phone's*
modem partition) and 0101 (rmtfs `hyp_assign` fix). 0101's log shows firmware READY, WMI/HTC/HTT up, radio ready and
three scans finding ~7 networks. What is missing is `en0`; 0103 writes it and was never booted.

Patches are cumulative, so every kernel carries 0103 and turning Wi-Fi on needs no CI run: rebuild the payload with the
gate on and repack, ~1 minute. **The gate is `wifi=1`, not the credentials** — `wifi_enabled()` in 0099 reads that arg,
and without it 0103's whole en0/autojoin block is skipped with no log line. Use `tools/cmdline.sh wifi wifi_ssid=…
wifi_pass=…`; `cmdline.sh good` deliberately still matches the proven 0098 line and now refuses credentials it would
silently ignore.

0103 was audited against `ue0` (0075), the only ifnet in this tree known to work on the phone, before its first boot.
Three defects were fixed and are in `out/shim-boot-miatoll-0103-wifi.img` (`f1ce505d…c459`, kernel 0103 built by CI
run `42169711641`, unpack-verified): `SIOCAIFADDR` was unhandled (that is how configd assigns the DHCP address),
`default: return 0` claimed success for every unimplemented ioctl, and `SIOCADDMULTI`/`SIOCDELMULTI` were rejected.
`ifnet_set_lladdr()` deliberately stays after `ifnet_attach()`, matching `ue0`. **Never booted.**

Miatoll is arguably closer than sweet was, because the firmware already runs. **Cost: days.** Best value per effort.

### GPU / Metal — the big one, now de-risked
In order: Adreno SMMU (CB0 for GMU, CB1 for GPU), GMU firmware + HFI (perf table in **kHz**, not MHz — a real bug they
hit), CP/RB ring, an `IOGPUFamily`-shaped provider, AIR→NIR→ir3 for shaders, then IOSurface sharing with 64-byte-aligned
rows.

`codex/native-adreno-metal` has all of it for a 618 on SM7150. Our 618 on SM7125 needs the register window, clock and
resource constants redone — the same class of edit that produced 0099's miatoll constants from topaz's. **Cost: weeks,
but a port rather than research.**

Caveat: even with Metal they measure 12-30 fps and user feedback "under 30". GPU fixes *compositing and app
rendering*, not raw speed; their A76-binding patches (0167/0176/0177/0178) are the perf work.

### Audio and sensors — one blocker, three features
`claude/audio-0195`/`0197` plus `codex/media-0211`: ADSP runs, but the sensor power domain inside it stalls and takes
MODEM down with it. Sensors and GPS share that domain, so audio is the gate for all three. **Cost: days-weeks.**

### Bluetooth — solved on sweet
Patches 0154/0155 (WCN3990 UART transport, Skywalk privileges). Shares the WCN3990 with Wi-Fi, so do Wi-Fi first and
reuse the rails and firmware path. **Cost: days.**

### Cellular — partial
`claude/ipa-0192` and `codex/cellular` exist; IPA v4.2 is the right block for SM7125. Still gated on Apple's
`CommCenter`, which the port deletes from launchd because it crash-loops without a baseband interface.

## Order

1. **0102 only** on the known-good kernel — one CI run, keeps the boot that works.
2. **Boot it and measure**: live log, fps, what actually feels broken.
3. **Wi-Fi**, because the firmware already runs.
4. **GPU**: fork `codex/native-adreno-metal` and redo the SM7125 constants.
5. The rest in dependency order (ADSP unlocks audio, sensors and GPS).

## Cost of an iteration

| Change | Cost |
| --- | --- |
| Root/userland tweak | ~2 min (`tools/root-variant.sh`, clonefile) |
| Kernel patch | ~8 min CI, then boot and read the live log |
| Rebuild root from the IPSW | ~15 min (only the first time) |
| Flash the root | ~7-10 min, only when the root changed |
