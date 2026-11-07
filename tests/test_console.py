"""Exercise the changed unbuffered console function from its patch postimage."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "xnu/patches/0114-sweet-mute-unbuffered-console.patch"
HARNESS = r"""
#include <cassert>
#include <string>
std::string persistent, displayed;
int sweet_console_muted;
bool panicking;
bool panic_active() { return panicking; }
void sweet_log_append(const char *c, int size) { persistent.append(c, size); }
void _cnputc(char c, bool poll) { assert(poll); displayed += c; }
// PRODUCTION CALLBACK
int main() {
    for (bool muted : {false, true}) {
        for (bool panic : {false, true}) {
            sweet_console_muted = muted; panicking = panic;
            persistent.clear(); displayed.clear();
            console_write_unbuffered('U');
            console_write_unbuffered('\n');
#if defined(ARM64_BOARD_CONFIG_SWEET)
            assert(persistent == "U\n");
            assert(displayed == ((!muted || panic) ? "U\n" : ""));
#else
            assert(persistent.empty() && displayed == "U\n");
#endif
        }
    }
}
"""


class Console(unittest.TestCase):
    def test_gui_mute_logging_and_panic_paths(self):
        # The patch contains the complete changed function; no copy of Apple's
        # base source or downloaded kernel tree is needed for this regression.
        postimage = "\n".join(
            line[1:]
            for line in PATCH.read_text().splitlines()
            if line.startswith((" ", "+")) and not line.startswith("+++")
        )
        function = re.search(
            r"^void\nconsole_write_unbuffered\([^\n]*\)\n\{.*?^\}",
            postimage,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(function)
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            path = work / "console.cpp"
            path.write_text(HARNESS.replace("// PRODUCTION CALLBACK", function.group()))
            for sweet in (False, True):
                with self.subTest(sweet=sweet):
                    binary = work / ("sweet" if sweet else "other")
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
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(
                        compiled.returncode, 0, compiled.stdout + compiled.stderr
                    )
                    result = subprocess.run(
                        [str(binary)], check=False, capture_output=True, text=True
                    )
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )
