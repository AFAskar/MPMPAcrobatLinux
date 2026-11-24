"""Class and Levels display inspection must preserve class names and associated levels."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'acrobat'))
import verify


def make_class_levels_pdf(path: Path, canonical: str, visible: str):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    font = DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
    })
    font_ref = writer._add_object(font)

    ap = DecodedStreamObject()
    ap.set_data(f'BT /F1 12 Tf 2 4 Td ({visible}) Tj ET'.encode('latin-1'))
    ap[NameObject('/Type')] = NameObject('/XObject')
    ap[NameObject('/Subtype')] = NameObject('/Form')
    ap[NameObject('/BBox')] = ArrayObject([NumberObject(0), NumberObject(0), NumberObject(200), NumberObject(20)])
    ap[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref}),
    })
    ap_ref = writer._add_object(ap)

    widget = DictionaryObject({
        NameObject('/Type'): NameObject('/Annot'),
        NameObject('/Subtype'): NameObject('/Widget'),
        NameObject('/FT'): NameObject('/Tx'),
        NameObject('/T'): TextStringObject('Class and Levels'),
        NameObject('/V'): TextStringObject(canonical),
        NameObject('/Rect'): ArrayObject([NumberObject(10), NumberObject(700), NumberObject(210), NumberObject(720)]),
        NameObject('/F'): NumberObject(4),
        NameObject('/AP'): DictionaryObject({NameObject('/N'): ap_ref}),
    })
    widget_ref = writer._add_object(widget)
    page[NameObject('/Annots')] = ArrayObject([widget_ref])
    writer._root_object[NameObject('/AcroForm')] = DictionaryObject({
        NameObject('/Fields'): ArrayObject([widget_ref]),
    })
    with path.open('wb') as stream:
        writer.write(stream)


class ClassAndLevelsVerifyTests(unittest.TestCase):
    def test_rejects_wrong_level_digits(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'wrong-level.pdf'
            make_class_levels_pdf(pdf, 'Fighter 12', 'Fighter 2')
            result = verify.inspect(pdf, {'Class and Levels': 'Fighter 12'})
            self.assertFalse(result['passed'])
            self.assertFalse(result['widgets'][0]['appearance_matches'])

    def test_rejects_swapped_multiclass_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'swapped-multiclass.pdf'
            make_class_levels_pdf(pdf, 'Fighter 5 / Wizard 2', 'Fighter 2 / Wizard 5')
            result = verify.inspect(pdf, {'Class and Levels': 'Fighter 5 / Wizard 2'})
            self.assertFalse(result['passed'])
            self.assertFalse(result['widgets'][0]['appearance_matches'])

    def test_accepts_matching_levels_with_formatting_punctuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'valid-multiclass.pdf'
            make_class_levels_pdf(pdf, 'Fighter 5 / Wizard 2', 'Fighter 5,  Wizard 2')
            result = verify.inspect(pdf, {'Class and Levels': 'Fighter 5 / Wizard 2'})
            self.assertTrue(result['passed'])
            self.assertTrue(result['widgets'][0]['appearance_matches'])


if __name__ == '__main__':
    unittest.main()
