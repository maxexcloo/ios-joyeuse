"""Raw UFS byte I/O contracts, without a controller or phone."""

import re
import tempfile
import unittest
from pathlib import Path

from host import ROOT, apply_patches, compile_and_run

SOURCE = "bsd/dev/sweet_ufs.c"


class RawUFS(unittest.TestCase):
    def test_offsets_scatter_faults_and_partition_bounds(self):
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            apply_patches(work, SOURCE)
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
            compile_and_run(
                self,
                path,
                "-O1",
                "-g",
                "-fsanitize=address,undefined",
                "-fno-omit-frame-pointer",
            )
