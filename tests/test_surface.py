"""Check the kernel's surface result against the native iOS 16 client ABI."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "iokit/Kernel/arm/SweetSurface.cpp"
HEADER = "iokit/Kernel/arm/SweetSurface.h"


class Surface(unittest.TestCase):
    def test_native_planar_getters_read_serialised_fields(self):
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
                    f"--include={HEADER}",
                    *(str(ROOT / p) for p in sorted(patches)),
                ],
                cwd=work,
                check=True,
                capture_output=True,
            )
            source, header = (work / SOURCE).read_text(), (work / HEADER).read_text()
            pieces = []
            for name in ("put32", "put64", "sweet_surface_fill_result"):
                pieces.append(
                    re.search(
                        rf"^static void\n{name}\([^\n]*\)\n\{{.*?^\}}",
                        source,
                        re.MULTILINE | re.DOTALL,
                    ).group()
                )
            plane = re.search(
                r"struct sweet_surface_plane \{.*?\};", header, re.DOTALL
            ).group()
            fields = header[
                header.index("\tuint32_t id;") : header.index("\tIOMemoryDescriptor")
            ]
            definitions = "\n".join(
                re.search(
                    rf"^#define {name}[^\n]*",
                    source if name != "SWEET_SURFACE_MAX_PLANES" else header,
                    re.MULTILINE,
                ).group()
                for name in (
                    "SWEET_SURFACE_RESULT_SIZE",
                    "SWEET_SURFACE_TIMESTAMPS",
                    "SWEET_SURFACE_MAX_PLANES",
                )
            )
            fixture = (ROOT / "tests/surface_host.cpp").read_text()
            fixture = fixture.replace(
                "// PRODUCTION TYPES",
                definitions
                + "\n"
                + plane
                + "\nstruct SweetSurface {\n"
                + fields
                + "};",
            )
            fixture = fixture.replace("// PRODUCTION SERIALISER", "\n".join(pieces))
            path, binary = work / "surface.cpp", work / "surface"
            path.write_text(fixture)
            result = subprocess.run(
                [
                    os.environ.get("CXX", "c++"),
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-fsanitize=address,undefined",
                    str(path),
                    "-o",
                    str(binary),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(
                [str(binary)], check=False, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
