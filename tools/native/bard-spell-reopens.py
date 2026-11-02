#!/usr/bin/env python3
"""Reopen each native/Reader Bard spell phase and edit/regenerate its real list.

Complete selected spell fields must load unchanged. Subsequent original ability
actions and generation must retain choices and recalculate healing/attack/DC.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect, script_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--reader-edit', type=Path, help='Only check this Reader-edited native generated sheet, then change Charisma to14')
    args = parser.parse_args()
    reader = json.loads(args.reader.read_text())
    native = json.loads(args.native.read_text())
    comparison = json.loads(args.comparison.read_text())
    assert reader['passed'] and native['passed'] and comparison['passed']
    assert Path(comparison['reader']).resolve() == args.reader.resolve()
    assert Path(comparison['native']).resolve() == args.native.resolve()
    folder = ROOT / 'output/testing' / ('bard-spell-reopens-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(args.reader),
              'native': str(args.native), 'comparison': str(args.comparison),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'cases': []}
    cases = []
    target_cha, target_modifier = ('14', 2) if args.reader_edit else ('12', 1)
    if args.reader_edit:
        edited = json.loads(args.reader_edit.read_text())
        assert edited['passed'] and Path(edited['native']).resolve() == args.native.resolve()
        phase = next(p for p in native['phases'] if p['state']['phase'] == 'regenerated')
        assert hashlib.sha256(Path(phase['pdf']).read_bytes()).hexdigest() == edited['source_sha256']
        assert edited['loaded'] == phase['state']['fields']
        state = {**phase['state'], 'fields': edited['edited'], 'phase': 'reader-edited-native-generation'}
        cases.append((state, 'reader', Path(edited['pdf'])))
        report['reader_edit'] = str(args.reader_edit)
    else:
        for entry in native['phases']:
            state = entry['state']
            reference = next(p for p in reader['phases'] if p['label'] == state['phase'])
            cases.extend([(state, 'native', Path(entry['pdf'])), (state, 'reader', Path(reference['pdf']))])
    try:
        for state, engine, source in cases:
            label = state['phase']
            names = list(state['fields'])
            read = "(function(){var r={};" + json.dumps(names) + ".forEach(function(n){r[n]=getField(n).valueAsString});return r})()"
            name = label + '-' + engine
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            output = folder / (name + '.pdf')
            scenario = folder / (name + '.json')
            evidence = folder / (name + '-probe.json')
            scenario.write_text(json.dumps({'dialogs': [
                {'title': 'SPELL SELECTION DIALOG', 'result': 'ok'},
                {'title': 'SPELL LIST GENERATION DIALOG', 'result': 'ok'}],
                'alerts': [1] * 30, 'steps': [
                    {'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': read},
                    {'op': 'edit', 'field': 'Cha', 'value': target_cha},
                    {'op': 'advance', 'ms': 1000},
                    {'op': 'eval', 'code': "__host.command('GenerateSpellSheet()')"},
                    {'op': 'advance', 'ms': 1000}, {'op': 'eval', 'code': read},
                    {'op': 'save', 'path': str(output)}]}))
            with (folder / (name + '.log')).open('w') as log:
                process = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)],
                                         stdout=log, stderr=log, timeout=360)
            data = json.loads(evidence.read_text())
            assert process.returncode == 0 and data['passed'] and not data['diagnostics']['errors']
            loaded = data['stages'][1]['result']
            edited = data['stages'][-2]['result']
            assert loaded == state['fields'], ('Loaded spell fields differ', name)
            prefix = state['prefix']
            assert edited[prefix + 'spellshead.dc.0'] == 'DC ' + str(11 + target_modifier)
            assert edited[prefix + 'spellshead.attack.0'] == '+' + str(3 + target_modifier)
            for row in state['rows']:
                assert edited[row['remember']] == state['fields'][row['remember']]
                if row['key'] in ['healing word', 'cure wounds']:
                    assert '+' + str(target_modifier) + ' (Cha)' in edited[row['description']]
            checked = inspect(output, edited)
            assert checked['actual'] == edited and checked['widgets'] and all(w['matches'] for w in checked['widgets'])
            assert script_hashes(output) == script_hashes(source)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before
            report['cases'].append({'label': name, 'source': str(source), 'source_sha256': before,
                                    'loaded_equal': True, 'edited': edited, 'output': str(output)})
            print(name, 'PASS', flush=True)
        assert len(report['cases']) == (1 if args.reader_edit else 8)
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'reopens.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
