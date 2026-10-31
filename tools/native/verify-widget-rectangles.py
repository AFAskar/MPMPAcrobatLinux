#!/usr/bin/env python3
"""Check isolated rect rejection/active restore and saved widget geometry.

Pass Reader observation.json and native comparison.json from the same observer.
The generic comparator verifies exact API/ASCII-carrier/scripts. This adds
explicit behavioral assertions and independent saved PDF geometry checks.
It qualifies this API slice only, not original MPMB table workflows.
"""
import argparse
import json
import sys
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import canonical_fields


def rectangles(path, name):
    reader = PdfReader(path)
    field = reader.get_object(canonical_fields(reader)[name]['reference'])
    widgets = field.get('/Kids', [field])
    return [[float(n) for n in widget.get_object()['/Rect']] for widget in widgets]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reader', type=Path)
    parser.add_argument('native', type=Path)
    args = parser.parse_args()
    reference = json.loads(args.reader.read_text())
    native = json.loads(args.native.read_text())
    assert reference['passed'] and native['passed'] and native['exact_observations_equal']
    assert Path(native['reader']).resolve() == args.reader.resolve()
    cases = reference['captured']['cases']
    assert not reference['captured'].get('errors', [])
    assert [case['field'] for case in cases] == ['Age', 'Height']
    for case in cases:
        pages = case['page'] if isinstance(case['page'], list) else [case['page']]
        assert pages[0] == -1
        error = {'ok': False, 'name': 'InvalidSetError', 'message': 'Set not possible, invalid or unknown.'}
        assert case['parent'] == case['inactive'] == error
        if len(pages) > 1:
            assert len(pages) == 2 and pages[1] >= 0
            assert case['activeAfterRejected'] == case['activeRestored'] == case['activeBefore']
            expected = case['activeBefore'].copy()
            expected[0] += 1; expected[2] += 1
            assert case['activeChanged'] == expected
            assert case['activeSet'] == case['activeRestore'] == {'ok': True}
        else:
            assert case['activeAbsent'] is True
        original = rectangles(reference['input'], case['field'])
        assert len(original) == len(pages)
        for saved in [args.reader.parent / 'reader.pdf', args.native.parent / 'native.pdf']:
            actual = rectangles(saved, case['field'])
            assert actual[0] == original[0], (saved, case['field'], 'inactive mutated')
            assert len(actual) == len(original)
            if len(original) > 1:
                assert all(abs(a-b) <= 1/65536 for a, b in zip(actual[1], original[1])), (saved, case['field'], 'active not restored')
    report = args.native.parent / 'widget-rectangles.json'
    report.write_text(json.dumps({'passed': True, 'scope': __doc__, 'reader': str(args.reader.resolve()), 'native': str(args.native.resolve()), 'fields': [case['field'] for case in cases]}, indent=2) + '\n')
    print(report)


if __name__ == '__main__':
    main()
