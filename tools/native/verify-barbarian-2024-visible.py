#!/usr/bin/env python3
"""Check visible Rage counters, including clearing, across the qualified chains.

The generic PDF inspector permits empty canonical values with retained APs.
This profile additionally rejects visible stale text after a usage reset. Its
negative control damages only a new native-output copy, never a Reader output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import canonical_fields, inspect, script_hashes


def counter_visibility(pdf, resources):
    result = inspect(pdf, resources)
    assert result['passed'], result
    assert resources['Limited Feature 1'].startswith('Rage ')
    value = resources['Limited Feature Used 1']
    rows = [w for w in result['widgets'] if w['name'] == 'Limited Feature Used 1'
            and w['visible'] and w['page'] is not None]
    assert rows, 'No visible Rage usage widget was checked'
    for row in rows:
        shown = row['appearance_text'] or ''
        if value:
            assert shown.strip() == value, ('Usage appearance differs', value, row)
        else:
            assert not shown.strip(), ('Cleared usage retains visible text', row)
    return {'resources': result, 'usage_widgets': rows,
            'scope': 'Exact nonempty usage text; blank usage permits absent AP or whitespace-only text. No font/pixel equality claim.'}


def full_name(widget):
    parts = []
    while widget:
        if '/T' in widget:
            parts.insert(0, str(widget['/T']))
        widget = widget.get('/Parent')
        if widget:
            widget = widget.get_object()
    return '.'.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['native', 'reader', 'native-to-reader', 'final-native']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    paths = [args.native, args.reader, args.native_to_reader, args.final_native]
    data = [json.loads(p.read_text()) for p in paths]
    assert all(d['passed'] for d in data)
    assert [len(d['phases']) for d in data[:3]] == [8, 8, 3]
    assert len(data[3]['cases']) == 4 and all(len(c['states']) == 2 for c in data[3]['cases'])
    assert data[1]['origin_mode'] == 'instrumented-baseline' and data[2]['origin_mode'] == 'native-spent'
    folder = ROOT / 'output/testing' / ('barbarian-2024-visible-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    report = {'passed': False, 'scope': __doc__, 'inputs': [str(p.resolve()) for p in paths], 'cases': []}
    try:
        phases = [(str(path), phase) for path, d in zip(paths[:3], data[:3]) for phase in d['phases']]
        phases += [(str(args.final_native), phase) for case in data[3]['cases'] for phase in case['states']]
        scripts = script_hashes(Path(data[0]['input']))
        for source, phase in phases:
            pdf = Path(phase['pdf'])
            resources = phase['state']['resources']
            checked = counter_visibility(pdf, resources)
            assert script_hashes(pdf) == scripts
            report['cases'].append({'source': source, 'label': phase.get('label'), 'pdf': str(pdf), 'checked': checked})
        assert len(report['cases']) == 27

        # Copy the real native spent AP over a cleared native counter. Canonical
        # /V stays empty, so this specifically proves stale AP detection.
        spent = next(p for p in data[0]['phases'] if p['label'] == 'spent3')
        cleared = next(p for p in data[0]['phases'] if p['label'] == 'long-rest3')
        spent_pdf, cleared_pdf = Path(spent['pdf']), Path(cleared['pdf'])
        original_hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in [spent_pdf, cleared_pdf]]
        source_reader = PdfReader(spent_pdf)
        field = canonical_fields(source_reader)['Limited Feature Used 1']
        appearance = source_reader.get_object(field['reference'])['/AP']
        writer = PdfWriter(clone_from=cleared_pdf)
        targets = [a.get_object() for page in writer.pages for a in page.get('/Annots', [])
                   if full_name(a.get_object()) == 'Limited Feature Used 1']
        assert targets
        for target in targets:
            target[NameObject('/AP')] = appearance.clone(writer)
        negative = folder / 'damaged-native-stale-counter.pdf'
        assert not negative.exists()
        writer.write(negative)
        assert canonical_fields(PdfReader(negative))['Limited Feature Used 1']['/V'] == ''
        assert inspect(negative, {'Limited Feature Used 1': ''})['passed'], 'Demonstrate the generic empty-value exemption'
        try:
            counter_visibility(negative, cleared['state']['resources'])
        except AssertionError as error:
            assert 'Cleared usage retains visible text' in str(error), error
            report['negative_control'] = {'pdf': str(negative), 'rejected': True, 'reason': str(error),
                                          'native_copy_only': True, 'canonical_usage_still_empty': True}
        else:
            raise AssertionError('Stale usage AP was not rejected')
        assert original_hashes == [hashlib.sha256(p.read_bytes()).hexdigest() for p in [spent_pdf, cleared_pdf]]
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (folder / 'visible.json').write_text(json.dumps(report, indent=2) + '\n')
        print(folder / 'visible.json', flush=True)


if __name__ == '__main__':
    main()
