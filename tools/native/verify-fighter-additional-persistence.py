#!/usr/bin/env python3
"""Changed compound-style saves and fresh native reopens from both engines.

The primary Archery and additional Dueling choices must survive a bow change
and a cold return to longsword. Checks the actual additional feature key and all
observed fields/resources. Other styles/classes and full progression remain open.
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
    parser.add_argument('--native', type=Path, required=True)
    origins = parser.add_mutually_exclusive_group(required=True)
    origins.add_argument('--reader', type=Path)
    origins.add_argument('--native-only', action='store_true', help='Native pilot; no Reader persistence claim')
    parser.add_argument('--reader-reopen', type=Path,
                        help='Also edit and cold-reopen the qualified native-to-Reader outputs')
    args = parser.parse_args()
    native = json.loads(args.native.read_text())
    reader = json.loads(args.reader.read_text()) if args.reader else None
    assert native['passed']
    mode = native.get('diagnostic_mode', 'repeated-RunUserScript')
    assert mode in (diagnostics.MODE, 'repeated-RunUserScript')
    if mode == diagnostics.MODE:
        assert native.get('diagnostic_helper_sha256') == hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()
    wanted = {p['label']: p['state'] for p in native['phases']}
    if reader:
        assert reader['passed'] and wanted == {p['label']: p['state'] for p in reader['phases']}
        assert reader.get('diagnostic_mode', 'repeated-RunUserScript') == mode
        if mode == diagnostics.MODE:
            assert reader['diagnostic_helper_sha256'] == native['diagnostic_helper_sha256']
    observer = (ROOT / 'tools/native/fighter-additional-observer.js').read_text()
    observer_hash = hashlib.sha256(observer.encode()).hexdigest()
    assert observer_hash == native['observer_sha256']
    if reader:
        assert observer_hash == reader['observer_sha256']
    profile = module('profile', 'fighter-styles.py')
    style = module('style', 'default-style-persistence.py')
    fields = module('fields', 'field-state-comparison.py')
    sword = wanted['reselected-extra-17']
    # A fresh user edit preserves its exact typed weapon casing; class
    # recalculation in the progression profile had rewritten it to lowercase.
    typed_sword = wanted['extra-dueling-sword']
    bow = json.loads(json.dumps(wanted['extra-dueling-bow']))
    bow['fields'].update({'AC': '20', 'AC Shield Bonus': '2', 'AC Shield Bonus Description': 'Shield',
                          'Attack.1.Weapon': 'Longbow'})
    reopened = json.loads(args.reader_reopen.read_text()) if args.reader_reopen else None
    if reopened:
        assert reader and reopened['passed']
        assert Path(reopened['native']).resolve() == args.native.resolve()
        assert reopened['diagnostic_mode'] == mode
        assert reopened['diagnostic_helper_sha256'] == native['diagnostic_helper_sha256']
        assert {p['label']: p['state'] for p in reopened['phases']} == {
            'compound-loaded-17': sword, 'compound-bow-17': bow,
            'compound-cold-bow-17': bow, 'compound-cold-sword-17': typed_sword,
            'native-cold-9': wanted['cold-9'],
            'native-restored-17': wanted['restored-17'],
            'native-reselected-extra-17': sword,
        }
    folder = ROOT / 'output/testing' / ('fighter-additional-persistence-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'native': str(args.native.resolve()),
              'reader': str(args.reader.resolve()) if args.reader else None,
              'reader_reopen': str(args.reader_reopen.resolve()) if args.reader_reopen else None,
              'reader_reopen_qualified': False,
              'native_only_pilot': args.native_only, 'reader_origin_qualified': False,
              'diagnostic_mode': mode,
              'diagnostic_helper_sha256': hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest(),
              'observer_sha256': observer_hash,
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'cases': []}

    def script(text):
        if mode == diagnostics.MODE:
            if text == observer:
                return {'op': 'eval', 'code': diagnostics.native_request()}
            if text == profile.SETUP:
                text = diagnostics.install(text, observer)
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(text) + ");__host.command('RunUserScript(false)')"}

    def run(source, label, before, weapon, after):
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        steps = [{'op': 'advance', 'ms': 4100}, script(profile.SETUP)]
        captures = []

        def capture(expected):
            steps.append(script(observer))
            index = len(steps)
            pdf = folder / (label + '-' + str(len(captures)) + '-diagnostic.pdf')
            steps.extend([{'op': 'eval', 'code': profile.SUMMARY}, {'op': 'save', 'path': str(pdf)}])
            captures.append((expected, index, pdf))

        capture(before)
        steps.extend([{'op': 'user-edit', 'field': 'Attack.1.Weapon Selection', 'value': weapon},
                      {'op': 'advance', 'ms': 1000}])
        capture(after)
        output = folder / (label + '.pdf')
        steps.extend([{'op': 'eval', 'code': "Value('User Script','');Value('PC Name','Champion additional style compatibility')"},
                      {'op': 'save', 'path': str(output)}])
        scenario = folder / (label + '-scenario.json')
        scenario.write_text(json.dumps({'steps': steps}))
        evidence = folder / (label + '-probe.json')
        with (folder / (label + '.log')).open('w') as log:
            process = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)],
                                     stdout=log, stderr=log, timeout=480,
                                     env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / (label + '-dialogs'))))
        probe = json.loads(evidence.read_text())
        assert process.returncode == 0 and probe['passed'], probe.get('error')
        assert not probe['diagnostics']['errors'] and not probe['diagnostics']['console']['messages']
        if mode == diagnostics.MODE:
            markers = [s['result'] for s in probe['stages'] if isinstance(s.get('result'), str) and s['result'].startswith(diagnostics.DONE)]
            assert markers == [diagnostics.DONE + str(i + 1) for i in range(len(captures))]
        case = {'label': label, 'input': str(source), 'input_sha256': source_hash,
                'output': str(output), 'probe': str(evidence), 'states': []}
        for expected, index, pdf in captures:
            state = style.saved_capture(pdf, probe['stages'][index]['result'], source)
            assert not state['errors'] and state == expected, (label, state, expected)
            canonical = fields.compare(pdf, dict(state['fields'], **state['resources']))
            visible = inspect(pdf, {n: state['fields'][n] for n in ['AC', 'Attack.1.To Hit', 'Attack.1.Damage', 'Attack.1.Weapon']})
            assert visible['passed'] and script_hashes(pdf) == script_hashes(source)
            case['states'].append({'state': state, 'pdf': str(pdf), 'canonical': canonical, 'visible': visible})
        assert script_hashes(output) == script_hashes(source)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        report['cases'].append(case)
        return output

    try:
        inputs = [('native', Path(native['pdf']), sword, 'Longbow', bow, 'Longsword', typed_sword)]
        if reader:
            inputs.append(('reader', Path(reader['pdf']), sword, 'Longbow', bow, 'Longsword', typed_sword))
        if reopened:
            inputs.extend([
                ('mixed-reader-bow', Path(reopened['bow_pdf']), bow, 'Longsword', typed_sword, 'Longbow', bow),
                ('mixed-reader-sword', Path(reopened['sword_pdf']), typed_sword, 'Longbow', bow, 'Longsword', typed_sword),
                ('mixed-reader-progressed', Path(reopened['pdf']), sword, 'Longbow', bow, 'Longsword', typed_sword),
            ])
        for engine, source, before, weapon, after, restore_weapon, restored in inputs:
            changed = run(source, engine + '-changed', before, weapon, after)
            run(changed, engine + '-cold-restored', after, restore_weapon, restored)
        report['passed'] = True
        report['reader_origin_qualified'] = bool(reader)
        report['reader_reopen_qualified'] = bool(reopened)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'persistence.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
