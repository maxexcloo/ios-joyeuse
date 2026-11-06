#!/bin/bash
# sudo's askpass helper: a native macOS password dialog.
#
# The root-image build runs in the background, where sudo has no terminal to
# prompt on. SUDO_ASKPASS points here instead, so the password is typed into a
# system dialog rather than echoed into a log.
#
# Prints the password on stdout, as sudo expects.
set -euo pipefail
osascript -e 'display dialog "ios-redmi needs sudo to copy the iOS root filesystem (owners, modes, logd stores, keybag)." with title "iOS root image" default answer "" with hidden answer buttons {"Cancel", "OK"} default button "OK" with icon caution' \
	| sed -n 's/^button returned:OK, text returned:\(.*\)$/\1/p'
