"""Check the kernel's surface result against the native iOS 16 client ABI."""

import re
import tempfile
import unittest
from pathlib import Path

from host import ROOT, apply_patches, compile_and_run

SOURCE = "iokit/Kernel/arm/SweetSurface.cpp"
HEADER = "iokit/Kernel/arm/SweetSurface.h"


class Surface(unittest.TestCase):
    def test_native_planar_getters_read_serialised_fields(self):
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            apply_patches(work, SOURCE, HEADER)
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
            path = work / "surface.cpp"
            path.write_text(fixture)
            compile_and_run(self, path, "-fsanitize=address,undefined")
