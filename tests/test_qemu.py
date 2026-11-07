"""The full kernel console must retain diagnostic evidence after screen wrap."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "qemu_sweet", Path(__file__).resolve().parents[1] / "tools/qemu-sweet.py"
)
qemu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qemu)


class Console(unittest.TestCase):
    def test_partial_and_wrapped_console(self):
        self.assertEqual(qemu.console_ring(b"abc\0\0", 0), b"")
        self.assertEqual(qemu.console_ring(b"abc\0\0", 3), b"abc")
        self.assertEqual(qemu.console_ring(b"abcde", 5), b"abcde")
        self.assertEqual(qemu.console_ring(b"fghde", 8), b"defgh")
        self.assertEqual(qemu.console_ring(b"klmij", 13), b"ijklm")
