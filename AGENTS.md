# Working on ios-miatoll

- Read `README.md`, then `NOTES.md` (hardware facts, the engineering log, one entry per patch) and `RESEARCH.md` (where
  each missing feature stands and which reference port already solves it).
- Record each milestone in `NOTES.md`, newest first, with the kernel number or patch, the boot args, exact results and
  what is still open. Keep observations apart from guesses. A new kernel patch is one line in the patch list too.
- Kernel changes go through GitHub Actions: add `xnu/patches/NNNN-*.patch`, push to `main`, `gh workflow run xnu.yml`,
  then `gh run download -n xnu-kernel`. `tools/xnu-cc.py` replays a single compile command from a previous CI log before
  spending a run.
- Device bring-up uses temporary `fastboot boot` images. The iOS root occupies `userdata` (which erases Android's data,
  with the user's explicit OK each time); the bootloader, recovery, modem, persist and the partition backups stay
  untouched. Confirm every destructive step with the user before running it. `RECOVERY.md` restores stock Android.
- Keep out of git: partition dumps, device trees and logs from a phone (serials, IMEI, network names), Apple's files
  (IPSW parts, the root image, shared cache, kernelcache) and firmware pulled from the phone's modem partition.
- Root-image work: never mount HFS+ without `-mountOptions owners`, and never attach the IPSW DMGs without `-owners on`.
  Both silently discard or misread ownership and produce an image that cannot boot; `root-finalize.sh` checks for it.
