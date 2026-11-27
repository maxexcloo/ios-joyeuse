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
import hashlib
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import uuid

MOBILE = 501
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JB_CACHE = os.path.join(ROOT_DIR, "cache/jb")
JB_HASHES = {
    "bootstrap-ssh-iphoneos-arm.tar.zst": "d1a619570f14fd074d857f5b30ee921a1a6c692f81c646cdcbafa5996a41f8bd",
    "ellekit_1.2_iphoneos-arm64.deb": "e21dc91bdc1be193dc915daecfff45256239b4fe583a36861e662ab1f43906dc",
    "org.coolstar.sileo_2.5.1_iphoneos-arm64.deb": "8e3c90e5a7d32f4ca207a0ac30d3cfa8a13dca86a2b4e11cb3f9e5c68d7bc97a",
    "procursus-memo.gpg": "10864afeaff3151d5bee4444335f33fb1042904e4bbb757f8a76033e6e2692bb",
}
PROCursus_FINGERPRINT = "C59F3798A305ADD7E7E6C7256430292CF9551B0E"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def copy_tree_contents(src, dst):
    os.makedirs(dst, exist_ok=True)
    for entry in os.scandir(src):
        source, target = entry.path, os.path.join(dst, entry.name)
        if entry.is_symlink():
            if os.path.lexists(target):
                if os.path.isdir(target) and not os.path.islink(target):
                    shutil.rmtree(target)
                else:
                    os.unlink(target)
            os.symlink(os.readlink(source), target)
        elif entry.is_dir(follow_symlinks=False):
            os.makedirs(target, exist_ok=True)
            copy_tree_contents(source, target)
            st = os.stat(source, follow_symlinks=False)
            os.chown(target, st.st_uid, st.st_gid)
            os.chmod(target, st.st_mode & 0o7777)
        else:
            shutil.copy2(source, target, follow_symlinks=False)
            st = os.stat(source, follow_symlinks=False)
            os.chown(target, st.st_uid, st.st_gid, follow_symlinks=False)


def install_rootless(root):
    if os.geteuid() != 0:
        raise RuntimeError(
            "rootless files require root and an owners-enabled HFS+ mount"
        )
    bsdtar, gpg = shutil.which("bsdtar"), shutil.which("gpg")
    if not bsdtar or not gpg:
        raise RuntimeError(
            "bsdtar and gpg are required to install verified rootless artifacts"
        )
    artifacts = {}
    for name, expected in JB_HASHES.items():
        path = os.path.join(JB_CACHE, name)
        if not os.path.isfile(path) or sha256(path) != expected:
            raise RuntimeError("missing or invalid cached artifact: " + path)
        artifacts[name] = path
    bootstrap_name = "bootstrap-ssh-iphoneos-arm.tar.zst"
    sig = artifacts[bootstrap_name] + ".asc"
    if not os.path.isfile(sig):
        raise RuntimeError("missing Procursus bootstrap detached signature: " + sig)
    with tempfile.TemporaryDirectory(prefix="sweet-jb-") as tmp:
        gh = os.path.join(tmp, "gnupg")
        os.mkdir(gh, 0o700)
        subprocess.run(
            [
                gpg,
                "--batch",
                "--homedir",
                gh,
                "--import",
                artifacts["procursus-memo.gpg"],
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        fingerprints = subprocess.check_output(
            [gpg, "--batch", "--homedir", gh, "--with-colons", "--fingerprint"],
            text=True,
        )
        if PROCursus_FINGERPRINT not in fingerprints:
            raise RuntimeError("unexpected Procursus signing-key fingerprint")
        subprocess.run(
            [
                gpg,
                "--batch",
                "--homedir",
                gh,
                "--verify",
                sig,
                artifacts[bootstrap_name],
            ],
            check=True,
        )
        jb = os.path.join(root, "private/var/jb")
        os.makedirs(jb, exist_ok=True)
        subprocess.run(
            [bsdtar, "-xpf", artifacts[bootstrap_name], "-C", jb], check=True
        )
        # Procursus bootstrap archives preserve iOS's /private/etc and /private/var
        # layout. Make the conventional paths resolve inside the rootless prefix.
        for public, private in (("etc", "private/etc"), ("var", "private/var")):
            public_path = os.path.join(jb, public)
            if not os.path.lexists(public_path):
                os.symlink(private, public_path)
            elif not os.path.islink(public_path) or os.readlink(public_path) != private:
                raise RuntimeError(
                    "unexpected Procursus path in bootstrap: " + public_path
                )
        for name in (
            "ellekit_1.2_iphoneos-arm64.deb",
            "org.coolstar.sileo_2.5.1_iphoneos-arm64.deb",
        ):
            stage = os.path.join(tmp, name)
            os.mkdir(stage)
            data = subprocess.check_output(
                [bsdtar, "-xOf", artifacts[name], "data.tar.xz"]
            )
            subprocess.run([bsdtar, "-xpf", "-", "-C", stage], input=data, check=True)
            payload = os.path.join(stage, "var/jb")
            if not os.path.isdir(payload):
                raise RuntimeError("unexpected rootless .deb layout: " + name)
            copy_tree_contents(payload, jb)
    configure_rootless_ssh(root)


def configure_rootless_ssh(root):
    jb = os.path.join(root, "private/var/jb")
    sshd = os.path.join(jb, "usr/sbin/sshd")
    if not os.path.isfile(sshd):
        raise RuntimeError(
            "SSH-enabled Procursus archive did not contain /usr/sbin/sshd"
        )
    keyfile = "/home/vsc/.ssh/id_ed25519.pub"
    with open(keyfile, encoding="utf-8") as f:
        fields = f.read().strip().split()
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise RuntimeError("expected an ssh-ed25519 public key at " + keyfile)
    ssh_dir = os.path.join(root, "private/var/root/.ssh")
    os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
    os.chown(ssh_dir, 0, 0)
    os.chmod(ssh_dir, 0o700)
    authorized = os.path.join(ssh_dir, "authorized_keys")
    with open(authorized, "w", encoding="utf-8") as f:
        f.write(" ".join(fields) + "\n")
    os.chown(authorized, 0, 0)
    os.chmod(authorized, 0o600)

    ssh_dir = os.path.join(jb, "etc/ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    host_key = os.path.join(ssh_dir, "ssh_host_ed25519_key")
    if not os.path.exists(host_key):
        keygen = shutil.which("ssh-keygen")
        if not keygen:
            raise RuntimeError("ssh-keygen on the build host is required")
        with tempfile.TemporaryDirectory(prefix="sweet-ssh-key-") as tmp:
            temporary_key = os.path.join(tmp, "ssh_host_ed25519_key")
            subprocess.run(
                [keygen, "-q", "-t", "ed25519", "-N", "", "-f", temporary_key],
                check=True,
            )
            shutil.copyfile(temporary_key, host_key)
            shutil.copyfile(temporary_key + ".pub", host_key + ".pub")
    os.chown(host_key, 0, 0)
    os.chmod(host_key, 0o600)
    os.chown(host_key + ".pub", 0, 0)
    os.chmod(host_key + ".pub", 0o644)
    config = os.path.join(ssh_dir, "sshd_config")
    settings = [
        "Port 22",
        "ListenAddress 192.168.7.2",
        "HostKey /var/jb/etc/ssh/ssh_host_ed25519_key",
        "AuthorizedKeysFile /private/var/root/.ssh/authorized_keys",
        "PermitRootLogin prohibit-password",
        "PubkeyAuthentication yes",
        "PasswordAuthentication no",
        "KbdInteractiveAuthentication no",
        "UsePAM no",
        "UseDNS no",
        "PidFile /private/var/run/sshd.pid",
        "Subsystem sftp /var/jb/usr/libexec/sftp-server",
    ]
    with open(config, "w", encoding="utf-8") as f:
        f.write("\n".join(settings) + "\n")
    os.chown(config, 0, 0)
    os.chmod(config, 0o600)

    profile = os.path.join(jb, "etc/profile")
    path_line = 'PATH="/var/jb/usr/bin:/var/jb/bin:/var/jb/usr/sbin:/var/jb/sbin:$PATH"; export PATH'
    old = ""
    if os.path.isfile(profile):
        with open(profile, encoding="utf-8") as f:
            old = f.read()
    if path_line not in old:
        with open(profile, "a", encoding="utf-8") as f:
            f.write("\n" + path_line + "\n")
    os.chown(profile, 0, 0)
    os.chmod(profile, 0o644)

    app = os.path.join(root, "Applications/Sileo.app")
    os.makedirs(os.path.dirname(app), exist_ok=True)
    link = "/var/jb/Applications/Sileo.app"
    if not os.path.lexists(app):
        os.symlink(link, app)
    elif not os.path.islink(app) or os.readlink(app) != link:
        raise RuntimeError("refusing to overwrite existing Applications/Sileo.app")
    daemon = {
        "Label": "org.procursus.sshd.usb",
        "ProgramArguments": [
            "/var/jb/usr/sbin/sshd",
            "-D",
            "-e",
            "-f",
            "/var/jb/etc/ssh/sshd_config",
        ],
        "RunAtLoad": True,
        "KeepAlive": {"NetworkState": True},
        "StandardOutPath": "/private/var/log/sweet-ssh.log",
        "StandardErrorPath": "/private/var/log/sweet-ssh.log",
    }
    # iOS 16's launchd_unsecure_cache=1 can skip third-party plist discovery
    # under /Library/LaunchDaemons. Register the job in launchd's merged system
    # database instead; unlike a plist on disk this is consumed at boot.
    launchd_path = os.path.join(root, "System/Library/xpc/launchd.plist")
    launchd_plist = load(launchd_path)
    jobs = launchd_plist.setdefault("LaunchDaemons", {})
    jobs["/System/Library/LaunchDaemons/org.procursus.sshd.usb.plist"] = daemon
    st = os.stat(launchd_path)
    save(launchd_path, launchd_plist, st.st_uid, st.st_gid, st.st_mode & 0o7777)
    print(
        "rootless: Procursus, ElleKit, Sileo and USB key-only SSH registered in launchd"
    )


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
    voicemail_disabled = 0
    for job in jobs.values():
        if job.get("Label") == "com.apple.voicemail.vmd":
            job["Disabled"] = True
            job["RunAtLoad"] = False
            voicemail_disabled += 1
        if "_PanicOnCrash" in job:
            job["_PanicOnCrasX"] = job.pop("_PanicOnCrash")
            renamed += 1
    removed = [k for k, j in jobs.items() if j.get("Label") == "com.apple.CommCenter"]
    for k in removed:
        del jobs[k]
    save(path, plist, st.st_uid, st.st_gid, st.st_mode & 0o7777)
    print(
        f"launchd.plist: {renamed} _PanicOnCrash renamed, {len(removed)} CommCenter jobs removed, "
        f"{voicemail_disabled} voicemail vmd jobs disabled"
    )


def user_temporary_directories(root):
    # libsystem_coreservices falls back to /var/tmp when TMPDIR is unset.
    # libsystem_c's confstr fallback requires the selected temp directory to
    # pass access(W_OK); /var/tmp must therefore be the standard sticky,
    # world-writable directory so mobile (uid 501) and system daemons can use it.
    tmp = os.path.join(root, "private/var/tmp")
    if not os.path.isdir(tmp):
        os.makedirs(tmp, exist_ok=True)
        print("mkdir", tmp)
    st = os.stat(tmp)
    if (st.st_uid, st.st_gid, st.st_mode & 0o7777) != (0, 0, 0o1777):
        os.chown(tmp, 0, 0)
        os.chmod(tmp, 0o1777)
        print("chmod 1777", tmp)

    # Keep the system-owned randomized-directory namespace available for
    # per-user DARWIN_USER_* directories created by the OS at runtime.
    base = os.path.join(root, "private/var/folders")
    zz = os.path.join(base, "zz")
    if not os.path.isdir(zz):
        os.makedirs(zz, exist_ok=True)
    st = os.stat(zz)
    if (st.st_uid, st.st_gid, st.st_mode & 0o7777) != (0, 0, 0o755):
        os.chown(zz, 0, 0)
        os.chmod(zz, 0o755)
        print("chmod 755", zz)


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


def activation(root, build, version):
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
            "-BuildVersion": build,
            "-ProductVersion": version,
            "-DataMigrationCompleted": True,
            "-PreSydroDataMigrationCompleted": True,
        },
        MOBILE,
        MOBILE,
        0o600,
    )
    print("data ark", d)


def audio(root):
    # These AudioUnit extensions repeatedly abort with SIGABRT on this device;
    # CoreAudio's component scanner respawns them until the corpse limit is hit.
    # Remove only the matching bundles from component discovery, preserving
    # them under a sibling disabled directory for easy restoration.
    tts_names = {"SiriTTSSynthesizerAU", "KonaSynthesizer", "MacinTalkAUSP"}
    component_roots = (
        os.path.join(root, "System/Library/Components"),
        os.path.join(root, "System/Library/Audio/Plug-Ins/Components"),
        os.path.join(root, "Library/Audio/Plug-Ins/Components"),
    )
    for component_root in component_roots:
        if not os.path.isdir(component_root):
            continue
        for current, dirs, files in os.walk(component_root):
            if "Info.plist" not in files:
                continue
            info = os.path.join(current, "Info.plist")
            try:
                bundle = load(info)
            except (OSError, plistlib.InvalidFileException):
                continue
            names = {
                bundle.get(key)
                for key in ("CFBundleExecutable", "CFBundleName", "CFBundleIdentifier")
            }
            names.update(
                bundle.get("AudioComponents", [{}])[0].get(key)
                for key in ("name", "type")
                if bundle.get("AudioComponents")
            )
            if not (names & tts_names):
                continue
            disabled_root = component_root + ".disabled"
            os.makedirs(disabled_root, exist_ok=True)
            target = os.path.join(
                disabled_root, os.path.relpath(current, component_root)
            )
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if not os.path.exists(target):
                shutil.move(current, target)
                print("audio component disabled", os.path.relpath(current, root))
            dirs[:] = []

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


def managed_configuration(root):
    # profiled's own launchd KeepAlive PathState probes are signals; seed the
    # parent directory, not the marker files, so it can publish its XPC service
    # and decide whether work is outstanding itself.
    profiles = os.path.join(
        root, "private/var/mobile/Library/UserConfigurationProfiles"
    )
    if not os.path.isdir(profiles):
        os.makedirs(profiles, exist_ok=True)
        os.chown(profiles, MOBILE, MOBILE)
        os.chmod(profiles, 0o700)
        print("mkdir", profiles)


def posterboard_and_tcc(root):
    tcc = os.path.join(root, "private/var/mobile/Library/TCC")
    if not os.path.isdir(tcc):
        os.makedirs(tcc, exist_ok=True)
        os.chown(tcc, MOBILE, MOBILE)
        os.chmod(tcc, 0o700)
        print("mkdir", tcc)

    angel_path = os.path.join(
        root, "System/Library/LaunchAngels/com.apple.PosterBoard.plist"
    )
    ld_path = os.path.join(root, "System/Library/xpc/launchd.plist")
    if os.path.exists(angel_path) and os.path.exists(ld_path):
        st = os.stat(ld_path)
        plist = load(ld_path)
        jobs = plist["LaunchDaemons"]
        # PosterBoard is currently killed for exceeding its per-process Jetsam
        # limit and immediately re-spawns in a crash loop. Until its footprint
        # is understood, disable both LaunchAngel and merged daemon entries.
        # Do not guess a larger memory limit from the exit reason alone.
        changed = 0
        for existing in jobs.values():
            if existing.get("Label") == "com.apple.PosterBoard":
                existing["RunAtLoad"] = False
                existing["Disabled"] = True
                existing["KeepAlive"] = False
                changed += 1
        job = load(angel_path)
        job["RunAtLoad"] = False
        job["Disabled"] = True
        job["KeepAlive"] = False
        save(
            angel_path,
            job,
            os.stat(angel_path).st_uid,
            os.stat(angel_path).st_gid,
            os.stat(angel_path).st_mode & 0o7777,
        )
        # Keep the registration disabled in the merged launchd database too.
        key = "/System/Library/LaunchDaemons/com.apple.PosterBoard.plist"
        job["MachServices"] = {"com.apple.posterboardservices.services": True}
        jobs[key] = job
        save(ld_path, plist, st.st_uid, st.st_gid, st.st_mode & 0o7777)
        print(
            f"launchd.plist: disabled PosterBoard LaunchAngel and {changed} merged job(s) to stop Jetsam restart loop"
        )


def main():
    if len(sys.argv) != 2 or not os.path.isdir(
        os.path.join(sys.argv[1], "System/Library/xpc")
    ):
        sys.exit(__doc__)
    root = sys.argv[1]
    system_version = load(
        os.path.join(root, "System/Library/CoreServices/SystemVersion.plist")
    )
    build = system_version["ProductBuildVersion"]
    version = system_version["ProductVersion"]
    launchd(root)
    install_rootless(root)
    managed_configuration(root)
    posterboard_and_tcc(root)
    user_temporary_directories(root)
    containers(root)
    activation(root, build, version)
    audio(root)
    capabilities(root)
    network(root)
    merge_pref(
        root,
        "com.apple.migration",
        {
            "LastSystemVersion": build,
            "DMUserDataDisposition": {
                "SyntheticDidUpgrade": False,
                "buildVersion": build,
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
