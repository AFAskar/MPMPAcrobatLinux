#!/usr/bin/env python3
"""Independently compare all six ability scores, modifiers and saves in four feat states.

Read-only canonical text comparison against actual Reader outputs. Does not
normalize missing values, write reference values, or claim appearance equality.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import canonical_fields, script_hashes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', type=Path, required=True)
    a = p.parse_args()
    native = json.loads(a.native.read_text())
    assert native['passed'] and len(native['phases']) == 4
    reader = json.loads(Path(native['reader']).read_text())
    assert reader['passed']
    assert hashlib.sha256((a.native.parent / 'mpmb-reader').read_bytes()).hexdigest() == native['binary_sha256']
    names = [ability + suffix for ability in ['Str', 'Dex', 'Con', 'Int', 'Wis', 'Cha']
             for suffix in ['', ' Mod', ' ST Mod']]
    folder = ROOT / 'output/testing' / ('resilient-calculations-' + str(time.time_ns()))
    folder.mkdir()
    report = {'passed': False, 'scope': __doc__, 'native': str(a.native.resolve()),
              'field_names': names, 'cases': []}
    references = {phase['label']: phase for phase in reader['phases']}
    source = Path(reader['input'])
    try:
        for phase in native['phases']:
            label = phase['label']
            native_pdf, reader_pdf = Path(phase['pdf']), Path(references[label]['pdf'])
            actual = canonical_fields(PdfReader(native_pdf))
            expected = canonical_fields(PdfReader(reader_pdf))
            values = {n: expected[n]['/V'] for n in names}
            assert {n: actual[n]['/V'] for n in names} == values
            assert script_hashes(native_pdf) == script_hashes(source) == script_hashes(reader_pdf)
            report['cases'].append({'label': label, 'fields': values,
                                    'native_sha256': hashlib.sha256(native_pdf.read_bytes()).hexdigest(),
                                    'reader_sha256': hashlib.sha256(reader_pdf.read_bytes()).hexdigest()})
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        path = folder / 'calculations.json'
        path.write_text(json.dumps(report, indent=2) + '\n')
        print(path, flush=True)


if __name__ == '__main__':
    main()
