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
# Unlike the upstream Linux script this needs no sudo and no iproute2.
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
# -k: keep listening across the phone's sender restarting.
if [ -n "$log" ]; then
	nc -ukl 5140 | tee -a "$log"
else
	nc -ukl 5140
fi
