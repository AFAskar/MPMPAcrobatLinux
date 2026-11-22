#!/usr/bin/env python3
"""Negative controls for verify-paired-feature-displays.py missing/hidden widgets."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "tools/native/verify-paired-feature-displays.py"


def write_synthetic_pdf(path: Path, hidden_widget: bool):
    w = PdfWriter()
    page = w.add_blank_page(width=200, height=200)
    field_dict = DictionaryObject(
        {
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/T"): TextStringObject("PC Name"),
            NameObject("/V"): TextStringObject("Populated Hero"),
        }
    )
    if hidden_widget:
        field_dict[NameObject("/Subtype")] = NameObject("/Widget")
        field_dict[NameObject("/Rect")] = ArrayObject([NumberObject(10), NumberObject(10), NumberObject(100), NumberObject(30)])
        field_dict[NameObject("/F")] = NumberObject(2)  # Hidden flag
    field_ref = w._add_object(field_dict)
    if hidden_widget:
        page[NameObject("/Annots")] = ArrayObject([field_ref])
    w._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): ArrayObject([field_ref])}
    )
    with path.open("wb") as out:
        w.write(out)


class MissingWidgetNegativeControls(unittest.TestCase):
    def _run_worker(self, hidden_widget: bool):
        with tempfile.TemporaryDirectory(prefix="paired-missing-widget-") as td:
            tmp = Path(td)
            nat, ref = tmp / "nat.pdf", tmp / "ref.pdf"
            write_synthetic_pdf(nat, hidden_widget=hidden_widget)
            write_synthetic_pdf(ref, hidden_widget=hidden_widget)
            req = tmp / "req.json"
            out = tmp / "out.json"
            req.write_text(json.dumps({"native": str(nat), "reference": str(ref), "expected": {"PC Name": "Populated Hero"}}))
            proc = subprocess.run(
                [sys.executable, str(VERIFIER), "--worker", str(req), "--worker-output", str(out)],
                capture_output=True,
                text=True,
            )
            data = json.loads(out.read_text())
            self.assertNotEqual(proc.returncode, 0, data)
            self.assertFalse(data["passed"], data)
            self.assertIn("Populated field has no visible widgets", data.get("error", ""))

    def test_rejects_populated_field_with_zero_widgets_in_both_pdfs(self):
        self._run_worker(hidden_widget=False)

    def test_rejects_populated_field_with_only_hidden_widgets_in_both_pdfs(self):
        self._run_worker(hidden_widget=True)


if __name__ == "__main__":
    unittest.main()
