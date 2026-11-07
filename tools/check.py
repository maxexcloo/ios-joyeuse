#!/usr/bin/env python3
"""Run host behaviour tests without a phone, firmware or a kernel build."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT, check=True
)
