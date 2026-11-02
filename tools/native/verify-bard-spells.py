#!/usr/bin/env python3
"""Compare selected Bard spell behavior, including pre-regeneration descriptions.

Only selection/row enumeration order is ignored. Field names and complete values,
spell keys, generated page prefix/count and offered labels remain exact. This
does not qualify all Bard spells, slot expenditure or other class spell lists.
"""
import argparse
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    args = parser.parse_args()
    reader = json.loads(args.reader.read_text())
    native = json.loads(args.native.read_text())
    assert reader['passed'] and native['passed']
    assert reader['source_sha256'] == native['source_sha256'], 'Different input PDFs'
    folder = ROOT / 'output/testing' / ('bard-spell-comparison-' + str(time.time_ns()))
    folder.mkdir()
    report = {'passed': False, 'scope': __doc__, 'reader': str(args.reader),
              'native': str(args.native), 'phases': []}
    try:
        offered = reader['offered']
        assert {key: offered[key] for key in ['cantrips', 'spells']} == native['offered']
        for entry in native['phases']:
            state = entry['state']
            matches = [p for p in reader['phases'] if p['label'] == state['phase']]
            assert len(matches) == 1
            reference = matches[0]['captured']
            checks = {
                'cantrips': sorted(state['cantrips']) == sorted(reference['selectedCantrips']),
                'spells': sorted(state['spells']) == sorted(reference['selectedSpells']),
                'prefix': state['prefix'] == reference['prefix'],
                'pages': state['pages'] == reference['pages'],
                'rows': sorted(state['rows'], key=lambda r: r['key']) ==
                        sorted(reference['rows'], key=lambda r: r['key']),
                'fields': state['fields'] == reference['fields'],
            }
            differences = {name: {'native': state['fields'].get(name),
                                  'reader': reference['fields'].get(name)}
                           for name in set(state['fields']) | set(reference['fields'])
                           if state['fields'].get(name) != reference['fields'].get(name)}
            report['phases'].append({'label': state['phase'], 'checks': checks,
                                     'field_differences': differences})
            assert all(checks.values()), ('Spell behavior differs', state['phase'], checks)
        assert len(report['phases']) == 4
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'comparison.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
