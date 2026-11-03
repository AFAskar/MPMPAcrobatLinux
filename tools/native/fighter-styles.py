#!/usr/bin/env python3
"""Original2014 Champion fighting-style choices, legal gear and conditional effects.

A bounded previously qualified Fighter6 input; complete class/option coverage and
Reader parity are separate gates. User inputs and offered menu choices only.
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


SETUP = "var iFileName='Fighter error observation.js';tDoc.__styleErrors=[];if(typeof displayError==='function'){tDoc.__styleOriginalError=displayError;displayError=function(e,s){try{tDoc.__styleErrors.push({error:String(e),context:String(s)})}catch(ignore){}return tDoc.__styleOriginalError.apply(this,arguments)}};"
PHASES = [
    ('baseline', '', '20', '+7', '1d8+4'),
    ('dueling', 'dueling', '20', '+7', '1d8+6'),
    ('dueling-ranged', 'dueling', '18', '+7', '1d8+4'),
    ('defense', 'defense', '19', '+7', '1d8+4'),
    ('defense-unarmored', 'defense', '14', '+7', '1d8+4'),
    ('defense-armored-again', 'defense', '19', '+7', '1d8+4'),
    ('archery', 'archery', '18', '+9', '1d8+4'),
]
SUMMARY = "(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    observer = (ROOT / 'tools/native/fighter-style-observer.js').read_text()
    style = module('style', 'default-style-persistence.py')
    field_state = module('field_state', 'field-state-comparison.py')
    folder = ROOT / 'output/testing' / ('native-fighter-styles-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'input': str(source), 'input_sha256': source_hash,
              'observer_sha256': hashlib.sha256(observer.encode()).hexdigest(),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'phases': []}
    def script(text):
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(text) + ");__host.command('RunUserScript(false)')"}
    steps = [{'op': 'advance', 'ms': 4100}, {'op': 'assert', 'values': {
        'Class and Levels': 'Fighter (Champion)', 'Character Level': '6', 'Str': '18', 'Dex': '18', 'Con': '12'}}, script(SETUP)]
    dialogs = []
    captures = []
    def edit(n, v):
        steps.extend([{'op': 'user-edit', 'field': n, 'value': v}, {'op': 'advance', 'ms': 1000}])
    def choose(name):
        steps.extend([{'op': 'eval', 'code': "__host.command('ClassFeatureOptions()')"}, {'op': 'advance', 'ms': 1000}])
        dialogs.extend([{'title': 'MPMB menu', 'button_path': ['Champion', 'Fighting Style', name]},
                        {'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}])
    def capture(label):
        steps.append(script(observer))
        index = len(steps)
        diagnostic = folder / (label + '-diagnostic.pdf')
        steps.extend([{'op': 'eval', 'code': SUMMARY}, {'op': 'save', 'path': str(diagnostic)}])
        captures.append((label, index, diagnostic))
    for n, v in [('AC Armor Description', 'Plate'), ('AC Shield Bonus Description', 'Shield'), ('Attack.1.Weapon Selection', 'Longsword')]:
        edit(n, v)
    capture('baseline')
    choose('Dueling')
    capture('dueling')
    edit('AC Shield Bonus Description', '')
    edit('Attack.1.Weapon Selection', 'Longbow')
    capture('dueling-ranged')
    choose('Defense')
    capture('defense')
    edit('AC Armor Description', 'Unarmored')
    capture('defense-unarmored')
    edit('AC Armor Description', 'Plate')
    capture('defense-armored-again')
    choose('Archery')
    capture('archery')
    output = folder / 'native-archery.pdf'
    steps.extend([{'op': 'eval', 'code': "Value('User Script','');Value('PC Name','Fighter compatibility')"}, {'op': 'save', 'path': str(output)}])
    scenario = folder / 'scenario.json'
    scenario.write_text(json.dumps({'steps': steps, 'dialogs': dialogs}))
    try:
        with (folder / 'probe.log').open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(folder / 'probe.json')],
                                  stdout=log, stderr=log, timeout=480,
                                  env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / 'dialogs')))
        data = json.loads((folder / 'probe.json').read_text())
        assert proc.returncode == 0 and data['passed'], data.get('error')
        assert not data['diagnostics']['errors'] and not data['diagnostics']['console']['messages']
        expected = {x[0]: x[1:] for x in PHASES}
        for label, index, diagnostic in captures:
            state = style.saved_capture(diagnostic, data['stages'][index]['result'], source)
            choice, ac, hit, damage = expected[label]
            assert not state['errors'] and state['identity']['level'] == 6 and state['identity']['subclass'].endswith('champion')
            assert state['choice'] == choice and not state['additional']
            assert tuple(state['fields'][n] for n in ['AC', 'Attack.1.To Hit', 'Attack.1.Damage']) == (ac, hit, damage)
            assert len(state['resources']) == 64
            fields = dict(state['fields'], **state['resources'])
            field_state.compare(diagnostic, fields)
            visible = inspect(diagnostic, {n: fields[n] for n in ['AC', 'Attack.1.To Hit', 'Attack.1.Damage', 'Attack.1.Weapon']})
            assert visible['passed'], visible
            report['phases'].append({'label': label, 'state': state, 'pdf': str(diagnostic), 'visible': visible})
        assert script_hashes(output) == script_hashes(source)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        report.update(passed=True, pdf=str(output))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'styles.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
