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

### Wi-Fi — the feature (what is left to do)
The chain is: RPMh/PMEM votes for the WLAN rails, SMMU stream mapping, WCN3990 firmware from the phone's own `modem`
partition via rmtfs, a userspace `wland` daemon, `en0`/Apple80211 glue, and a `preferences.plist` network service (or
configd never DHCPs). Both the `wland` daemon and the Apple80211/IO80211 glue exist today in `DC28088/ios-sweet`'s
`userspace/wifi` — they are ports, not unwritten work.

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

Two routes exist, and they are not the same amount of work:

- **Light (what 0103 does):** kernel `ifnet` + autojoin, no `wland`, no Apple80211. Gets `en0` and BPF so configd can
  DHCP, but wifid has no 802.11 driver nub, so Settings shows no Wi-Fi UI. Cheapest path to an IP address.
- **Full (what redfin and DC28088 have):** `wland` userspace daemon over `/dev/wlan`, `Apple80211` as
  `SIOCGA80211`/`SIOCSA80211` on a `RedwoodWLAN`-shaped `IO80211Controller`, plus `MiniIONetworkStack.cpp` so
  configd's InterfaceNamer waits for it. This is what put a Wi-Fi icon in Settings. The userspace half already exists
  in `DC28088/ios-sweet`'s `userspace/wifi` — see the repo reference below — so it is a port, not new work.

Either route also needs the network service in `preferences.plist`: this root image has **no**
`/var/preferences/SystemConfiguration/preferences.plist` at all (checked inside the built image), so configd has never
had an `en0` service to run DHCP on. Redfin solved exactly this with a small plistlib script
(`tools/sunfish-netprefs.py` in `denialofgravity/ios-redfin`) that adds the `NetworkServices` + `Sets` entries and
restarts configd. Ours needs no SSH — it is an offline edit on a `tools/root-variant.sh` clone, ~2 min.

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

1. **Flash and boot** the built kernel — nothing further is learnable without a root filesystem on the device.
2. **Wi-Fi**, because the firmware already runs and both halves (light `ifnet`, full `wland`+Apple80211) now have a
   written reference to port from.
3. **GPU**: fork `codex/native-adreno-metal` and redo the SM7125 constants.
4. The rest in dependency order (ADSP unlocks audio, sensors and GPS).

## Repo reference

A sweep of the wider family, 2026-11-06. Only entries marked **verified** were checked against the repo itself (exists,
stars, default branch, last push, or a file listing); the rest came from the sweep and are unconfirmed. Treat the
claim columns as what the repo *says*, not as hardware evidence — this family has a documented history of presenting
claims outrunning what is on film.

### Direct lineage

| Repo | What it is | Status |
| --- | --- | --- |
| [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet) | root of the family: Redmi Note 10 Pro, SM7150, Adreno 618, WCN3990. 863 forks, almost all empty | **verified** |
| [olaffx/ios-miatoll](https://github.com/olaffx/ios-miatoll) | our parent; 5 forks total, 3 empty | **verified** |
| [maxexcloo/ios-miatoll](https://github.com/maxexcloo/ios-miatoll) | ours — Redmi Note 9 Pro, SM7125 | **verified** |

### Wi-Fi — the reference trees to port from

[`DC28088/ios-sweet`](https://github.com/DC28088/ios-sweet) branch `codex/native-adreno-metal` carries a complete
**`userspace/wifi`** tree, which is the `wland` daemon RESEARCH.md listed as missing:

```
.github/workflows/wifi.yml
tools/adt-add-wlan.py
tools/prepare-sweet-wland-job.py
userspace/wifi/patches/0001-sweet-board-rails-msa-bdf.patch
userspace/wifi/patches/0002-sweet-kernel-programs-wlan-smmu-stream.patch
xnu/patches/0138-sweet-wifi-pmem-wlan-from-flame.patch
xnu/patches/0141-sweet-pmem-rpmh-wifi-votes.patch
xnu/patches/0153-sweet-kernel-wlan-smmu-stream.patch
```

**verified** (file listing), last push 2026-11-03. This is the same WCN3990 on the same board family, so it is a port
candidate rather than research. It is the full route (wland + Apple80211 + IO80211, which is what put a Wi-Fi icon in
Settings on redfin); our 0103 is the light route (kernel `ifnet` + autojoin, no wland). Branch also has
`codex/unixnu-ios16-sweet` and `codex/adreno-power-audit`.

[`limonetexd/ios-sweet-gpu`](https://github.com/limonetexd/ios-sweet-gpu) — Adreno ring instrumented. **Its README says
the work is "99% vibe coded"; treat the ring/present claims as unverified** until a photographed screen backs them.

### Same family, different SoC (Xiaomi ABL + `fastboot boot`, same patch shape)

| Repo | Device | What it reached | Status |
| --- | --- | --- | --- |
| [TigerShota/ios-sweet](https://github.com/TigerShota/ios-sweet) | Redmi Note 9 Pro **5G** (`gauguin`, SM7225, Adreno 619) | SpringBoard UI 2026-11-04; Novatek NT36672C touch working; CPU rendering; GPU bring-up to GX-rail readable | **verified**; best-documented working record in the family. Note: Adreno **619**, not our 618 |
| [seshubonn/ios-karna](https://github.com/seshubonn/ios-karna) | POCO X3 (SM7150-AC, Adreno 618, sweet board family) | board-layer port; Novatek SPI touch missing | **verified** (exists, ★0, pushed 2026-11-05) |
| [zeroninefourfour/ios-extra](https://github.com/zeroninefourfour/ios-extra) | — | ios-sweet author's driver playground with CI; validated work upstreamed. Watch, do not fork | **verified** |
| [turgayasuk-sketch/ios-topaz](https://github.com/turgayasuk-sketch/ios-topaz) | Redmi Note 12 | lock screen in ~3 min via direct MDP scanout, no GPU compositor | **verified** (★36, pushed 2026-10-20) |

### Exact device, other lineage (a parallel bet, not a shortcut)

| Repo | What | Status |
| --- | --- | --- |
| [qdizax-w/UniXNU-miatoll](https://github.com/qdizax-w/UniXNU-miatoll) | exact device (miatoll, SM7125), UniXNU device repo — config/DTS/drivers only | **verified**; README says "first-console stage, nothing verified on the phone yet". Not under the `UniXNU` org — the sweep had that wrong |
| [qdizax-w/UniXNU-sm7125-common](https://github.com/qdizax-w/UniXNU-sm7125-common) | shared SM7125 config | **verified**; same caveat |

Its value is the SM7125 constants (GIC-500 `0x17a00000`, 19.2 MHz counter, INTID 19) as a cross-check, not as a boot
path. [UniXNU/UniXNU](https://github.com/UniXNU/UniXNU) itself was evaluated and rejected for this port: iPadOS
17.7.11, arm64e, "first-console stage".

### GPU — the two references that matter

| Repo | What | Status |
| --- | --- | --- |
| [DC28088/ios-sweet](https://github.com/DC28088/ios-sweet) `codex/native-adreno-metal` | the Adreno 618 Metal path (SM7150) | **verified** branch |
| [Ken-u/MaliMetal](https://github.com/Ken-u/MaliMetal) | Mali-G610 on RK3588/UniXNU: PanVK cross-built for iOS, `darwin-drm` libdrm stand-in over a Mali IOKit user client, `NativeMaliMetalPlugin`, metal2vulkan. Claims lock screen composited on GPU, ~50 fps scroll | **verified** (exists, ★0, pushed 2026-11-01); **claims unverified** |
| [Dracen-W/MaliMetal](https://github.com/Dracen-W/MaliMetal) | Mali-G52; design document only, says the kernel driver is the critical path | **verified** |
| [steelbrain/metal2vulkan](https://github.com/steelbrain/metal2vulkan) | Metal→Vulkan translation | used by redfin |

### MediaTek / Jelly Star (out of scope for this repo, kept for the sibling port)

| Repo | What | Status |
| --- | --- | --- |
| [oosexgang/hakios-mt6768](https://github.com/oosexgang/hakios-mt6768) | Infinix Hot 20, MT6768/G85, eMMC. **`mtkloader` in `boot_a`**: starts XNU once when Android asks and returns to Android after every run; iOS in an `xnusys` partition carved from `userdata`. Solves the "slot B is all zeros" problem without flashing the boot chain. Touch firmware loaded by the loader before XNU starts (same class as the Chipsea problem). 4 cores, SCP sensors, Mali-G52 via panfrost | **verified** (★5, pushed 2026-11-05); capability claims unverified |
| [lizi600jin/hakios-xaga](https://github.com/lizi600jin/hakios-xaga) | Dimensity 8100; SpringBoard up, touch working, no GPU (3-14 fps) | **verified** (★2, pushed 2026-11-06) |
| [qu33rl1nk/ios-topaz](https://github.com/qu33rl1nk/ios-topaz) branch `asteroids` | Nothing Phone 3a; boots **entirely from RAM**, nothing flashed, `userdata` untouched, reboot returns Android | **verified** (★1, branch `asteroids`, pushed 2026-10-27) |
| [squeeeezy/HelioDarwin](https://github.com/squeeeezy/HelioDarwin) | MediaTek Helio base for the Jelly Star port; supplies the UFS half that hakios-mt6768's eMMC does not | referenced by the sibling port |
| [lib-fluff-so/KLiOS716](https://github.com/lib-fluff-so/KLiOS716) | iOS 7.1.6 work, from Jelly Star recon | referenced by the sibling port |
| [woaphone/UniXNU-mt6789-common](https://github.com/woaphone/UniXNU-mt6789-common) | shared MT6789 config (Redmi Pad); config/DTS only, no drivers | from the sweep, unverified |
| [YinCQL/UniXNU-picasso](https://github.com/YinCQL/UniXNU-picasso) branch `feat/ios16-gpu` | Redmi K30 5G, **exact SM7250**, retargeted to iPhone X / iOS 16.7.16; early userspace, service startup incomplete | **verified** (★7, pushed 2026-11-06) |

### Supporting tooling

[blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build) (what our CI uses, pinned `663906528d…`) ·
[blacktop/ipsw](https://github.com/blacktop/ipsw) ·
[oosexgang/hackios-xnu-kernel](https://github.com/oosexgang/hackios-xnu-kernel) +
[hackios-xnu-userland](https://github.com/oosexgang/hackios-xnu-userland) (keystore wrap/unwrap) ·
[linux-msm/hexagonrpc](https://github.com/linux-msm/hexagonrpc) (ADSP, for audio/sensors) ·
[sgan81/apfs-fuse](https://github.com/sgan81/apfs-fuse) (Linux root build only).

### Fork reality
`ios-sweet` 863 forks, nearly all renamed clones with no changes; the substantive ones are DC28088, limonetexd,
TigerShota, seshubonn and misaghbab (Poco F3). `ios-miatoll` 5 forks (3 empty), `ios-redfin` 7 (2 empty),
`HelioDarwin` 4 (2 untouched) — nothing to gain from any of them. `ios-topaz` 178 forks, but only `ios-sapphire`
(SM6225), `turgayasuk-sketch` and the `asteroids` branch carry real work.

Known junk, do not spend time: `nithinyadavamaraboina-online/IOS-26-Hot` ("iOS 26.5.2 on SD855", no substance);
`HouseOfBalance/ios26-sapphire` (described as Redmi Note 13, targets Xiaomi 15 / SM8750 / arm64e).

### How these were checked, and what was wrong

"**verified**" above means `gh api repos/<r>` was consulted: existence, stars, default branch, last push, and where it
mattered a `git/trees` listing. It does **not** mean the capability claims in a README were reproduced on hardware.

Three corrections to the sweep that produced this section, kept so the same mistakes are not repeated:

- `UniXNU/UniXNU-sm7125-common` **does not exist** — it is `qdizax-w/UniXNU-sm7125-common`.
- `Sho1don/ios-sweet` **does not exist** (404).
- `qu33rl1nk/ios-topaz` has **★1**, not zero.

Two habits worth keeping: a fork count is not a signal (863 forks on `ios-sweet`, almost all empty clones), and a
README claim is not evidence — `limonetexd/ios-sweet-gpu` describes itself as "99% vibe coded", and this family's
GPU/present claims in particular should be treated as unproven until there is a photographed screen.


## Cost of an iteration

| Change | Cost |
| --- | --- |
| Root/userland tweak | ~2 min (`tools/root-variant.sh`, clonefile) |
| Kernel patch | ~8 min CI, then boot and read the live log |
| Rebuild root from the IPSW | ~15 min (only the first time) |
| Flash the root | ~7-10 min, only when the root changed |
