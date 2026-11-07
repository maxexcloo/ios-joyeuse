"""Raw UFS byte I/O contracts, without a controller or phone."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "bsd/dev/sweet_ufs.c"


class RawUFS(unittest.TestCase):
    def test_offsets_scatter_faults_and_partition_bounds(self):
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            patches = subprocess.check_output(
                [
                    "git",
                    "ls-files",
                    "--",
                    "xnu/patches/*.patch",
                ],
                cwd=ROOT,
                text=True,
            ).splitlines()
            subprocess.run(
                [
                    "git",
                    "apply",
                    f"--include={SOURCE}",
                    *(str(ROOT / p) for p in sorted(patches)),
                ],
                cwd=work,
                check=True,
                capture_output=True,
            )
            source = (work / SOURCE).read_text()
            callbacks = []
            for name in ("sweet_ufs_raw_io", "sweet_ufs_read", "sweet_ufs_write"):
                match = re.search(
                    rf"^static int\n{name}\([^\n]*\)\n\{{.*?^\}}",
                    source,
                    re.MULTILINE | re.DOTALL,
                )
                self.assertIsNotNone(match, name)
                callbacks.append(match.group())
            path = work / "ufs.cpp"
            path.write_text(
                (ROOT / "tests/ufs_host.cpp")
                .read_text()
                .replace("// PRODUCTION CALLBACKS", "\n".join(callbacks))
            )
            binary = work / "ufs"
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
