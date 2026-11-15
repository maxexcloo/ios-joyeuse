"""Exercise the opt-in HID timer without hardware or an IOHID runtime."""

import re
import tempfile
import unittest
from pathlib import Path

from host import apply_patches, compile_and_run

SOURCE = "iokit/Kernel/arm/hid/SweetHID.cpp"


class HID(unittest.TestCase):
    def test_synthetic_input_finishes_with_buttons_and_contacts_released(self):
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            apply_patches(work, SOURCE)
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
    bool down = false, tapping = false, expectTap = false;
    int previous = 0;
    unsigned int strokes = 0, taps = 0;
    void touch(int finger, bool next, int x, int y) {
        assert(finger == 0 && x >= 0 && x < 1080 && y >= 0 && y < 2400);
        if (!down) {
            assert(next);
            tapping = y <= 2350;
            if (tapping) { assert(expectTap && x == 670 && y == 850); ++taps; }
            else { ++strokes; }
        } else if (!tapping) { assert(y <= previous); }
        if (tapping) assert(x == 670 && y == 850);
        if (!next && !tapping) assert(y < 800);
        down = next; previous = y;
    }
} touch;
Touch *gSweetTouch = &touch;
struct SweetHIDButtons : OSObject {
    bool fTestSwipe = false, fTestTap = false, down = false;
    int fTestTapX = 670, fTestTapY = 850;
    unsigned int fTestCount = 0, fTestSecs = 30, fTestCycles = 30, presses = 0;
    void key(unsigned int usage, bool next) {
        assert(usage == (fTestSwipe ? kHIDUsage_Csmr_Power : kHIDUsage_Csmr_Menu));
        assert(down != next);
        down = next; if (next) ++presses;
    }
    static void testFired(OSObject *, IOTimerEventSource *);
};
// PRODUCTION CALLBACK
int main() {
    for (unsigned int cycles : {0, 1, 2, 30}) {
    for (bool swipe : {false, true}) {
      for (bool tap : {false, true}) {
        if (tap && !swipe) continue;
        touch = Touch{};
        touch.expectTap = tap;
        SweetHIDButtons buttons;
        buttons.fTestCycles = cycles;
        buttons.fTestSwipe = swipe;
        buttons.fTestTap = tap;
        IOTimerEventSource timer;
        unsigned int callbacks = 0;
        while (timer.pending) {
            timer.pending = false;
            SweetHIDButtons::testFired(&buttons, &timer);
            assert(++callbacks < 1000);
        }
        assert(buttons.presses == (swipe ? cycles : 30));
        assert(!buttons.down && !touch.down);
        assert(touch.strokes == (swipe ? cycles : 0));
        assert(touch.taps == (tap ? cycles : 0));
      }
    }
    }
}
""".replace("// PRODUCTION CALLBACK", callback)
            source = work / "hid.cpp"
            source.write_text("#include <initializer_list>\n" + fixture)
            compile_and_run(self, source, "-fsanitize=address,undefined")
