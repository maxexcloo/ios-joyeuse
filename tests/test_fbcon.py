"""Exercise the framebuffer serial callback that kprintf calls directly."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "xnu/patches/0118-sweet-mute-framebuffer-serial.patch"
HARNESS = r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <vector>
#define FBCON_SCALE 2
#define FBCON_FG 0xffffffffu
#define FBCON_BG 0xff000000u
unsigned char iso_font[256 * 16];
volatile uint32_t *fbcon_base;
uint32_t fbcon_stride = 256, fbcon_cols = 4, fbcon_col, fbcon_row;
int sweet_console_muted;
bool panicking;
bool panic_active() { return panicking; }
void fbcon_newline() { fbcon_col = 0; fbcon_row++; }
// PRODUCTION CALLBACK
int main() {
    std::fill_n(iso_font, sizeof(iso_font), 0xff);
    for (bool muted : {false, true}) {
        for (bool panic : {false, true}) {
            std::vector<uint32_t> pixels(64 * 64, 0x12345678);
            fbcon_base = pixels.data(); fbcon_col = 1; fbcon_row = 0;
            sweet_console_muted = muted; panicking = panic;
            bool draws = true;
#if defined(ARM64_BOARD_CONFIG_SWEET)
            draws = !muted || panic;
#endif
            fbcon_transmit_data('K');
            assert(fbcon_col == (draws ? 2u : 1u));
            for (unsigned y = 0; y < 64; ++y) {
                for (unsigned x = 0; x < 64; ++x) {
                    assert(pixels[y * 64 + x] ==
                        ((draws && x >= 16 && x < 32 && y < 32)
                            ? FBCON_FG : 0x12345678));
                }
            }
            fbcon_transmit_data('\r');
            assert(fbcon_col == (draws ? 0u : 1u));
            fbcon_transmit_data('\n');
            assert(fbcon_row == (draws ? 1u : 0u));
        }
    }
}
"""


class FramebufferSerial(unittest.TestCase):
    def test_direct_kprintf_callback_mute_and_panic(self):
        postimage = "\n".join(
            line[1:]
            for line in PATCH.read_text().splitlines()
            if line.startswith((" ", "+")) and not line.startswith("+++")
        )
        function = re.search(
            r"^static void\nfbcon_transmit_data\([^\n]*\)\n\{.*?^\}",
            postimage,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(function)
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "fbcon.cpp"
            path.write_text(HARNESS.replace("// PRODUCTION CALLBACK", function.group()))
            for sweet in (False, True):
                with self.subTest(sweet=sweet):
                    binary = Path(scratch) / ("sweet" if sweet else "other")
                    flags = ["-DARM64_BOARD_CONFIG_SWEET"] if sweet else []
                    compiled = subprocess.run(
                        [
                            os.environ.get("CXX", "c++"),
                            "-std=c++17",
                            "-Wall",
                            "-Wextra",
                            "-Werror",
                            *flags,
                            str(path),
                            "-o",
                            str(binary),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    result = subprocess.run(
                        [str(binary)], capture_output=True, text=True, check=False
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
