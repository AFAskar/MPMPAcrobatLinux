#!/usr/bin/env python3
"""Compare a genuine HP-menu/Constitution user commit with actual Reader.

Legacy mode exercises the existing page-click/edit/page-click path, so its old
engine counterexample does not rely on calling a newly introduced host API.
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
    p.add_argument('--binary', type=Path, default=ROOT / 'target/debug/mpmb-reader')
    p.add_argument('--mode', choices=['user-commit', 'legacy-widget-switch'], default='user-commit')
    a = p.parse_args()
    reference = json.loads(a.reader.read_text())
    assert reference['passed']
    source = Path(reference['input'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == reference['input_sha256']
    profile = module('profile', 'reader-hp-workflow.py')
    style = module('style', 'default-style-persistence.py')
    field_state = module('field_state', 'field-state-comparison.py')
    code = profile.original_blur(source)
    assert hashlib.sha256(code.encode()).hexdigest() == reference['original_blur_sha256']
    observer = (ROOT / 'tools/native/hp-workflow-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == reference['observer_sha256']
    folder = ROOT / 'output/testing' / ('hp-workflow-comparison-' + str(time.time_ns()))
    folder.mkdir()
    binary = folder / 'mpmb-reader'
    shutil.copy2(a.binary, binary)
    print(folder, flush=True)
    report = {'passed': False, 'scope': __doc__, 'reader': str(a.reader.resolve()), 'mode': a.mode,
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'phases': [], 'reopens': []}
    summary = "(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    def script(text):
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(text) + ");__host.command('RunUserScript(false)')"}
    steps = [{'op': 'advance', 'ms': 4100}, script(profile.setup(code))]
    steps += [{'op': 'edit', 'field': n, 'value': v} for n, v in {'HP Current': '30', 'HP Temp': '5', 'HD1 Used': '2'}.items()]
    steps.append(script(profile.MENU))
    captures = []
    def capture(label):
        steps.append(script(observer))
        index = len(steps)
        diagnostic = folder / (label + '-diagnostic.pdf')
        steps.extend([{'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(diagnostic)}])
        captures.append((label, index, diagnostic))
    capture('auto-fixed')
    if a.mode == 'legacy-widget-switch':
        steps.extend([{'op': 'eval', 'code': "__host.activate('Con')"}, {'op': 'edit', 'field': 'Con', 'value': '16'},
                      {'op': 'eval', 'code': "__host.activate('Int')"}])
    else:
        steps.append({'op': 'user-edit', 'field': 'Con', 'value': '16'})
    steps.append({'op': 'advance', 'ms': 1000})
    capture('constitution-user-commit')
    steps.extend([{'op': 'edit', 'field': 'Feat Name 1', 'value': 'Tough'}, {'op': 'advance', 'ms': 1000}])
    capture('tough')
    output = folder / 'native.pdf'
    restore = "var iFileName='Restore HP action.js';tDoc.getField('Con').setAction('OnBlur'," + json.dumps(code) + ');'
    steps.extend([script(restore), {'op': 'eval', 'code': "Value('User Script','');Value('PC Name','HP compatibility')"}, {'op': 'save', 'path': str(output)}])
    scenario = folder / 'scenario.json'
    scenario.write_text(json.dumps({'steps': steps, 'dialogs': [
        {'title': 'MPMB menu', 'button_path': ['Set the Max HP to automatically assume', 'The total HP using fixed values (57)']},
        {'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}]}))
    try:
        with (folder / 'probe.log').open('w') as log:
            result = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(folder / 'probe.json')],
                                    stdout=log, stderr=log, timeout=360,
                                    env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / 'dialogs')))
        data = json.loads((folder / 'probe.json').read_text())
        assert result.returncode == 0 and data['passed'] and not data['diagnostics']['errors'], data.get('error')
        assert not data['diagnostics']['console']['messages']
        expected = {p['label']: p['state'] for p in reference['phases']}
        for label, index, diagnostic in captures:
            state = style.saved_capture(diagnostic, data['stages'][index]['result'], source)
            report['phases'].append({'label': label, 'state': state})
            assert state == expected[label], (label, state, expected[label])
        state = report['phases'][-1]['state']
        report['canonical'] = field_state.compare(output, state['fields'])
        report['visible'] = inspect(output, {n: state['fields'][n] for n in ['HP Max', 'HP Current', 'HP Temp', 'Con', 'Con Mod']})
        assert report['visible']['passed'] and script_hashes(output) == script_hashes(source)
        assert profile.original_blur(output) == code
        report['output'] = str(output)
        # Both saved engines must retain automatic mode and the Tough callback.
        for engine, input_pdf in [('native', output), ('reader', Path(reference['pdf']))]:
            diagnostic = folder / (engine + '-reopened-diagnostic.pdf')
            saved = folder / (engine + '-reopened-edited.pdf')
            spec = folder / (engine + '-reopen-scenario.json')
            spec.write_text(json.dumps({'steps': [{'op': 'advance', 'ms': 4100}, script(profile.setup(code)),
                {'op': 'user-edit', 'field': 'Con', 'value': '18'}, {'op': 'advance', 'ms': 1000}, script(observer),
                {'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(diagnostic)}, script(restore),
                {'op': 'eval', 'code': "Value('User Script','');Value('PC Name','HP compatibility')"},
                {'op': 'save', 'path': str(saved)}]}))
            probe = folder / (engine + '-reopened-probe.json')
            with (folder / (engine + '-reopened.log')).open('w') as log:
                result = subprocess.run([str(binary), str(input_pdf), '--probe', str(spec), str(probe)], stdout=log, stderr=log, timeout=300)
            reopened = json.loads(probe.read_text())
            assert result.returncode == 0 and reopened['passed'] and not reopened['diagnostics']['errors']
            after = style.saved_capture(diagnostic, reopened['stages'][5]['result'], source)
            assert not after['errors'] and after['fields']['HP Max'] == '102' and after['fields']['Con'] == '18'
            assert after['mapping'].split(',')[3] == 'fixed' and after['feats'] == state['feats']
            assert after['trace'] and all(e['name'] == 'Blur' and e['target'] == 'Con' for e in after['trace'])
            assert profile.original_blur(saved) == code and script_hashes(saved) == script_hashes(source)
            field_state.compare(saved, after['fields'])
            assert inspect(saved, {n: after['fields'][n] for n in ['HP Max', 'Con', 'Con Mod']})['passed']
            report['reopens'].append({'engine': engine, 'pdf': str(saved), 'state': after})
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
