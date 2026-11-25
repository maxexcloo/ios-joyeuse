#!/bin/bash
# Provision the shader cache in a mounted iOS16 root, before starting BackBoard.
set -euo pipefail
root=${1:?Usage: prepare-sweet-metal2-cache.sh /mounted/ios-root}
[[ $EUID -eq 0 && $root == /* && $root != / ]]
version=$(cat "$root/System/Library/CoreServices/SystemVersion.plist")
case "$version" in *'<string>20H392</string>'*) ;; *) echo 'Unexpected iOS build' >&2; exit 1 ;; esac

# The mobile process cannot create a directory below root-owned /var/local.
# Keep the parent owned by root and give only BackBoard's cache to mobile.
for rel in private private/var private/var/local private/var/local/m2v-cache private/var/local/m2v-cache/backboardd; do
    [[ ! -L "$root/$rel" ]]
done
cache="$root/private/var/local/m2v-cache"
mkdir -p "$cache/backboardd"
chown 0:0 "$cache"
chmod 0755 "$cache"
chown 501:501 "$cache/backboardd"
chmod 0700 "$cache/backboardd"
echo 'Metal2 BackBoard cache provisioned for uid/gid501.'
