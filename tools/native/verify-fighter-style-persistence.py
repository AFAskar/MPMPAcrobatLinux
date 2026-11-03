#!/usr/bin/env python3
"""Fresh native style/gear edits from native and actual Reader outputs.

Each origin traverses three fresh runtimes: Archery attack cycling, Defense armor
cycling, then Dueling melee/ranged cycling. Real original menu callbacks and field
actions must rebuild the changed numbers; retained old appearances are insufficient.
"""
import argparse
import hashlib
import importlib.util
import json
import os
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--reader', type=Path, required=True)
    a = p.parse_args()
    native = json.loads(a.native.read_text())
    reader = json.loads(a.reader.read_text())
    assert native['passed'] and reader['passed']
    observer = (ROOT / 'tools/native/fighter-style-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == native['observer_sha256'] == reader['observer_sha256']
    profile = module('profile', 'fighter-styles.py')
    style = module('style', 'default-style-persistence.py')
    fields = module('fields', 'field-state-comparison.py')
    wanted = {p['label']: p['state'] for p in native['phases']}
    assert wanted == {p['label']: p['state'] for p in reader['phases']}
    folder = ROOT / 'output/testing' / ('fighter-style-persistence-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'native': str(a.native.resolve()), 'reader': str(a.reader.resolve()),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'cases': []}
    def script(text):
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(text) + ");__host.command('RunUserScript(false)')"}
    def run(source, label, mode):
        captures = []
        steps = [{'op': 'advance', 'ms': 4100}, script(profile.SETUP)]
        dialogs = []
        def edit(n, v):
            steps.extend([{'op': 'user-edit', 'field': n, 'value': v}, {'op': 'advance', 'ms': 1000}])
        def choose(name):
            steps.extend([{'op': 'eval', 'code': "__host.command('ClassFeatureOptions()')"}, {'op': 'advance', 'ms': 1000}])
            dialogs.extend([{'title': 'MPMB menu', 'button_path': ['Champion', 'Fighting Style', name]},
                            {'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}])
        def capture(expected):
            steps.append(script(observer))
            index = len(steps)
            diagnostic = folder / (label + '-' + str(len(captures)) + '-diagnostic.pdf')
            steps.extend([{'op': 'eval', 'code': profile.SUMMARY}, {'op': 'save', 'path': str(diagnostic)}])
            captures.append((expected, index, diagnostic))
        if mode == 'archery':
            capture('archery')
            edit('Attack.1.Weapon Selection', 'Longsword')
            # Archery must stop applying to melee; this intentionally has no
            # matching original phase, so use the measured baseline minus shield.
            melee = json.loads(json.dumps(wanted['baseline']))
            melee.update(choice='archery')
            melee['fields'].update({'AC': '18', 'AC Shield Bonus': '', 'AC Shield Bonus Description': ''})
            capture(melee)
            edit('Attack.1.Weapon Selection', 'Longbow')
            capture('archery')
            choose('Defense')
            capture('defense')
        elif mode == 'defense':
            capture('defense')
            edit('AC Armor Description', 'Unarmored')
            capture('defense-unarmored')
            edit('AC Armor Description', 'Plate')
            capture('defense-armored-again')
            choose('Dueling')
            edit('AC Shield Bonus Description', 'Shield')
            edit('Attack.1.Weapon Selection', 'Longsword')
            capture('dueling')
        else:
            capture('dueling')
            edit('AC Shield Bonus Description', '')
            edit('Attack.1.Weapon Selection', 'Longbow')
            capture('dueling-ranged')
            choose('Archery')
            capture('archery')
        saved = folder / (label + '.pdf')
        steps.extend([{'op': 'eval', 'code': "Value('User Script','');Value('PC Name','Fighter compatibility')"}, {'op': 'save', 'path': str(saved)}])
        scenario = folder / (label + '-scenario.json')
        scenario.write_text(json.dumps({'steps': steps, 'dialogs': dialogs}))
        with (folder / (label + '.log')).open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(folder / (label + '-probe.json'))],
                                  stdout=log, stderr=log, timeout=480,
                                  env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / (label + '-dialogs'))))
        data = json.loads((folder / (label + '-probe.json')).read_text())
        assert proc.returncode == 0 and data['passed'], data.get('error')
        assert not data['diagnostics']['errors'] and not data['diagnostics']['console']['messages']
        case = {'label': label, 'input': str(source), 'pdf': str(saved), 'states': []}
        for expected, index, diagnostic in captures:
            state = style.saved_capture(diagnostic, data['stages'][index]['result'], source)
            target = wanted[expected] if isinstance(expected, str) else expected
            assert state == target, (label, expected, state, target)
            fields.compare(diagnostic, dict(state['fields'], **state['resources']))
            visible = inspect(diagnostic, {n: state['fields'][n] for n in ['AC', 'Attack.1.To Hit', 'Attack.1.Damage', 'Attack.1.Weapon']})
            assert visible['passed'], visible
            case['states'].append({'expected': expected if isinstance(expected, str) else 'archery-melee', 'state': state, 'pdf': str(diagnostic)})
        assert script_hashes(saved) == script_hashes(source)
        report['cases'].append(case)
        return saved
    try:
        for engine, input_pdf in [('native', Path(native['pdf'])), ('reader', Path(reader['pdf']))]:
            first = run(input_pdf, engine + '-archery-reopened', 'archery')
            second = run(first, engine + '-defense-reopened', 'defense')
            run(second, engine + '-dueling-reopened', 'dueling')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'persistence.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
