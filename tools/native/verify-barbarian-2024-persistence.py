#!/usr/bin/env python3
"""Changed native saves after both Reader-origin and native-to-Reader Rage chains.

Each rested Reader output is spent, partially recovered, saved, cold-loaded and
fully recovered. Exact captured class/features/choices/resources are required.
This does not qualify HP healing, higher-level features or every Barbarian path.
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
import fighter_additional_diagnostics as diagnostics


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    parser.add_argument('--native-to-reader', type=Path, required=True)
    args = parser.parse_args()
    readers = [json.loads(p.read_text()) for p in [args.reader, args.native_to_reader]]
    assert all(r['passed'] for r in readers)
    assert [r['origin_mode'] for r in readers] == ['instrumented-baseline', 'native-spent']
    assert [len(r['phases']) for r in readers] == [8, 3]
    wanted = {p['label']: p['state'] for p in readers[0]['phases']}
    assert all(p['state'] == wanted[p['label']] for p in readers[1]['phases'])
    observer = ROOT / 'tools/native/barbarian-2024-observer.js'
    assert all(r['observer_sha256'] == hashlib.sha256(observer.read_bytes()).hexdigest() for r in readers)
    assert all(r['diagnostic_helper_sha256'] == hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest() for r in readers)
    profile = module('profile', 'fighter-styles.py')
    style = module('style', 'default-style-persistence.py')
    fields = module('fields', 'field-state-comparison.py')
    folder = ROOT / 'output/testing' / ('barbarian-2024-final-native-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    native = json.loads(Path(readers[0]['native']).read_text())
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == native['binary_sha256']
    report = {'passed': False, 'scope': __doc__, 'reader': str(args.reader.resolve()),
              'native_to_reader': str(args.native_to_reader.resolve()),
              'binary_sha256': native['binary_sha256'], 'cases': []}

    def run(source, label, actions, before, after):
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        steps = [{'op': 'advance', 'ms': 5100},
                 {'op': 'assert', 'values': {'User Script': '// MPMB workflow observer installed'}}]
        captures = []

        def capture(expected):
            steps.append({'op': 'eval', 'code': diagnostics.native_request()})
            index = len(steps)
            pdf = folder / (label + '-' + str(len(captures)) + '-diagnostic.pdf')
            steps.extend([{'op': 'eval', 'code': profile.SUMMARY}, {'op': 'save', 'path': str(pdf)}])
            captures.append((expected, index, pdf))

        capture(before)
        for action in actions:
            steps.extend([action, {'op': 'advance', 'ms': 1000}])
        capture(after)
        output = folder / (label + '.pdf')
        steps.extend([{'op': 'eval', 'code': "Value('User Script','');Value('PC Name','2024 Berserker resource compatibility')"},
                      {'op': 'save', 'path': str(output)}])
        scenario, evidence = folder / (label + '-scenario.json'), folder / (label + '-probe.json')
        scenario.write_text(json.dumps({'steps': steps, 'dialogs': []}))
        with (folder / (label + '.log')).open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)],
                                  stdout=log, stderr=log, timeout=480,
                                  env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / (label + '-dialogs'))))
        data = json.loads(evidence.read_text())
        assert proc.returncode == 0 and data['passed'], data.get('error')
        assert not data['diagnostics']['errors'], data['diagnostics']
        assert [m['text'] for m in data['diagnostics']['console']['messages']] == ['MPMB 2024 Barbarian workflow console sentinel']
        assert not list((folder / (label + '-dialogs')).glob('dialog-*.json')), 'Unexpected original dialog'
        markers = [s['result'] for s in data['stages'] if isinstance(s.get('result'), str) and s['result'].startswith(diagnostics.DONE)]
        assert markers == [diagnostics.DONE + '1', diagnostics.DONE + '2']
        case = {'label': label, 'input': str(source), 'input_sha256': source_hash,
                'probe': str(evidence), 'output': str(output), 'states': []}
        for expected, index, pdf in captures:
            state = style.saved_capture(pdf, data['stages'][index]['result'], source)
            assert not state['errors'] and state == expected, (label, state, expected)
            canonical = fields.compare(pdf, dict(state['fields'], **state['resources'], **state['reactions']))
            visible = inspect(pdf, {n: v for n, v in state['resources'].items() if v})
            assert visible['passed'] and script_hashes(pdf) == script_hashes(source)
            case['states'].append({'state': state, 'pdf': str(pdf), 'canonical': canonical, 'visible': visible})
        assert script_hashes(output) == script_hashes(source)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        report['cases'].append(case)
        (folder / 'progress.json').write_text(json.dumps(report, indent=2))
        return output

    try:
        for label, reader in zip(['reader-origin', 'native-reader-origin'], readers):
            partial = run(Path(reader['pdf']), label + '-partial', [
                {'op': 'user-edit', 'field': 'Limited Feature Used 1', 'value': '2'},
                {'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('short rest')\")"}],
                wanted['cold-long-rest3'], wanted['cold-short-rest3'])
            run(partial, label + '-cold-long', [
                {'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('long rest')\")"}],
                wanted['cold-short-rest3'], wanted['cold-long-rest3'])
        assert len(report['cases']) == 4
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        path = folder / 'reopen.json'
        path.write_text(json.dumps(report, indent=2) + '\n')
        print(path, flush=True)


if __name__ == '__main__':
    main()
