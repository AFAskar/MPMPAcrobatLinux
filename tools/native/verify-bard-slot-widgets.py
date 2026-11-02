#!/usr/bin/env python3
"""Check actual saved checkbox appearance states for the Bard slot roundtrips.

Field values alone cannot prove that a checked slot is drawn as checked. This
requires each visible widget's AS and its checked appearance. Reader may omit an
Off stream entirely, which means no checkbox mark is drawn; record that directly.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]


def widgets(path, expected):
    reader = PdfReader(path)
    rows = []
    for page_number, page in enumerate(reader.pages):
        for reference in page.get('/Annots', []):
            node = reference.get_object()
            chain = [node]
            while chain[-1].get('/Parent'):
                chain.append(chain[-1]['/Parent'].get_object())
            name = '.'.join(str(n['/T']) for n in reversed(chain) if n.get('/T'))
            if name not in expected or int(node.get('/F', 0)) & 34:
                continue
            state = '/' + expected[name]
            normal = node['/AP']['/N'].get_object()
            assert node.get('/AS') == state, ('Wrong checkbox AS', path, name, node.get('/AS'), state)
            on = normal['/True'].get_object().get_data()
            off = normal['/Off'].get_object().get_data() if '/Off' in normal else None
            assert on and on != off, ('Missing/distinct checkbox appearance', name)
            if state != '/Off':
                assert normal[state].get_object().get_data(), ('Missing checked appearance', name)
            rows.append({'name': name, 'page': page_number + 1, 'AS': str(node['/AS']),
                         'on_sha256': hashlib.sha256(on).hexdigest(),
                         'off_sha256': hashlib.sha256(off).hexdigest() if off is not None else None,
                         'off_representation': 'explicit stream' if off is not None else 'absent: no appearance',
                         'appearance_keys': list(normal)})
    assert {r['name'] for r in rows} == set(expected), 'Visible slot widgets missing'
    assert len(rows) == len(expected), 'Duplicate visible slot widgets'
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    args = parser.parse_args()
    reader = json.loads(args.reader.read_text())
    native = json.loads(args.native.read_text())
    assert reader['passed'] and native['passed']
    assert Path(native['reader']).resolve() == args.reader.resolve()
    folder = ROOT / 'output/testing' / ('bard-slot-widget-comparison-' + str(time.time_ns()))
    folder.mkdir()
    report = {'passed': False, 'scope': __doc__, 'reader': str(args.reader),
              'native': str(args.native), 'cases': []}
    try:
        for engine, phases in [('reader', reader['phases']), ('native', native['phases'])]:
            for phase in phases:
                reference = next(p for p in reader['phases'] if p['label'] == phase['label'])
                expected = {n: reference['fields'][n] for n in reader['boxes']}
                path = Path(phase['pdf'])
                rows = widgets(path, expected)
                report['cases'].append({'engine': engine, 'label': phase['label'],
                                        'pdf': str(path), 'widgets': rows})
        assert len(report['cases']) == 12
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'widgets.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
