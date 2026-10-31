#!/usr/bin/env python3
"""Read-only comparison of rebuilt borderless plain-text origins with Reader.

Checks one active widget, not complete glyph advances or rendered equality.
Both appearances must use untransformed first text origins; this diagnostic
refuses transformed appearances rather than guessing their coordinates.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from pypdf import PdfReader
from pypdf.generic import ContentStream
from verify import canonical_fields, script_hashes


def measure(path, field):
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    reader = PdfReader(path)
    fields = canonical_fields(reader)
    node = reader.get_object(fields[field]['reference'])
    ids = {ref.get_object().indirect_reference.idnum for ref in node.get('/Kids', [node])}
    active = [ref.get_object() for page in reader.pages for ref in page.get('/Annots', []) if ref.idnum in ids]
    assert len(active) == 1, 'Expected exactly one active widget'
    widget = active[0]
    width = widget['/BS'].get('/W', 1) if '/BS' in widget else widget.get('/Border', [0, 0, 1])[2]
    assert width == 0, 'Widget is not explicitly borderless'
    ap = widget['/AP']['/N'].get_object()
    assert list(ap.get('/Matrix', [1, 0, 0, 1, 0, 0])) == [1, 0, 0, 1, 0, 0]
    operations = ContentStream(ap, reader).operations
    first = next(i for i, (_, op) in enumerate(operations) if op in [b'Tm', b'Td'])
    assert not any(op == b'cm' for _, op in operations[:first]), 'Transformed appearance needs separate qualification'
    operands, operator = operations[first]
    if operator == b'Tm':
        assert list(operands[:4]) == [1, 0, 0, 1]
    origin = list(map(float, operands[4:6] if operator == b'Tm' else operands[:2]))
    fonts = [str(ref.get_object().get('/BaseFont')) for ref in ap['/Resources']['/Font'].values()]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    return {'path': str(path.resolve()), 'sha256': before, 'origin': origin,
            'rect': list(map(float, widget['/Rect'])), 'value': str(fields[field]['/V']), 'fonts': fonts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native', type=Path)
    parser.add_argument('reader', type=Path)
    parser.add_argument('--field', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = {'passed': False, 'scope': __doc__, 'field': args.field}
    try:
        native, reader = (measure(path, args.field) for path in [args.native, args.reader])
        report.update(native=native, reader=reader, tolerance_points=0.001,
                      normalization='Canonical text: CR/CRLF to LF only; geometry/origins: absolute point tolerance.')
        normalized = lambda value: value.replace('\r\n', '\n').replace('\r', '\n')
        checks = {'text': normalized(native['value']) == normalized(reader['value']),
                  'rebuilt_native_font': any(name.startswith('/MPMB') for name in native['fonts']),
                  'rect': all(abs(a-b) < 0.001 for a, b in zip(native['rect'], reader['rect'])),
                  'horizontal_origin': abs(native['origin'][0] - reader['origin'][0]) < 0.001,
                  'baseline': abs(native['origin'][1] - reader['origin'][1]) < 0.001,
                  'original_scripts': script_hashes(args.native) == script_hashes(args.reader)}
        report['checks'] = checks
        assert all(checks.values()), checks
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    finally:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(args.report)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
