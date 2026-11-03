#!/usr/bin/env python3
"""Fresh native changed saves and restores after the real Reader style roundtrip.

Each of three bounded Champion6 styles uses two fresh runtimes, with original
field actions, exact observed Reader states and independently rebuilt values.
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
    a = p.parse_args()
    reader = json.loads(a.reader.read_text())
    assert reader['passed'] and len(reader['cases']) == 3
    observer = (ROOT / 'tools/native/fighter-style-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == reader['observer_sha256']
    profile = module('profile', 'fighter-styles.py')
    style = module('style', 'default-style-persistence.py')
    fields = module('fields', 'field-state-comparison.py')
    folder = ROOT / 'output/testing' / ('fighter-style-final-native-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(a.reader.resolve()),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'cases': []}
    def script(text):
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(text) + ");__host.command('RunUserScript(false)')"}
    def run(source, label, edits, before, after):
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
        for edit in edits:
            steps.extend([{'op': 'user-edit', 'field': edit['field'], 'value': edit['value']}, {'op': 'advance', 'ms': 1000}])
        capture(after)
        output = folder / (label + '.pdf')
        steps.extend([{'op': 'eval', 'code': "Value('User Script','');Value('PC Name','Fighter compatibility')"}, {'op': 'save', 'path': str(output)}])
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
        for item in reader['cases']:
            states = [v['state'] for v in item['states']]
            assert len(states) == 3 and states[0] == states[2]
            negative = run(Path(item['final_save']['pdf']), item['style'] + '-changed', item['off_inputs'], states[2], states[1])
            run(negative, item['style'] + '-restored', item['on_inputs'], states[1], states[2])
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
