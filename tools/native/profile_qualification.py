"""Separate intermediate Reader state capture from terminal paired-display qualification."""
import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAIRED_VERIFIER = ROOT / "tools/native/verify-paired-feature-displays.py"


def finalize_profile_qualification(
    report: dict,
    folder: Path,
    native_report_path: Path,
    source_pdf: Path,
    *,
    skip_paired_display: bool = False,
    timeout: int = 3600,
    runner=subprocess.run,
) -> dict:
    """Persist intermediate capture.json, run paired display check unless deferred, and set terminal passed."""
    report["state_capture_passed"] = True
    report["passed"] = False
    capture_path = folder / "capture.json"
    capture_payload = copy.deepcopy(report)
    capture_payload["passed"] = True
    capture_payload["capture_only"] = True
    capture_path.write_text(json.dumps(capture_payload, indent=2) + "\n")
    report["capture_report"] = str(capture_path)

    if skip_paired_display:
        report["paired_display_status"] = "deferred"
        report["paired_display"] = None
        report["passed"] = False
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        return report

    pair_out = folder / "paired-displays"
    try:
        runner(
            [
                sys.executable,
                str(PAIRED_VERIFIER),
                "--native",
                str(native_report_path),
                "--reference",
                str(capture_path),
                "--original",
                str(source_pdf),
                "--output",
                str(pair_out),
            ],
            cwd=ROOT,
            check=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        report["paired_display_status"] = "timeout"
        report["paired_display"] = None
        report["passed"] = False
        report["error"] = f"Paired display verification timed out after {timeout}s: {exc}"
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        raise
    except Exception as exc:
        report["paired_display_status"] = "failed"
        report["paired_display"] = str(pair_out / "comparison.json") if (pair_out / "comparison.json").exists() else None
        report["passed"] = False
        report["error"] = f"Paired display verification failed: {exc}"
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        raise

    comparison_path = pair_out / "comparison.json"
    if not comparison_path.exists():
        report["paired_display_status"] = "failed"
        report["passed"] = False
        report["error"] = f"Missing paired display comparison output: {comparison_path}"
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        raise AssertionError(report["error"])

    pair_data = json.loads(comparison_path.read_text())
    if pair_data.get("passed") is not True or pair_data.get("complete_report_pair") is not True:
        report["paired_display_status"] = "failed"
        report["paired_display"] = str(comparison_path)
        report["passed"] = False
        report["error"] = f"Paired display comparison did not pass completely: {pair_data.get('error')}"
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        raise AssertionError(report["error"])

    report["paired_display_status"] = "passed"
    report["paired_display"] = str(comparison_path)
    report["passed"] = True
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
