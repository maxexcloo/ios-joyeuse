"""Root preferences use the copied system's build and version."""

import importlib.util
import plistlib
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "root_tweaks", Path(__file__).resolve().parents[1] / "tools/sweet-root-tweaks.py"
)
root_tweaks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(root_tweaks)


class RootVersion(unittest.TestCase):
    def run_tweaks(self, system_version):
        with tempfile.TemporaryDirectory() as scratch, ExitStack() as stack:
            root = Path(scratch)
            (root / "System/Library/xpc").mkdir(parents=True)
            version_path = root / "System/Library/CoreServices/SystemVersion.plist"
            version_path.parent.mkdir()
            version_path.write_bytes(plistlib.dumps(system_version))
            stack.enter_context(
                mock.patch.object(root_tweaks.sys, "argv", ["tweaks", scratch])
            )
            for name in ("launchd", "containers", "audio", "capabilities", "network"):
                stack.enter_context(mock.patch.object(root_tweaks, name))
            stack.enter_context(
                mock.patch.object(
                    root_tweaks, "find_container", return_value=str(root / "container")
                )
            )
            stack.enter_context(mock.patch.object(root_tweaks.os, "chown"))
            save = stack.enter_context(mock.patch.object(root_tweaks, "save"))
            merge = stack.enter_context(mock.patch.object(root_tweaks, "merge_pref"))
            root_tweaks.main()
            return save.call_args.args[1], merge.call_args_list[0].args[2]

    def test_copied_system_version_reaches_activation_and_migration(self):
        activation, migration = self.run_tweaks(
            {"ProductBuildVersion": "20H999", "ProductVersion": "16.7.99"}
        )
        self.assertEqual(activation["-BuildVersion"], "20H999")
        self.assertEqual(activation["-ProductVersion"], "16.7.99")
        self.assertEqual(migration["LastSystemVersion"], "20H999")
        self.assertEqual(migration["DMUserDataDisposition"]["buildVersion"], "20H999")

    def test_missing_build_has_no_pinned_fallback(self):
        with self.assertRaisesRegex(KeyError, "ProductBuildVersion"):
            self.run_tweaks({"ProductVersion": "16.7.99"})
