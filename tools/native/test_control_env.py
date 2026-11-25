"""Verify tools/acrobat/control.py honors environment-variable and .env overrides."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = ROOT / "tools/acrobat/control.py"


def load_control(env_overrides, clear=False):
    spec = importlib.util.spec_from_file_location("mpmb_control_env_test", CONTROL_PATH)
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, env_overrides, clear=clear):
        spec.loader.exec_module(mod)
    return mod


def clean_env(extra):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("MPMB_WIN_")
        and k not in ("MPMB_VM_NAME", "MPMB_MUX_DIR", "MPMB_ENV_FILE")
    }
    env.update(extra)
    return env


class ControlEnvTests(unittest.TestCase):
    def test_defaults_without_env_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = load_control(clean_env({"MPMB_MUX_DIR": tmp, "MPMB_ENV_FILE": ""}), clear=True)
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
                clean_env(
                    {
                        "MPMB_ENV_FILE": "",
                        "MPMB_WIN_USER": "alice",
                        "MPMB_WIN_HOST": "10.0.0.5",
                        "MPMB_WIN_PORT": "2229",
                        "MPMB_WIN_SSH_KEY": str(Path(tmp) / "custom_key"),
                        "MPMB_VM_NAME": "custom-win11",
                        "MPMB_MUX_DIR": tmp,
                    }
                ),
                clear=True,
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
                clean_env(
                    {
                        "MPMB_ENV_FILE": "",
                        "MPMB_WIN_USER": "alice",
                        "MPMB_WIN_SCP_TARGET": "bob@127.0.0.1",
                        "MPMB_WIN_ROOT": r"D:\Testing\MPMB",
                        "MPMB_MUX_DIR": tmp,
                    }
                ),
                clear=True,
            )
            self.assertEqual(mod.SCP_TARGET, "bob@127.0.0.1")
            self.assertEqual(mod.WIN, r"D:\Testing\MPMB")

    def test_dotenv_file_loads_and_shell_env_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            key_path = Path(tmp) / "vm_key"
            env_path.write_text(
                "\n".join(
                    [
                        "# Comment line",
                        "",
                        "MPMB_WIN_USER=dotenv-user",
                        'export MPMB_WIN_HOST="127.0.0.2"',
                        "MPMB_WIN_PORT='2244'",
                        f"MPMB_WIN_SSH_KEY={key_path}",
                        "MPMB_VM_NAME=dotenv-vm",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            mod = load_control(
                clean_env(
                    {
                        "MPMB_ENV_FILE": str(env_path),
                        "MPMB_WIN_PORT": "2299",
                        "MPMB_MUX_DIR": tmp,
                    }
                ),
                clear=True,
            )
            self.assertEqual(mod.WIN_USER, "dotenv-user")
            self.assertEqual(mod.WIN_HOST, "127.0.0.2")
            self.assertEqual(mod.WIN_PORT, "2299")
            self.assertEqual(mod.SCP_TARGET, "dotenv-user@127.0.0.2")
            self.assertEqual(mod.WIN, r"C:\Users\dotenv-user\MPMB-Testing")
            self.assertEqual(mod.KEY, key_path)
            self.assertEqual(mod.VM_NAME, "dotenv-vm")

    def test_missing_dotenv_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = load_control(
                clean_env(
                    {
                        "MPMB_ENV_FILE": str(Path(tmp) / "does-not-exist.env"),
                        "MPMB_MUX_DIR": tmp,
                    }
                ),
                clear=True,
            )
            self.assertEqual(mod.WIN_USER, "mpmb-test")
            self.assertEqual(mod.WIN_HOST, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
