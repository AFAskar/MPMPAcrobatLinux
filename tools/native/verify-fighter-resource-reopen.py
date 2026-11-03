#!/usr/bin/env python3
"""Changed native resource saves/reopens after both real Reader resource chains.

Two measured rested Champion17 origins each traverse three fresh runtimes:
spend → original short reset → original long reset, with exact Reader states.
This does not qualify full rest healing or other classes/resource profiles.
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
    p.add_argument('--reader', type=Path, required=True)
    p.add_argument('--roundtrip', type=Path, required=True)
    a = p.parse_args()
    reader = json.loads(a.reader.read_text())
    roundtrip = json.loads(a.roundtrip.read_text())
    assert reader['passed'] and roundtrip['passed']
    assert reader['observer_sha256'] == roundtrip['observer_sha256']
    wanted = {v['label']: v['state'] for v in reader['phases']}
    assert roundtrip['cases'][0]['states'][-1]['state'] == wanted['long-rest']
    observer = (ROOT / 'tools/native/fighter-style-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == reader['observer_sha256']
    profile = module('profile', 'fighter-styles.py')
    style = module('style', 'default-style-persistence.py')
    fields = module('fields', 'field-state-comparison.py')
    folder = ROOT / 'output/testing' / ('fighter-resource-final-native-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(a.reader.resolve()), 'roundtrip': str(a.roundtrip.resolve()),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'cases': []}
    def script(text):
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(text) + ");__host.command('RunUserScript(false)')"}
    def run(source, label, actions, before, after):
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        steps = [{'op': 'advance', 'ms': 4100}, script(profile.SETUP)]
        captures = []
        def capture(expected):
            steps.append(script(observer))
            index = len(steps)
            diagnostic = folder / (label + '-' + str(len(captures)) + '-diagnostic.pdf')
            steps.extend([{'op': 'eval', 'code': profile.SUMMARY}, {'op': 'save', 'path': str(diagnostic)}])
            captures.append((expected, index, diagnostic))
        capture(before)
        for action in actions:
            steps.extend([action, {'op': 'advance', 'ms': 1000}])
        capture(after)
        output = folder / (label + '.pdf')
        steps.extend([{'op': 'eval', 'code': "Value('User Script','');Value('PC Name','Fighter resource compatibility')"}, {'op': 'save', 'path': str(output)}])
        scenario = folder / (label + '-scenario.json')
        scenario.write_text(json.dumps({'steps': steps, 'dialogs': [{'result': 'ok'}] * 20}))
        evidence = folder / (label + '-probe.json')
        with (folder / (label + '.log')).open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)], stdout=log, stderr=log,
                                  timeout=480, env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / (label + '-dialogs'))))
        data = json.loads(evidence.read_text())
        assert proc.returncode == 0 and data['passed'], data.get('error')
        assert not data['diagnostics']['errors'] and not data['diagnostics']['console']['messages']
        case = {'label': label, 'input': str(source), 'input_sha256': source_hash, 'probe': str(evidence), 'output': str(output), 'states': []}
        for expected, index, diagnostic in captures:
            state = style.saved_capture(diagnostic, data['stages'][index]['result'], source)
            assert not state['errors'] and state == expected, (label, state, expected)
            canonical = fields.compare(diagnostic, dict(state['fields'], **state['resources']))
            visible = inspect(diagnostic, {n: state['fields'][n] for n in ['AC', 'Attack.1.To Hit', 'Attack.1.Damage', 'Attack.1.Weapon']})
            assert visible['passed']
            case['states'].append({'state': state, 'pdf': str(diagnostic), 'canonical': canonical, 'visible': visible})
        assert script_hashes(output) == script_hashes(source)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        report['cases'].append(case)
        return output
    try:
        origins = [('reader-progression', Path(reader['pdf'])),
                   ('reader-native-roundtrip', Path(roundtrip['cases'][0]['final_save']['pdf']))]
        for label, source in origins:
            edits = [{'op': 'user-edit', 'field': 'Limited Feature Used ' + str(row), 'value': value}
                     for row, value in [(1, '1'), (2, '2'), (3, '2')]]
            spent = run(source, label + '-spent', edits, wanted['long-rest'], wanted['spent-17'])
            short = run(spent, label + '-short', [{'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('short rest')\")"}],
                        wanted['spent-17'], wanted['short-rest'])
            run(short, label + '-long', [{'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('long rest')\")"}],
                wanted['short-rest'], wanted['long-rest'])
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'reopen.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
