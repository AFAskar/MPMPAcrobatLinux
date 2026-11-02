#!/usr/bin/env python3
"""Fresh native reopens of every native/Reader expertise phase, followed by edits.

Checks complete saved choice/menu/field state, then an original Dexterity edit,
visible skill totals, proficiency/expertise widget states and retained scripts.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect, script_hashes


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


field_state = module('field_state', 'field-state-comparison.py')
widget_state = module('widget_state', 'verify-bard-slot-widgets.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--reader', type=Path, required=True)
    parser.add_argument('--reader-interoperability', type=Path, help='Only reopen this actual Reader-edited native expertise9 save, then change Dexterity16 to18')
    args = parser.parse_args()
    native = json.loads(args.native.read_text())
    reader = json.loads(args.reader.read_text())
    assert native['passed'] and reader['passed']
    assert Path(reader['native']).resolve() == args.native.resolve()
    observer = (ROOT / 'tools/native/bard-expertise-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == native['observer_sha256'] == reader['observer_sha256']
    folder = ROOT / 'output/testing' / ('bard-expertise-reopens-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'native': str(args.native), 'reader': str(args.reader),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'cases': []}
    phases = native['phases']
    target_dex, target_modifier = ('18', '4') if args.reader_interoperability else ('16', '3')
    interoperability = None
    if args.reader_interoperability:
        interoperability = json.loads(args.reader_interoperability.read_text())
        assert interoperability['passed'] and interoperability['observer_sha256'] == native['observer_sha256']
        assert interoperability['pre_values'] == {'Dex': '16'}
        phase = next(p for p in phases if p['label'] == 'expertise9')
        assert Path(interoperability['input']).resolve() == Path(phase['pdf']).resolve()
        expected = {**phase['state'], 'fields': {**phase['state']['fields'],
                    'Dex': '16', 'Dex Mod': '3', 'Acr': str(int(phase['state']['fields']['Acr']) + 1)}}
        assert interoperability['captured'] == expected
        displays = {**phase['displays'], 'Acr': ['+' + str(int(v) + 1) for v in phase['displays']['Acr']]}
        phases = [{**phase, 'state': expected, 'displays': displays}]
        report['reader_interoperability'] = str(args.reader_interoperability)

    def capture(steps):
        steps.extend([{'op': 'eval', 'code': "Value('User Script'," + json.dumps(observer) + ')'},
                      {'op': 'eval', 'code': "__host.command('RunUserScript(false)')"}])
        index = len(steps)
        steps.append({'op': 'eval', 'code': "JSON.parse(getField('PC Name').valueAsString)"})
        steps.append({'op': 'advance', 'ms': 1000})
        return index

    try:
        for phase in phases:
            counterpart = next(p for p in reader['phases'] if p['label'] == phase['label'])
            inputs = [('reader-interoperability', args.reader_interoperability.parent / 'reader.pdf')] if interoperability else [('native', Path(phase['pdf'])), ('reader', Path(counterpart['pdf']))]
            for engine, source in inputs:
                label = phase['label'] + '-' + engine
                before = hashlib.sha256(source.read_bytes()).hexdigest()
                output = folder / (label + '.pdf')
                steps = [{'op': 'advance', 'ms': 4100}]
                loaded_index = capture(steps)
                steps.extend([{'op': 'edit', 'field': 'Dex', 'value': target_dex}, {'op': 'advance', 'ms': 1000}])
                edited_index = capture(steps)
                steps.extend([{'op': 'edit', 'field': 'PC Name', 'value': 'Bard compatibility'},
                              {'op': 'save', 'path': str(output)}])
                scenario = folder / (label + '.json')
                evidence = folder / (label + '-probe.json')
                scenario.write_text(json.dumps({'steps': steps, 'alerts': [1] * 20,
                                               'dialogs': [{'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}] * 8}))
                with (folder / (label + '.log')).open('w') as log:
                    process = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)],
                                             stdout=log, stderr=log, timeout=360)
                data = json.loads(evidence.read_text())
                assert process.returncode == 0 and data['passed'] and not data['diagnostics']['errors']
                loaded = data['stages'][loaded_index]['result']
                edited = data['stages'][edited_index]['result']
                # saved_capture verifies and removes this transport marker. The
                # immediate native JSON parse retains it, so verify it at that
                # boundary before comparing the unchanged MPMB state.
                assert 'sentinel' not in phase['state']
                assert loaded.pop('sentinel') == '\u00a0\u2028\U0001f600'
                assert edited.pop('sentinel') == '\u00a0\u2028\U0001f600'
                assert loaded == phase['state'], ('Saved expertise state changed on load', label)
                expected = {**phase['state'], 'fields': {**phase['state']['fields'],
                            'Dex': target_dex, 'Dex Mod': target_modifier,
                            'Acr': str(int(phase['state']['fields']['Acr']) + 1)}}
                assert edited == expected, ('Original ability edit changed unrelated state', label)
                displays = {}
                for name, previous in phase['displays'].items():
                    checked = inspect(output, {name: edited['fields'][name]})
                    displays[name] = [w['appearance_text'] for w in checked['widgets'] if w['visible']]
                    wanted = ['+' + str(int(value) + 1) for value in previous] if name == 'Acr' else previous
                    assert displays[name] == wanted, ('Edited calculated skill total differs', label, name)
                raw = field_state.compare(output, edited['fields'])
                boxes = {n: value for n, value in edited['fields'].items() if n.endswith((' Prof', ' Exp'))}
                actual_widgets = widget_state.widgets(output, boxes)
                assert script_hashes(output) == script_hashes(source)
                assert hashlib.sha256(source.read_bytes()).hexdigest() == before
                report['cases'].append({'label': label, 'source': str(source), 'source_sha256': before,
                                        'loaded_equal': True, 'transport_sentinels_verified': True,
                                        'edited': edited, 'displays': displays,
                                        'api_raw_comparison': raw, 'checkbox_appearances': actual_widgets, 'output': str(output)})
                print(label, 'PASS', flush=True)
        assert len(report['cases']) == (1 if interoperability else 8)
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
