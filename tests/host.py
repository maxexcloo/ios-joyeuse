"""Reconstruct patched kernel sources and run their host harnesses."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def apply_patches(work, *paths):
    patches = subprocess.check_output(
        ["git", "ls-files", "--", "xnu/patches/*.patch"], cwd=ROOT, text=True
    ).splitlines()
    subprocess.run(
        [
            "git",
            "apply",
            *(f"--include={path}" for path in paths),
            *(str(ROOT / patch) for patch in patches),
        ],
        cwd=work,
        check=True,
        capture_output=True,
    )


def compile_and_run(test, source, *flags):
    binary = source.with_suffix("")
    compiled = subprocess.run(
        [
            os.environ.get("CXX", "c++"),
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            *flags,
            str(source),
            "-o",
            str(binary),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    test.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
    result = subprocess.run([str(binary)], check=False, capture_output=True, text=True)
    test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
