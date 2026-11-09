"""Compile replay must follow the CI checkout rather than a particular fork."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CompileReplay(unittest.TestCase):
    def test_replay_uses_local_compilers_and_relocates_fork_paths(self):
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            compiler = work / "compiler"
            compiler.write_text(
                f"#!{sys.executable}\n"
                "import json, pathlib, sys\n"
                "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text(\n"
                "    json.dumps(sys.argv[1:]))\n"
            )
            compiler.chmod(0o755)
            for fork in ("ios-joyeuse", "ios-sweet"):
                with self.subTest(fork=fork):
                    bt = work / fork
                    cdir = bt / "build/xnu.obj/iokit/DEVELOPMENT"
                    cdir.mkdir(parents=True)
                    (cdir / "meta_features.h").touch()
                    objects = bt / "objects"
                    objects.mkdir()
                    ci = f"/Users/runner/work/{fork}/{fork}/dxb"
                    sdk = (
                        "/Applications/Xcode_16.app/Contents/Developer/Platforms/"
                        "MacOSX.platform/Developer/SDKs/MacOSX.sdk/System/Library/"
                        "Frameworks/Kernel.framework/Versions/A/PrivateHeaders/platform"
                    )
                    log = bt / "ci.log"
                    log.write_text(
                        "build\tBuild\t2026-11-07T03:50:00Z "
                        f"/toolchain/clang++ -c -arch arm64 -I{ci}/xnu/iokit "
                        f"-I{sdk} -D'NAME=two words' {ci}/xnu/iokit/test.cpp "
                        f"-o {ci}/build/test.o\n"
                    )
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(ROOT / "tools/xnu-cc.py"),
                            str(log),
                            str(bt),
                        ],
                        env={
                            **os.environ,
                            "CC": str(compiler),
                            "CXX": str(compiler),
                            "XNU_CC_OBJDIR": str(objects),
                        },
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    args = json.loads((objects / "iokit__test.cpp.o").read_text())
                    self.assertIn(str(bt / "xnu/iokit/test.cpp"), args)
                    self.assertIn(f"-I{bt}/sdk-kernel-platform/platform", args)
                    self.assertIn("-DNAME=two words", args)
                    self.assertFalse(any(ci in arg for arg in args))
                    self.assertNotIn("-arch", args)
