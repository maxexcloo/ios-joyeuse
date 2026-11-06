#!/bin/bash
# Finish an iOS root image that already holds the copied filesystem.
#
#   sudo root-finalize.sh MOUNTED_ROOT
#
# Run as root (writes root/_logd/mobile-owned files). Idempotent, so it can be
# re-run on an image whose earlier build stopped part-way. Split out of
# mkiosroot-macos.sh so the 11 GiB copy never has to be repeated just to redo
# these steps.
#
# BSD install(1) cannot read from /dev/stdin (GNU install can), so the keybag
# goes through a temporary file.
set -euo pipefail
[[ $# -eq 1 ]] || { sed -n '2,10p' "$0"; exit 2; }
root=${1%/}
[[ -d $root/System/Library/xpc ]] || {
	echo "$root does not look like an iOS root (no System/Library/xpc)" >&2; exit 1; }
[[ $(id -u) -eq 0 ]] || { echo "run as root" >&2; exit 1; }

repo=$(cd "$(dirname "$0")/.." && pwd)

echo "== logd stores, keybag"
# logd checks the owner and mode of its store (else "BUG IN LIBTRACE: Failed to
# migrate directory" and a crash loop), and needs the .migrated marker.
db=$root/private/var/db
install -d -o 272 -g 272 -m 0751 "$db/diagnostics"
install -d -o 272 -g 272 -m 0755 "$db/uuidtext" "$db/diagnostics/timesync"
for d in diagnostics uuidtext diagnostics/timesync; do
	install -o 272 -g 272 -m 0644 /dev/null "$db/$d/.migrated"
done

# Plain-plist system keybag for the built-in AppleKeyStore (no passcode).
install -d -m 0700 -o 0 -g 0 "$root/private/var/keybags"
kb=$(mktemp)
trap 'rm -f "$kb"' EXIT
cat > "$kb" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>KeyBagKeys</key><data>U1dFRVQ=</data></dict></plist>
PLIST
install -m 0600 -o 0 -g 0 "$kb" "$root/private/var/keybags/systembag.kb"
echo "   logd stores + systembag.kb"

echo "== bring-up tweaks (Setup skip, watchdogs, launchd, containers)"
python3 "$repo/tools/sweet-root-tweaks.py" "$root"

# Refuse to continue on a noowners mount: every chown above would have been
# dropped without an error, and the image would boot into a wall of EACCES.
probe=$root/.ios-redmi-owner-probe
touch "$probe"; chown 272:272 "$probe"
if [ "$(stat -f %u "$probe")" != 272 ]; then
	rm -f "$probe"
	echo "ERROR: $root is mounted with noowners; ownership cannot be set." >&2
	echo "       remount with -mountOptions owners and re-run." >&2
	exit 1
fi
rm -f "$probe"

echo "== dyld shared cache at the path ignition_level=1 looks in"
# On a device /private/preboot is its own volume holding the cryptexes, and
# dyld finds the shared cache through the cryptex. Collapsed into one volume
# that path still exists, so the cache must ALSO be hard-linked at the plain
# /System/Library/Caches/com.apple.dyld path that ignition level 1 probes.
# Hard links on one volume cost no extra space.
dsc=$root/private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld
dst=$root/System/Library/Caches/com.apple.dyld
if [ -d "$dsc" ]; then
	mkdir -p "$dst"
	n=0
	for f in "$dsc"/*; do
		[ -e "$f" ] || continue
		ln -f "$f" "$dst/${f##*/}" && n=$((n + 1))
	done
	echo "   $n shared-cache files linked"
else
	echo "   WARNING: no $dsc, dyld will not find the shared cache" >&2
fi
