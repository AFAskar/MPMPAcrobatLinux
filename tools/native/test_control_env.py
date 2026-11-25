"""Verify tools/acrobat/control.py honors environment-variable overrides."""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = ROOT / "tools/acrobat/control.py"


def load_control(env_overrides):
    spec = importlib.util.spec_from_file_location("mpmb_control_env_test", CONTROL_PATH)
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, env_overrides, clear=False):
        spec.loader.exec_module(mod)
    return mod


class ControlEnvTests(unittest.TestCase):
    def test_defaults_without_env_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = {
                k: v
                for k, v in os.environ.items()
                if not k.startswith("MPMB_WIN_") and k not in ("MPMB_VM_NAME", "MPMB_MUX_DIR")
            }
            clean["MPMB_MUX_DIR"] = tmp
            with mock.patch.dict(os.environ, clean, clear=True):
                spec = importlib.util.spec_from_file_location("mpmb_control_defaults", CONTROL_PATH)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            self.assertEqual(mod.WIN_USER, "mpmb-test")
            self.assertEqual(mod.WIN_HOST, "127.0.0.1")
            self.assertEqual(mod.WIN_PORT, "2222")
            self.assertEqual(mod.SCP_TARGET, "mpmb-test@127.0.0.1")
            self.assertEqual(mod.VM_NAME, "mpmb-windows11")
            self.assertEqual(mod.WIN, r"C:\Users\mpmb-test\MPMB-Testing")
            self.assertIn("mpmb-test@127.0.0.1", mod.SSH)

    def test_custom_env_overrides_all_endpoints_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = load_control(
                {
                    "MPMB_WIN_USER": "alice",
                    "MPMB_WIN_HOST": "10.0.0.5",
                    "MPMB_WIN_PORT": "2229",
                    "MPMB_WIN_SSH_KEY": str(Path(tmp) / "custom_key"),
                    "MPMB_VM_NAME": "custom-win11",
                    "MPMB_MUX_DIR": tmp,
                }
            )
            self.assertEqual(mod.WIN_USER, "alice")
            self.assertEqual(mod.SCP_TARGET, "alice@10.0.0.5")
            self.assertEqual(mod.WIN, r"C:\Users\alice\MPMB-Testing")
            self.assertEqual(mod.VM_NAME, "custom-win11")
            self.assertEqual(mod.KEY, Path(tmp) / "custom_key")
            self.assertIn("2229", mod.SSH)
            self.assertIn("alice@10.0.0.5", mod.SSH)
            self.assertIn("2229", mod.SCP)
            self.assertEqual(mod.remote_path("runs/a.pdf"), r"C:\Users\alice\MPMB-Testing\runs\a.pdf")

    def test_explicit_root_and_scp_target_override_derived_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = load_control(
                {
                    "MPMB_WIN_USER": "alice",
                    "MPMB_WIN_SCP_TARGET": "bob@127.0.0.1",
                    "MPMB_WIN_ROOT": r"D:\Testing\MPMB",
                    "MPMB_MUX_DIR": tmp,
                }
            )
            self.assertEqual(mod.SCP_TARGET, "bob@127.0.0.1")
            self.assertEqual(mod.WIN, r"D:\Testing\MPMB")


if __name__ == "__main__":
    unittest.main()
