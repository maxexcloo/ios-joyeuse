"""Exercise the opt-in HID timer without hardware or an IOHID runtime."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "iokit/Kernel/arm/hid/SweetHID.cpp"


class HID(unittest.TestCase):
    def test_synthetic_input_finishes_with_buttons_and_contacts_released(self):
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            patches = subprocess.check_output(
                ["git", "ls-files", "--", "xnu/patches/*.patch"],
                cwd=ROOT,
                text=True,
            ).splitlines()
            subprocess.run(
                [
                    "git",
                    "apply",
                    f"--include={SOURCE}",
                    *map(str, (ROOT / p for p in sorted(patches))),
                ],
                cwd=work,
                check=True,
                capture_output=True,
            )
            callback = re.search(
                r"^void\nSweetHIDButtons::testFired\([^\n]*\)\n\{.*?^\}",
                (work / SOURCE).read_text(),
                re.MULTILINE | re.DOTALL,
            ).group()
            fixture = r"""
#include <cassert>
struct OSObject {};
struct IOTimerEventSource {
    bool pending = true;
    void setTimeoutMS(unsigned int ms) { assert(ms > 0); pending = true; }
};
constexpr unsigned int kHIDUsage_Csmr_Menu = 0x40;
constexpr unsigned int kHIDUsage_Csmr_Power = 0x30;
struct Touch {
    bool down = false;
    int previous = 0, strokes = 0;
    void touch(int finger, bool next, int x, int y) {
        assert(finger == 0 && x >= 0 && x < 1080 && y >= 0 && y < 2400);
        if (!down) { assert(next && y > 2350); ++strokes; }
        else { assert(y <= previous); }
        if (!next) assert(y < 800);
        down = next; previous = y;
    }
} touch;
Touch *gSweetTouch = &touch;
struct SweetHIDButtons : OSObject {
    bool fTestSwipe = false, down = false;
    unsigned int fTestCount = 0, fTestSecs = 30, presses = 0;
    void key(unsigned int usage, bool next) {
        assert(usage == (fTestSwipe ? kHIDUsage_Csmr_Power : kHIDUsage_Csmr_Menu));
        assert(down != next);
        down = next; if (next) ++presses;
    }
    static void testFired(OSObject *, IOTimerEventSource *);
};
// PRODUCTION CALLBACK
int main() {
    for (bool swipe : {false, true}) {
        touch = Touch{};
        SweetHIDButtons buttons;
        buttons.fTestSwipe = swipe;
        IOTimerEventSource timer;
        unsigned int callbacks = 0;
        while (timer.pending) {
            timer.pending = false;
            SweetHIDButtons::testFired(&buttons, &timer);
            assert(++callbacks < 1000);
        }
        assert(buttons.presses > 0 && !buttons.down && !touch.down);
        assert((touch.strokes > 0) == swipe);
    }
}
""".replace("// PRODUCTION CALLBACK", callback)
            source, binary = work / "hid.cpp", work / "hid"
            source.write_text("#include <initializer_list>\n" + fixture)
            subprocess.run(
                [
                    os.environ.get("CXX", "c++"),
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-fsanitize=address,undefined",
                    str(source),
                    "-o",
                    str(binary),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run([str(binary)], check=True, capture_output=True)
