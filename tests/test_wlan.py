"""Exercise the patched WLAN callbacks with host-side mbuf and BPF consumers."""

import re
import tempfile
import unittest
from pathlib import Path

from host import ROOT, apply_patches, compile_and_run

SOURCE = "iokit/Kernel/arm/TopazModem.cpp"


class WLAN(unittest.TestCase):
    def test_ethernet_delivery_and_packet_ownership(self):
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            apply_patches(work, SOURCE)
            source = (work / SOURCE).read_text()
            callbacks = []
            for name in ("wl_output", "wl_rx"):
                match = re.search(
                    rf"^static (?:errno_t|void)\n{name}\([^\n]*\)\n\{{.*?^\}}",
                    source,
                    re.MULTILINE | re.DOTALL,
                )
                self.assertIsNotNone(match, name)
                callbacks.append(match.group())
            harness = (ROOT / "tests/wlan_host.cpp").read_text()
            path = work / "wlan.cpp"
            path.write_text(
                harness.replace("// PRODUCTION CALLBACKS", "\n".join(callbacks))
            )
            compile_and_run(
                self,
                path,
                "-O1",
                "-g",
                "-fsanitize=address,undefined",
                "-fno-omit-frame-pointer",
            )
