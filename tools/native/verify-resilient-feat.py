#!/usr/bin/env python3
"""Compare original Resilient/Wisdom and ability-dialog application/removal.

Complete captured API objects compare with object-member order ignored only.
Native and Reader-saved states then receive fresh original ability-dialog edits.
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
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect, canonical_fields, script_hashes


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reader', type=Path, required=True)
    p.add_argument('--binary', type=Path, default=ROOT / 'target/debug/mpmb-reader')
    a = p.parse_args()
    reference = json.loads(a.reader.read_text())
    assert reference['passed']
    source = Path(reference['input'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == reference['input_sha256']
    observer = (ROOT / 'tools/native/resilient-feat-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == reference['observer_sha256']
    style = module('style', 'default-style-persistence.py')
    field_state = module('field_state', 'field-state-comparison.py')
    folder = ROOT / 'output/testing' / ('resilient-feat-comparison-' + str(time.time_ns()))
    folder.mkdir()
    binary = folder / 'mpmb-reader'
    shutil.copy2(a.binary, binary)
    print(folder, flush=True)
    report = {'passed': False, 'scope': __doc__, 'reader': str(a.reader.resolve()),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'phases': [], 'reopens': []}
    summary = "(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"

    def script(code):
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(code) + ");__host.command('RunUserScript(false)')"}

    def run(label, input_pdf, steps, dialogs):
        scenario = folder / (label + '-scenario.json')
        scenario.write_text(json.dumps({'steps': steps, 'dialogs': dialogs}))
        output = folder / (label + '-probe.json')
        with (folder / (label + '.log')).open('w') as log:
            result = subprocess.run([str(binary), str(input_pdf), '--probe', str(scenario), str(output)],
                                    stdout=log, stderr=log, timeout=360,
                                    env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / (label + '-dialogs'))))
        data = json.loads(output.read_text())
        assert result.returncode == 0 and data['passed'] and not data['diagnostics']['errors'], data.get('error')
        assert not data['diagnostics']['console']['messages']
        return data

    steps = [{'op': 'advance', 'ms': 4100}, script(reference['setup_script']),
             {'op': 'edit', 'field': 'Feat Name 1', 'value': 'Resilient'}, {'op': 'advance', 'ms': 1000}]
    captures = []

    def capture(label):
        steps.append(script(observer))
        index = len(steps)
        diagnostic = folder / (label + '-diagnostic.pdf')
        output = folder / (label + '.pdf')
        steps.extend([{'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(diagnostic)},
                      {'op': 'eval', 'code': "Value('User Script','');Value('PC Name','Feat compatibility')"},
                      {'op': 'save', 'path': str(output)}])
        captures.append((label, index, diagnostic, output))

    capture('selected')
    steps.extend([script(reference['apply_script']), {'op': 'advance', 'ms': 1000}])
    capture('applied')
    steps.extend([{'op': 'edit', 'field': 'Feat Name 1', 'value': ''}, {'op': 'advance', 'ms': 1000}])
    capture('removed-pending')
    steps.extend([script(reference['apply_script']), {'op': 'advance', 'ms': 1000}])
    capture('removed-applied')
    dialogs = [{'title': 'ASK USER DIALOG', 'header': 'Select Resilient Type', 'result': 'ok', 'values': {'r004': True}},
               {'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}, {'title': 'ABILITY SCORES DIALOG', 'result': 'ok'},
               {'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}, {'title': 'ABILITY SCORES DIALOG', 'result': 'ok'}]
    phases = {p['label']: p for p in reference['phases']}
    try:
        data = run('main', source, steps, dialogs)
        for label, index, diagnostic, output in captures:
            state = style.saved_capture(diagnostic, data['stages'][index]['result'], source)
            assert state == phases[label]['state'], (label, state, phases[label]['state'])
            field_state.compare(output, state['fields'])
            visible = {n: state['fields'][n] for n in ['Wis', 'Wis Mod', 'Wis ST Mod', 'Perc']}
            checked = inspect(output, visible)
            assert checked['passed']
            report['phases'].append({'label': label, 'pdf': str(output), 'state': state, 'visible': checked})
        for label, _, _, native_pdf in captures:
            for engine, input_pdf in [('native', native_pdf), ('reader', Path(phases[label]['pdf']))]:
                key = engine + '-' + label
                diagnostic = folder / (key + '-reopened-diagnostic.pdf')
                output = folder / (key + '-reopened-edited.pdf')
                active = label in ['selected', 'applied']
                reopen_steps = [{'op': 'advance', 'ms': 4100}, script(reference['setup_script']),
                                script(reference['apply_script']), {'op': 'advance', 'ms': 1000}, script(observer),
                                {'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(diagnostic)},
                                {'op': 'eval', 'code': "Value('User Script','');Value('PC Name','Feat compatibility')"},
                                {'op': 'save', 'path': str(output)}]
                replies = [{'title': 'ABILITY SCORES DIALOG', 'event': '00Ws', 'values': {'00Ws': '15'}},
                           {'title': 'ABILITY SCORES DIALOG', 'result': 'ok'}]
                reopened = run(key, input_pdf, reopen_steps, replies)
                state = style.saved_capture(diagnostic, reopened['stages'][5]['result'], source)
                assert not state['errors']
                wanted = ('16', 'True', '7', '11') if active else ('15', 'Off', '2', '10')
                assert tuple(state['fields'][n] for n in ['Wis', 'Wis ST Prof', 'Wis ST Mod', 'Perc']) == wanted
                assert state['feats'] == phases[label]['state']['feats']
                assert state['stats']['cols'][0]['scores'][4] == 15
                field_state.compare(output, state['fields'])
                visible = {n: state['fields'][n] for n in ['Wis', 'Wis Mod', 'Wis ST Mod', 'Perc']}
                assert inspect(output, visible)['passed']
                assert script_hashes(output) == script_hashes(source)
                report['reopens'].append({'engine': engine, 'label': label, 'pdf': str(output), 'state': state})
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        path = folder / 'comparison.json'
        path.write_text(json.dumps(report, indent=2) + '\n')
        print(path, flush=True)


if __name__ == '__main__':
    main()
