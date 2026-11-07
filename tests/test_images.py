"""Host-side image format checks; no firmware, Apple files or devices needed."""
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import adt
import mkadt
import mkpayload


class Images(unittest.TestCase):
    def test_v2_sections_and_aosp_image_id(self):
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            names = ('kernel', 'ramdisk', 'second', 'recovery_dtbo', 'dtb')
            parts = [bytes([i + 1]) * (4097 + i) for i in range(len(names))]
            args = []
            for name, data in zip(names, parts):
                path = work / name
                path.write_bytes(data)
                args.extend((f'--{name}', str(path)))
            boot = work / 'boot.img'
            subprocess.run([sys.executable, str(ROOT / 'tools/mkbootimg.py'), str(boot), *args],
                           check=True, capture_output=True)
            data = boot.read_bytes()
            expected = hashlib.sha1()
            offset = 4096
            for part in parts:
                expected.update(part)
                expected.update(struct.pack('<I', len(part)))
                self.assertEqual(data[offset:offset + len(part)], part)
                offset += (len(part) + 4095) // 4096 * 4096
            self.assertEqual(data[576:596], expected.digest())
            self.assertEqual(struct.unpack_from('<IQI', data, 1632), (4100, 28672, 1660))
            unpacked = work / 'unpacked'
            subprocess.run([sys.executable, str(ROOT / 'tools/unpack_bootv2.py'), str(boot), str(unpacked)],
                           check=True, capture_output=True)
            for name, part in zip(names, parts):
                self.assertEqual((unpacked / name).read_bytes(), part)

    def test_kernel_arguments_are_not_silently_truncated(self):
        for line in ('x' * 608, 'x\0y'):
            with self.subTest(line_length=len(line)):
                with self.assertRaisesRegex(ValueError, '607 bytes'):
                    mkpayload.build('unused-kernel', 'unused-adt', line)

    def test_hardware_adt_requires_product_input(self):
        with self.assertRaisesRegex(ValueError, '--product'):
            mkadt.build(device='miatoll')
        with tempfile.TemporaryDirectory() as scratch:
            with self.assertRaises(FileNotFoundError):
                mkadt.build(device='miatoll', product=Path(scratch) / 'missing.adt')
        self.assertNotIn('product', [node.name for node in mkadt.build(qemu=True).children])

    def test_hardware_adt_preserves_product_properties(self):
        product = mkadt.node('product', [('product-name', b'Test Product\0')])
        product.props.append(('placeholder', 1, b'not copied'))
        source = mkadt.node('device-tree', children=[product])
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / 'product.adt'
            path.write_bytes(adt.serialize(source))
            root = mkadt.build(device='miatoll', product=path)
        generated = next(node for node in root.children if node.name == 'product')
        self.assertEqual(generated.prop('product-name'), b'Test Product\0')
        self.assertIsNone(generated.prop('placeholder'))

    def test_radio_profile_inherits_boot_arguments(self):
        script = str(ROOT / 'tools/cmdline.sh')
        good = subprocess.check_output(['bash', script, 'good'], text=True).strip()
        wifi = subprocess.check_output(['bash', script, 'wifi'], text=True).strip()
        self.assertEqual(wifi, good + ' modem=1 wifi=1')
        replaced = subprocess.check_output(['bash', script, 'good', 'cpus=1'], text=True).split()
        self.assertIn('cpus=1', replaced)
        self.assertNotIn('cpus=8', replaced)


if __name__ == '__main__':
    unittest.main()
