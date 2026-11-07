"""Host-side image format checks; no firmware, Apple files or devices needed."""

import hashlib
import importlib.util
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import adt
import mkadt
import mkpayload

spec = importlib.util.spec_from_file_location(
    "root_tweaks", ROOT / "tools/sweet-root-tweaks.py"
)
root_tweaks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(root_tweaks)


class Images(unittest.TestCase):
    def test_v2_sections_and_aosp_image_id(self):
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            names = ("kernel", "ramdisk", "second", "recovery_dtbo", "dtb")
            parts = [bytes([i + 1]) * (4097 + i) for i in range(len(names))]
            args = []
            for name, data in zip(names, parts):
                path = work / name
                path.write_bytes(data)
                args.extend((f"--{name}", str(path)))
            boot = work / "boot.img"
            subprocess.run(
                [sys.executable, str(ROOT / "tools/mkbootimg.py"), str(boot), *args],
                check=True,
                capture_output=True,
            )
            data = boot.read_bytes()
            expected = hashlib.sha1()
            offset = 4096
            for part in parts:
                expected.update(part)
                expected.update(struct.pack("<I", len(part)))
                self.assertEqual(data[offset : offset + len(part)], part)
                offset += (len(part) + 4095) // 4096 * 4096
            self.assertEqual(data[576:596], expected.digest())
            self.assertEqual(
                struct.unpack_from("<IQI", data, 1632), (4100, 28672, 1660)
            )
            unpacked = work / "unpacked"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/unpack_bootv2.py"),
                    str(boot),
                    str(unpacked),
                ],
                check=True,
                capture_output=True,
            )
            for name, part in zip(names, parts):
                self.assertEqual((unpacked / name).read_bytes(), part)

    def test_kernel_arguments_are_not_silently_truncated(self):
        for line in ("x" * 608, "x\0y"):
            with (
                self.subTest(line_length=len(line)),
                self.assertRaisesRegex(ValueError, "607 bytes"),
            ):
                mkpayload.build("unused-kernel", "unused-adt", line)

    def test_hardware_adt_requires_product_input(self):
        with self.assertRaisesRegex(ValueError, "--product"):
            mkadt.build(device="miatoll")
        with (
            tempfile.TemporaryDirectory() as scratch,
            self.assertRaises(FileNotFoundError),
        ):
            mkadt.build(device="miatoll", product=Path(scratch) / "missing.adt")
        diagnostic = mkadt.build(qemu=True)
        self.assertNotIn("product", [node.name for node in diagnostic.children])
        chosen = next(node for node in diagnostic.children if node.name == "chosen")
        self.assertEqual(chosen.prop("sweet-qemu"), struct.pack("<I", 1))
        addresses = [
            chosen.prop("mac-address-" + name)
            for name in ("bluetooth0", "ethernet0", "wifi0")
        ]
        self.assertEqual(len(set(addresses)), 3)
        for address in addresses:
            self.assertEqual(len(address), 6)
            self.assertEqual(address[0] & 3, 2)  # local, unicast virtual identity

    def test_hardware_adt_preserves_product_properties(self):
        product = mkadt.node("product", [("product-name", b"Test Product\0")])
        product.props.append(("placeholder", 1, b"not copied"))
        source = mkadt.node("device-tree", children=[product])
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "product.adt"
            path.write_bytes(adt.serialize(source))
            with self.assertRaisesRegex(ValueError, "--touch-firmware"):
                mkadt.build(device="miatoll", product=path)
            firmware = Path(scratch) / "touch.bin"
            firmware.write_bytes(b"device-supplied touch firmware")
            root = mkadt.build(device="miatoll", product=path, touch_firmware=firmware)
        generated = next(node for node in root.children if node.name == "product")
        self.assertEqual(generated.prop("product-name"), b"Test Product\0")
        self.assertIsNone(generated.prop("placeholder"))
        chosen = next(node for node in root.children if node.name == "chosen")
        self.assertEqual(
            chosen.prop("focaltech-firmware"), b"device-supplied touch firmware"
        )
        self.assertIsNone(chosen.prop("sweet-qemu"))
        for name in ("bluetooth0", "ethernet0", "wifi0"):
            self.assertIsNone(chosen.prop("mac-address-" + name))

    def test_root_preparation_invalidates_cached_hardware_answers(self):
        with tempfile.TemporaryDirectory() as scratch:
            cache = (
                Path(scratch)
                / "private/var/containers/Shared/SystemGroup/example/Library/Caches"
            )
            cache.mkdir(parents=True)
            stale = cache / "com.apple.MobileGestalt.plist"
            stale.write_bytes(b"stale camera and flash capabilities")
            unrelated = cache / "other.plist"
            unrelated.write_bytes(b"keep")
            root_tweaks.capabilities(scratch)
            self.assertFalse(stale.exists())
            self.assertEqual(unrelated.read_bytes(), b"keep")
            root_tweaks.capabilities(scratch)

    def test_network_service_is_published_in_current_set(self):
        with (
            tempfile.TemporaryDirectory() as scratch,
            mock.patch.object(root_tweaks.os, "chown"),
        ):
            path = (
                Path(scratch)
                / "Library/Preferences/SystemConfiguration/preferences.plist"
            )
            path.parent.mkdir(parents=True)
            existing = {
                "CurrentSet": "/Sets/EXISTING",
                "NetworkServices": {"USB": {"Interface": {"DeviceName": "ue0"}}},
                "Sets": {
                    "EXISTING": {
                        "Network": {
                            "Global": {"IPv4": {"ServiceOrder": ["USB"]}},
                            "Service": {"USB": {"__LINK__": "/NetworkServices/USB"}},
                        }
                    }
                },
                "Version": 1,
            }
            path.write_bytes(plistlib.dumps(existing))
            root_tweaks.network(scratch)
            data = plistlib.loads(path.read_bytes())
            service = next(k for k in data["NetworkServices"] if k != "USB")
            self.assertEqual(
                data["NetworkServices"]["USB"], existing["NetworkServices"]["USB"]
            )
            wlan = data["NetworkServices"][service]
            self.assertEqual(wlan["Interface"]["DeviceName"], "en0")
            self.assertEqual(wlan["Interface"]["Type"], "Ethernet")
            self.assertEqual(wlan["IPv4"], {"ConfigMethod": "DHCP"})
            network = data["Sets"]["EXISTING"]["Network"]
            self.assertEqual(
                network["Service"][service], {"__LINK__": "/NetworkServices/" + service}
            )
            self.assertEqual(
                network["Global"]["IPv4"]["ServiceOrder"], ["USB", service]
            )
            before = path.read_bytes()
            root_tweaks.network(scratch)
            self.assertEqual(path.read_bytes(), before)

    def test_network_service_seeds_empty_root(self):
        with (
            tempfile.TemporaryDirectory() as scratch,
            mock.patch.object(root_tweaks.os, "chown") as chown,
        ):
            root_tweaks.network(scratch)
            path = (
                Path(scratch)
                / "Library/Preferences/SystemConfiguration/preferences.plist"
            )
            data = plistlib.loads(path.read_bytes())
            current = data["Sets"][data["CurrentSet"].split("/")[-1]]
            service = current["Network"]["Global"]["IPv4"]["ServiceOrder"][0]
            self.assertEqual(
                current["Network"]["Service"][service]["__LINK__"],
                "/NetworkServices/" + service,
            )
            self.assertEqual(
                data["NetworkServices"][service]["IPv6"], {"ConfigMethod": "Automatic"}
            )
            chown.assert_called_once_with(str(path), 0, 0)

    def test_radio_profile_inherits_boot_arguments(self):
        script = str(ROOT / "tools/cmdline.sh")
        good = subprocess.check_output(["bash", script, "good"], text=True).strip()
        wifi = subprocess.check_output(["bash", script, "wifi"], text=True).strip()
        self.assertEqual(wifi, good + " modem=1 wifi=1")
        replaced = subprocess.check_output(
            ["bash", script, "good", "cpus=1"], text=True
        ).split()
        self.assertIn("cpus=1", replaced)
        self.assertNotIn("cpus=8", replaced)


if __name__ == "__main__":
    unittest.main()
