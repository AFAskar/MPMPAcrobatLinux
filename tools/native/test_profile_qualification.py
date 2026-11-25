"""Terminal profile qualification must never persist passed=True when paired display fails, times out, or is deferred."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from profile_qualification import finalize_profile_qualification
import profiles_2014
import profiles_2024


class ProfileQualificationTests(unittest.TestCase):
    def _base_report(self):
        return {
            "passed": False,
            "profile": "cleric",
            "phases": [{"label": "p1", "pdf": "p1.pdf", "pdf_sha256": "a" * 64, "state": {}}],
            "mixed_native": {"passed": True},
        }

    def test_deferred_paired_display_keeps_terminal_passed_false_and_writes_capture(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            report = self._base_report()
            out = finalize_profile_qualification(
                report,
                folder,
                folder / "native.json",
                folder / "source.pdf",
                skip_paired_display=True,
            )
            disk = json.loads((folder / "report.json").read_text())
            capture = json.loads((folder / "capture.json").read_text())
            self.assertFalse(out["passed"])
            self.assertFalse(disk["passed"])
            self.assertTrue(disk["state_capture_passed"])
            self.assertEqual(disk["paired_display_status"], "deferred")
            self.assertIsNone(disk["paired_display"])
            self.assertTrue(capture["passed"])
            self.assertTrue(capture["capture_only"])

    def test_failed_paired_display_never_persists_passed_true(self):
        def failing_runner(cmd, **kwargs):
            out_dir = Path(cmd[cmd.index("--output") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "comparison.json").write_text(json.dumps({"passed": False, "complete_report_pair": False, "error": "AP mismatch"}))
            raise subprocess.CalledProcessError(1, cmd)

        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            report = self._base_report()
            with self.assertRaises(subprocess.CalledProcessError):
                finalize_profile_qualification(
                    report,
                    folder,
                    folder / "native.json",
                    folder / "source.pdf",
                    runner=failing_runner,
                )
            disk = json.loads((folder / "report.json").read_text())
            self.assertFalse(disk["passed"])
            self.assertTrue(disk["state_capture_passed"])
            self.assertEqual(disk["paired_display_status"], "failed")
            self.assertIn("error", disk)

    def test_timeout_paired_display_never_persists_passed_true(self):
        def timeout_runner(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1800))

        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            report = self._base_report()
            with self.assertRaises(subprocess.TimeoutExpired):
                finalize_profile_qualification(
                    report,
                    folder,
                    folder / "native.json",
                    folder / "source.pdf",
                    timeout=10,
                    runner=timeout_runner,
                )
            disk = json.loads((folder / "report.json").read_text())
            self.assertFalse(disk["passed"])
            self.assertTrue(disk["state_capture_passed"])
            self.assertEqual(disk["paired_display_status"], "timeout")
            self.assertIn("timed out", disk["error"])

    def test_successful_paired_display_sets_terminal_passed_true(self):
        def ok_runner(cmd, **kwargs):
            ref_path = Path(cmd[cmd.index("--reference") + 1])
            self.assertEqual(ref_path.name, "capture.json")
            out_dir = Path(cmd[cmd.index("--output") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "comparison.json").write_text(json.dumps({"passed": True, "complete_report_pair": True}))
            return subprocess.CompletedProcess(cmd, 0)

        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            report = self._base_report()
            out = finalize_profile_qualification(
                report,
                folder,
                folder / "native.json",
                folder / "source.pdf",
                runner=ok_runner,
            )
            disk = json.loads((folder / "report.json").read_text())
            self.assertTrue(out["passed"])
            self.assertTrue(disk["passed"])
            self.assertTrue(disk["state_capture_passed"])
            self.assertEqual(disk["paired_display_status"], "passed")
            self.assertTrue(disk["paired_display"].endswith("comparison.json"))

    def test_profile_validators_reject_invalid_state_even_under_python_optimize(self):
        bad_state = {
            "errors": ["injected error"],
            "unavailable": [],
            "calculation": {"app": False, "doc": False, "delay": True},
            "fields": {},
            "rows": [],
            "identity": {},
            "choices": {},
            "race": {},
            "background": {},
            "spells": {},
            "pages": 0,
            "notesAndActions": {},
        }
        with self.assertRaises(AssertionError):
            profiles_2024.validate_profile_state("cleric", "cleric-l1-setup", bad_state)
        with self.assertRaises(AssertionError):
            profiles_2014.validate_profile_state("barbarian", "barbarian-l3-berserker", bad_state)
        bad_fields_only = dict(bad_state, errors=[], calculation={"app": True, "doc": True, "delay": False}, fields={"Character Level": "99", "Proficiency Bonus": "9"})
        with self.assertRaises(AssertionError):
            profiles_2024.validate_profile_state("cleric", "cleric-l1-setup", bad_fields_only)
        with self.assertRaises(AssertionError):
            profiles_2014.validate_profile_state("barbarian", "barbarian-l3-berserker", bad_fields_only)


if __name__ == "__main__":
    unittest.main()
