#!/usr/bin/env python3
"""Negative controls for PDF evidence using disposable native outputs only.

Never modifies an original fixture or a Reader reference output, and never
writes expected reference values. Damaged copies must fail independent checks.
"""
import argparse, hashlib, json, sys, time
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect


def field_name(widget):
    chain = [widget]
    while chain[-1].get('/Parent'):
        chain.append(chain[-1]['/Parent'])
        if len(chain) > 64:
            raise RuntimeError('Field ancestry too deep')
    return '.'.join(str(n['/T']) for n in reversed(chain) if n.get('/T'))


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('native_report', type=Path); args = parser.parse_args()
    source_report = json.loads(args.native_report.read_text()); assert source_report['passed']
    case = source_report['cases'][0]; source = Path(case['output']); expected = case['expected']
    assert 'native-table-' in str(source), 'Negative controls require a disposable native table output'
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    folder = ROOT / 'output/testing' / ('verify-regressions-' + str(time.time_ns())); folder.mkdir(parents=True)
    report = {'passed': False, 'input': str(source), 'cases': []}
    try:
        baseline = inspect(source, expected); assert baseline['passed'], baseline
        report['cases'].append({'name': 'choice labels and inactive template widgets', 'passed': True, 'active_widgets': sum(w['page'] is not None for w in baseline['widgets']), 'template_widgets': sum(w['template'] is not None for w in baseline['widgets'])})
        for defect in ['missing-widget', 'missing-choice-appearance', 'wrong-export-value']:
            writer = PdfWriter(clone_from=source); found = False
            for page in writer.pages:
                annotations = page.get('/Annots', [])
                for ref in list(annotations):
                    widget = ref.get_object()
                    if field_name(widget) != 'Limited Feature Recovery 1':
                        continue
                    found = True
                    if defect == 'missing-widget':
                        page[NameObject('/Annots')] = ArrayObject(a for a in annotations if a != ref)
                    elif defect == 'missing-choice-appearance':
                        stream = DecodedStreamObject(); stream.set_data(b'q Q')
                        widget[NameObject('/AP')] = DictionaryObject({NameObject('/N'): writer._add_object(stream)})
                    else:
                        # Removing the actual stored value is damage, not an expected value.
                        widget.pop('/V', None)
                    break
                if found:
                    break
            assert found
            path = folder / (defect + '.pdf')
            with path.open('xb') as handle:
                writer.write(handle)
            result = inspect(path, expected)
            assert not result['passed'], defect + ' was incorrectly accepted'
            report['cases'].append({'name': defect, 'passed': True, 'damaged_copy': str(path)})
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
        report['passed'] = True
    finally:
        (folder / 'verification.json').write_text(json.dumps(report, indent=2)); print(folder / 'verification.json')

if __name__ == '__main__':
    main()
