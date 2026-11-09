#!/usr/bin/env python3
"""Apply the SWEET bring-up changes to an iOS root made by tools/mkiosroot-macos.sh.

  sudo sweet-root-tweaks.py MOUNTED_ROOT

MOUNTED_ROOT is the HFS+ image mounted read-write. Run as root (it writes
root/mobile owned files). Idempotent. tools/root-finalize.sh runs it; these
are the changes that reached the home screen in the parent port:

  launchd.plist   _PanicOnCrash -> _PanicOnCrasX (a crashing daemon must not
                  panic the system); CommCenter jobs removed (no baseband: it
                  crash-loops and Setup blocks on its CoreTelephony XPC)
  containers      /private/var/containers/{Bundle,Data/System,Shared/SystemGroup,Temp}
                  (on iOS they live on the data volume)
  migration       LastSystemVersion so DataMigration does not run for an hour
                  on every boot
  audio           VirtualAudio HAL plug-in disabled (mediaserverd crash)
  MediaToolbox    StartRecorderServer=false (camera filter prewarm calls a
                  NULL OpenGL function without a GPU -> mediaserverd crash loop)
  SpringBoard     BKNoWatchdogs (one slow CPU path, no scene-create watchdog
                  kills), no cloud-configuration UI
  Setup           skipped: SetupDone, SetupFinishedAllSteps, SetupVersion 11,
                  mini-buddy flags off
  activation      mobileactivationd data ark seeded; the actual Activated state
                  comes from its Hactivation branch, selected by the /chosen
                  security-status properties in tools/mkadt.py
"""

import glob
import os
import plistlib
import shutil
import sys
import uuid

BUILD, VERSION = "20H392", "16.7.16"
MOBILE = 501


def load(path):
    with open(path, "rb") as f:
        return plistlib.load(f)


def save(path, data, uid, gid, mode, fmt=plistlib.FMT_BINARY):
    with open(path, "wb") as f:
        plistlib.dump(data, f, fmt=fmt)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def merge_pref(root, name, values):
    """Merge keys into /var/mobile/Library/Preferences/NAME.plist (mobile, 0600)."""
    path = os.path.join(root, "private/var/mobile/Library/Preferences", name + ".plist")
    data = load(path) if os.path.exists(path) else {}
    data.update(values)
    save(path, data, MOBILE, MOBILE, 0o600)
    print("pref", name, sorted(values))


def launchd(root):
    path = os.path.join(root, "System/Library/xpc/launchd.plist")
    st = os.stat(path)
    plist = load(path)
    jobs = plist["LaunchDaemons"]
    renamed = 0
    for job in jobs.values():
        if "_PanicOnCrash" in job:
            job["_PanicOnCrasX"] = job.pop("_PanicOnCrash")
            renamed += 1
    removed = [k for k, j in jobs.items() if j.get("Label") == "com.apple.CommCenter"]
    for k in removed:
        del jobs[k]
    save(path, plist, st.st_uid, st.st_gid, st.st_mode & 0o7777)
    print(
        f"launchd.plist: {renamed} _PanicOnCrash renamed, {len(removed)} CommCenter jobs removed"
    )


def containers(root):
    base = os.path.join(root, "private/var/containers")
    for sub, uid in (
        ("Bundle", 33),
        ("Data/System", 0),
        ("Shared/SystemGroup", 0),
        ("Temp", 0),
    ):
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            os.makedirs(d)
            os.chown(d, uid, uid)
            os.chmod(d, 0o755)
            print("mkdir", d)


def find_container(root, kind, identifier):
    for meta in glob.glob(
        os.path.join(
            root,
            "private/var/containers",
            kind,
            "*",
            ".com.apple.mobile_container_manager.metadata.plist",
        )
    ):
        if load(meta).get("MCMMetadataIdentifier") == identifier:
            return os.path.dirname(meta)
    return None


def activation(root):
    c = find_container(root, "Data/System", "com.apple.mobileactivationd")
    if c is None:
        print(
            "warning: no mobileactivationd system container in the image; skipped data ark"
        )
        return
    d = os.path.join(c, "Library/internal")
    os.makedirs(d, exist_ok=True)
    os.chown(d, MOBILE, MOBILE)
    os.chmod(d, 0o755)
    save(
        os.path.join(d, "data_ark.plist"),
        {
            "-ActivationState": "Activated",
            "-BrickState": False,
            "-BuildVersion": BUILD,
            "-ProductVersion": VERSION,
            "-DataMigrationCompleted": True,
            "-PreSydroDataMigrationCompleted": True,
        },
        MOBILE,
        MOBILE,
        0o600,
    )
    print("data ark", d)


def audio(root):
    src = os.path.join(root, "Library/Audio/Plug-Ins/HAL/VirtualAudio.plugin")
    dst_dir = os.path.join(root, "Library/Audio/Plug-Ins/HAL.disabled")
    if os.path.exists(src):
        os.makedirs(dst_dir, exist_ok=True)
        shutil.move(src, dst_dir)
        print("VirtualAudio.plugin disabled")
    for conf in glob.glob(
        os.path.join(
            root,
            "System/Library/Frameworks/MediaToolbox.framework/*/SubServerConfiguration.plist",
        )
    ):
        st = os.stat(conf)
        data = load(conf)
        data["StartRecorderServer"] = False
        save(conf, data, st.st_uid, st.st_gid, st.st_mode & 0o7777, plistlib.FMT_XML)
        print("StartRecorderServer off", os.path.relpath(conf, root))


def capabilities(root):
    # Stale camera/flash answers can block SpringBoard on unavailable media XPC.
    pattern = os.path.join(
        root,
        "private/var/containers/Shared/SystemGroup",
        "*",
        "Library/Caches/com.apple.MobileGestalt.plist",
    )
    for path in glob.glob(pattern):
        os.unlink(path)
        print("MobileGestalt: hardware capabilities will rebuild at next boot")


def network(root):
    # Kernel-only en0 has no IOEthernetInterface for InterfaceNamer to configure.
    # prefsmon publishes this service; IPConfiguration matches its BSD name.
    path = os.path.join(
        root, "Library/Preferences/SystemConfiguration/preferences.plist"
    )
    data = load(path) if os.path.exists(path) else {"Version": 1}
    services = data.setdefault("NetworkServices", {})
    if any(
        s.get("Interface", {}).get("DeviceName") == "en0" for s in services.values()
    ):
        print("network: preserving existing en0 service")
        return
    service = str(uuid.uuid4()).upper()
    name = "Joyeuse WLAN"
    services[service] = {
        "IPv4": {"ConfigMethod": "DHCP"},
        "IPv6": {"ConfigMethod": "Automatic"},
        "Interface": {
            "DeviceName": "en0",
            "Hardware": "Ethernet",
            "Type": "Ethernet",
            "UserDefinedName": name,
        },
        "UserDefinedName": name,
    }
    if "CurrentSet" not in data:
        data["CurrentSet"] = "/Sets/" + str(uuid.uuid4()).upper()
    set_id = data["CurrentSet"].split("/")[-1]
    current = data.setdefault("Sets", {}).setdefault(
        set_id, {"UserDefinedName": "Automatic"}
    )
    net = current.setdefault("Network", {})
    net.setdefault("Service", {})[service] = {"__LINK__": "/NetworkServices/" + service}
    order = (
        net.setdefault("Global", {})
        .setdefault("IPv4", {})
        .setdefault("ServiceOrder", [])
    )
    order.append(service)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    save(path, data, 0, 0, 0o644)
    print("network: en0 DHCP service prepared (radio still requires wifi boot profile)")


def main():
    if len(sys.argv) != 2 or not os.path.isdir(
        os.path.join(sys.argv[1], "System/Library/xpc")
    ):
        sys.exit(__doc__)
    root = sys.argv[1]
    launchd(root)
    containers(root)
    activation(root)
    audio(root)
    capabilities(root)
    network(root)
    merge_pref(
        root,
        "com.apple.migration",
        {
            "LastSystemVersion": BUILD,
            "DMUserDataDisposition": {
                "SyntheticDidUpgrade": False,
                "buildVersion": BUILD,
            },
        },
    )
    merge_pref(
        root,
        "com.apple.springboard",
        {
            "BKNoWatchdogs": True,
            "FBLaunchWatchdogExceptions": {"com.apple.purplebuddy": 100.0},
            "MCForceShowCloudConfigurationUI": False,
        },
    )
    merge_pref(
        root,
        "com.apple.purplebuddy",
        {
            "SetupDone": True,
            "SetupFinishedAllSteps": True,
            "SetupVersion": 11,
            "daemonizeNeedsToRun": False,
        },
    )
    merge_pref(
        root,
        "com.apple.purplebuddy.notbackedup",
        {
            k: False
            for k in (
                "ShouldRunDiagnosticsMiniBuddy",
                "ShouldRunHSA2MiniBuddy",
                "ShouldRunKeychainSyncMiniBuddy",
                "ShouldRunMesaMiniBuddy",
                "ShouldRunPaymentMiniBuddy",
                "ShouldRunStandardMiniBuddy",
                "SilentICDPUpgrade",
            )
        },
    )
    merge_pref(
        root,
        "com.apple.managedconfiguration.notbackedup",
        {"LockdownActivationIndicatesCloudConfigurationAvailable": False},
    )


if __name__ == "__main__":
    main()
