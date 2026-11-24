#!/usr/bin/env python3
"""Negative controls for verify-paired-feature-displays.py missing/hidden widgets."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
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


def write_visible_page_pdf(path: Path, target_page_index: int, text: str = "Populated Hero"):
    w = PdfWriter()
    pages = [w.add_blank_page(width=200, height=200), w.add_blank_page(width=200, height=200)]
    font_ref = w._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    ap = DecodedStreamObject()
    ap.set_data(f"BT /F1 12 Tf 2 4 Td ({text}) Tj ET".encode("latin-1"))
    ap[NameObject("/Type")] = NameObject("/XObject")
    ap[NameObject("/Subtype")] = NameObject("/Form")
    ap[NameObject("/BBox")] = ArrayObject([NumberObject(0), NumberObject(0), NumberObject(150), NumberObject(20)])
    ap[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
    })
    ap_ref = w._add_object(ap)
    widget_ref = w._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Tx"),
        NameObject("/T"): TextStringObject("PC Name"),
        NameObject("/V"): TextStringObject(text),
        NameObject("/Rect"): ArrayObject([NumberObject(10), NumberObject(10), NumberObject(160), NumberObject(30)]),
        NameObject("/F"): NumberObject(4),
        NameObject("/AP"): DictionaryObject({NameObject("/N"): ap_ref}),
    }))
    pages[target_page_index][NameObject("/Annots")] = ArrayObject([widget_ref])
    w._root_object[NameObject("/AcroForm")] = DictionaryObject({
        NameObject("/Fields"): ArrayObject([widget_ref]),
    })
    with path.open("wb") as out:
        w.write(out)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MissingWidgetNegativeControls(unittest.TestCase):
    def _run_worker(self, hidden_widget: bool, optimize: bool = False):
        with tempfile.TemporaryDirectory(prefix="paired-missing-widget-") as td:
            tmp = Path(td)
            nat, ref = tmp / "nat.pdf", tmp / "ref.pdf"
            write_synthetic_pdf(nat, hidden_widget=hidden_widget)
            write_synthetic_pdf(ref, hidden_widget=hidden_widget)
            req = tmp / "req.json"
            out = tmp / "out.json"
            req.write_text(json.dumps({"native": str(nat), "reference": str(ref), "expected": {"PC Name": "Populated Hero"}}))
            cmd = [sys.executable] + (["-O"] if optimize else []) + [str(VERIFIER), "--worker", str(req), "--worker-output", str(out)]
            env = dict(os.environ, PYTHONOPTIMIZE="1") if optimize else None
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
            data = json.loads(out.read_text())
            self.assertNotEqual(proc.returncode, 0, data)
            self.assertFalse(data["passed"], data)
            self.assertIn("Populated field has no visible widgets", data.get("error", ""))

    def _run_pair(self, nat_page: int, ref_page: int, nat_digest_override=..., ref_indep_override=..., optimize: bool = False):
        with tempfile.TemporaryDirectory(prefix="paired-provenance-") as td:
            tmp = Path(td)
            nat_pdf, ref_pdf = tmp / "nat.pdf", tmp / "ref.pdf"
            nat_sha = write_visible_page_pdf(nat_pdf, nat_page)
            ref_sha = write_visible_page_pdf(ref_pdf, ref_page)
            state = {"fields": {"PC Name": "Populated Hero"}, "resources": {}, "notesAndActions": {}}
            nat_phase = {"label": "p1", "pdf": str(nat_pdf), "state": state}
            if nat_digest_override is ...:
                nat_phase["pdf_sha256"] = nat_sha
            elif nat_digest_override is not None:
                nat_phase["pdf_sha256"] = nat_digest_override
            ref_phase = {
                "label": "p1",
                "pdf": str(ref_pdf),
                "pdf_sha256": ref_sha,
                "canonical": {"independent": {"sha256": ref_sha if ref_indep_override is ... else ref_indep_override}},
                "state": state,
            }
            nat_report = tmp / "nat.json"
            ref_report = tmp / "ref.json"
            nat_report.write_text(json.dumps({"passed": True, "phases": [nat_phase]}))
            ref_report.write_text(json.dumps({"passed": True, "phases": [ref_phase]}))
            out_dir = tmp / "out"
            cmd = [sys.executable] + (["-O"] if optimize else []) + [
                str(VERIFIER), "--native", str(nat_report), "--reference", str(ref_report), "--output", str(out_dir)
            ]
            env = dict(os.environ, PYTHONOPTIMIZE="1") if optimize else None
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
            comp = json.loads((out_dir / "comparison.json").read_text())
            return proc.returncode, comp

    def test_rejects_populated_field_with_zero_widgets_in_both_pdfs(self):
        self._run_worker(hidden_widget=False)
        self._run_worker(hidden_widget=False, optimize=True)

    def test_rejects_populated_field_with_only_hidden_widgets_in_both_pdfs(self):
        self._run_worker(hidden_widget=True)

    def test_rejects_missing_or_mismatched_producer_pdf_digests(self):
        rc, comp = self._run_pair(0, 0, nat_digest_override=None)
        self.assertNotEqual(rc, 0)
        self.assertFalse(comp["passed"])
        self.assertIn("Missing producer PDF sha256 digest", comp.get("error", ""))

        rc, comp = self._run_pair(0, 0, nat_digest_override="0" * 64, optimize=True)
        self.assertNotEqual(rc, 0)
        self.assertFalse(comp["passed"])
        self.assertIn("Qualified PDF hash differs", comp.get("error", ""))

        rc, comp = self._run_pair(0, 0, ref_indep_override="f" * 64)
        self.assertNotEqual(rc, 0)
        self.assertFalse(comp["passed"])
        self.assertIn("Qualified PDF hash differs", comp.get("error", ""))

    def test_rejects_visible_widget_on_wrong_page(self):
        rc, comp = self._run_pair(1, 0)
        self.assertNotEqual(rc, 0)
        self.assertFalse(comp["passed"])
        self.assertIn("visible widget page mismatch", comp.get("error", ""))

    def test_accepts_matching_producer_digests_and_page(self):
        rc, comp = self._run_pair(0, 0)
        self.assertEqual(rc, 0, comp)
        self.assertTrue(comp["passed"])
        self.assertTrue(comp["complete_report_pair"])


if __name__ == "__main__":
    unittest.main()
