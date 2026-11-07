"""Exercise the patched WLAN callbacks with host-side mbuf and BPF consumers."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "iokit/Kernel/arm/TopazModem.cpp"


class WLAN(unittest.TestCase):
    def test_ethernet_delivery_and_packet_ownership(self):
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            # Reconstruct the production file from its source of truth, without
            # downloading XNU or keeping a second copy of the callback code.
            patches = subprocess.check_output(
                ["git", "ls-files", "--", "xnu/patches/*.patch"], cwd=ROOT, text=True
            ).splitlines()
            subprocess.run(
                [
                    "git",
                    "apply",
                    f"--include={SOURCE}",
                    *(str(ROOT / patch) for patch in patches),
                ],
                cwd=work,
                check=True,
                capture_output=True,
            )
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
            binary = work / "wlan"
            compiled = subprocess.run(
                [
                    os.environ.get("CXX", "c++"),
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-O1",
                    "-g",
                    "-fsanitize=address,undefined",
                    "-fno-omit-frame-pointer",
                    str(path),
                    "-o",
                    str(binary),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(
                [str(binary)], check=False, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
