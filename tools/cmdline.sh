#!/bin/bash
# Trim a kernel's boot arguments for an iteration build.
#
#   tools/cmdline.sh BASE|good|fast|gpu|wifi [ARG=VAL ...]   print the merged cmdline
#
# BASE is a file holding a cmdline, the word "good" for the proven 0098 line,
# "fast" for experimental frame pacing, "gpu" for experimental GPU, or
# "wifi" for modem=1 wifi=1. Arguments are
# merged by name because XNU reads duplicate arguments inconsistently.
#
# The good profile avoids high-volume diagnostics for performance comparisons.
# panichalt=1 and periodic UFS log flushing remain enabled for crash capture.
set -euo pipefail
base=${1:?usage: cmdline.sh BASE|good|gpu|wifi [ARG=VAL ...]}
shift

if [ "$base" = good ]; then
	# Normal-performance profile: retain useful crash diagnostics without the
	# high-volume process sampler or kernel printf flood. The panel runs at 60 Hz.
	base_line='debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress ufsroot=iosroot rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_hz=60 sweetpresentwait=1 sweettouchdelay=5 panichalt=1 ufslogsecs=5 sweetfb_noconsole=1 sweetusb=2'
elif [ "$base" = fast ]; then
	# Experimental frame-pacing profile: keep the proven good baseline intact,
	# but remove the CPU presentation fence gate and request 60 Hz scheduling.
	base_line="$("$0" good) sweetpresentwait=0 sweetfb_hz=60 ufslogsecs=5"
elif [ "$base" = gpu ]; then
	base_line="$("$0" good) sweetgpu=9"
elif [ "$base" = wifi ]; then
	base_line="$("$0" good) modem=1 wifi=1"
elif [ -f "$base" ]; then
	base_line=$(cat "$base")
else
	echo "no such cmdline file: $base (or use 'good', 'gpu' or 'wifi')" >&2; exit 1
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

# Wi-Fi autojoin runs inside the modem thread.
if 'wifi_ssid' in cur:
    for radio in ('wifi', 'modem'):
        if cur.get(radio, '0').split('=', 1)[-1] in ('', '0'):
            sys.exit(f"cmdline.sh: wifi_ssid requires {radio} to be enabled. "
                     "Use the 'wifi' base or set modem=1 wifi=1.")
print(' '.join(cur[n] for n in order))
PY
