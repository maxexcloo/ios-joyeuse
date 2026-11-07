#!/bin/bash
# Catch the phone's live kernel log over USB Ethernet (macOS side of patches
# 0075-0077). Replaces "film the screen / reboot to OrangeFox": the phone
# streams its console as UDP to the host every 100 ms, from the moment the USB
# device mode comes up.
#
#   tools/livelog.sh [LOGFILE]
#
# Start this BEFORE `fastboot boot`. The phone appears as a CDC-ECM Ethernet
# device; macOS binds AppleUSBECM, so no driver work is needed. The kernel
# (patch 0075/0076) sets the phone to 192.168.7.2/24 by itself; this only adds
# 192.168.7.1/24 on the host and listens on UDP 5140.
#
# Assigning the host address requires sudo.
set -euo pipefail
log=${1:-}
mac=02:00:5e:77:ee:01
iface=""

echo "waiting for the phone's USB Ethernet (host MAC $mac)..." >&2
echo "  (boot the phone now: tools/device.sh boot out/shim-boot-*.img)" >&2
for _ in $(seq 600); do
	# networksetup lists the hardware port and MAC of every interface.
	for i in $(ifconfig -l); do
		if ifconfig "$i" 2>/dev/null | grep -qi "ether $mac"; then iface=$i; break; fi
	done
	[ -n "$iface" ] && break
	sleep 2
done
[ -n "$iface" ] || { echo "no interface with MAC $mac appeared" >&2; exit 1; }

echo "phone on $iface; assigning 192.168.7.1/24 (needs sudo, once)" >&2
if ! ifconfig "$iface" | grep -q "inet 192.168.7.1 "; then
	sudo ifconfig "$iface" inet 192.168.7.1 netmask 255.255.255.0
fi
ifconfig "$iface" | grep -E "inet |ether " >&2

echo "listening on udp/5140 — Ctrl-C to stop" >&2
# Do NOT use `nc -ukl 5140` here. macOS's nc binds the socket to the first
# source address it sees (connect() on a datagram listener) and silently drops
# everything from any other sender: after a panic, a reboot, or the kernel's
# UDP sender being recreated, the capture just stops with no error. That is
# exactly the crash case this script exists for. A plain recvfrom loop takes
# datagrams from any sender, so the log survives a restart.
exec python3 -u - "$log" <<'PY'
import socket, sys, time

path = sys.argv[1] if len(sys.argv) > 1 else ""
if path:
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
out = open(path, "ab", buffering=0) if path else sys.stdout.buffer
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 5140))
last = time.time()
while True:
    s.settimeout(5.0)
    try:
        data, addr = s.recvfrom(65535)
    except socket.timeout:
        # Say so while waiting: a silent 30 s gap is indistinguishable from a
        # hung phone, which is the one thing a live log must never look like.
        if time.time() - last > 30:
            out.write(b"[livelog: no packets for 30 s]\n")
            last = time.time()
        continue
    out.write(data)
    if not data.endswith(b"\n"):
        out.write(b"\n")
    last = time.time()
PY
