#!/bin/bash
# Trim a kernel's boot arguments for an iteration build.
#
#   tools/cmdline.sh BASE [ARG=VAL ...]        print the merged cmdline
#   tools/cmdline.sh --diff BASE [ARG=VAL ...] show what would change
#
# BASE is a file holding a cmdline, or the word "good" for the proven 0098
# line. Arguments are merged by name, so repeating one replaces it instead of
# appending a duplicate (a real footgun with xnu: the first copy wins for some
# args, the last for others).
#
# Removes debug-only weight while debugging a feature:
#   -enable_kprintf_spam   floods the 4 MiB ring, hides the lines you want
#   keep  panichalt=1      freeze on panic instead of rebooting into Android
#   keep  ufslogsecs=2     flush the log ring every 2 s (crash survives)
set -euo pipefail
diff_mode=0
if [ "${1:-}" = "--diff" ]; then diff_mode=1; shift; fi
base=${1:?usage: cmdline.sh [--diff] BASE|good [ARG=VAL ...]}
shift

if [ "$base" = good ]; then
	# The exact cmdline the 0098 boot used (NOTES.md), minus nothing.
	base_line='debug=0xc serial=3 cpus=8 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_hz=30 sweettouchdelay=5 panichalt=1 ufslogsecs=2 sweetfb_noconsole=1'
elif [ -f "$base" ]; then
	base_line=$(cat "$base")
else
	echo "no such cmdline file: $base (or use 'good')" >&2; exit 1
fi

python3 - "$base_line" "$@" <<'PY'
import sys
line, extra = sys.argv[1], sys.argv[2:]
args = line.split()
# name -> value for merging; a bare flag merges as name=""
def name_of(a):
    return a.split('=', 1)[0]
order, cur = [], {}
for a in args:
    n = name_of(a)
    if n not in cur:
        order.append(n)
    cur[n] = a
for a in extra:
    n = name_of(a)
    if n not in cur:
        order.append(n)
    cur[n] = a
print(' '.join(cur[n] for n in order))
PY
