#!/usr/bin/env python3
"""Fresh-native validation/edit after actual Reader score-dialog reopen changes."""
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
    reference = json.loads(a.reader.read_text())
    assert reference['passed'] and len(reference['phases']) == 2
    previous = reference['phases'][-1]
    source = Path(previous['pdf'])
    profile = module('profile', 'reader-resilient-feat.py')
    style = module('style', 'default-style-persistence.py')
    state_fields = module('state_fields', 'field-state-comparison.py')
    widgets = module('widgets', 'verify-bard-slot-widgets.py')
    observer = (ROOT / 'tools/native/resilient-feat-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == reference['observer_sha256']
    folder = ROOT / 'output/testing' / ('ability-final-native-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(a.reader.resolve()), 'input': str(source),
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    summary = "(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    def script(code):
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(code) + ");__host.command('RunUserScript(false)')"}
    output = folder / 'native-edited.pdf'
    steps = [{'op': 'advance', 'ms': 4100}, script(profile.SETUP), script(observer),
             {'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(folder / 'loaded-diagnostic.pdf')},
             script(profile.APPLY), {'op': 'advance', 'ms': 1000}, script(observer),
             {'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(folder / 'edited-diagnostic.pdf')},
             {'op': 'eval', 'code': "Value('User Script','');Value('PC Name','Feat compatibility')"},
             {'op': 'save', 'path': str(output)}]
    scenario = folder / 'scenario.json'
    scenario.write_text(json.dumps({'steps': steps, 'dialogs': [
        {'title': 'ABILITY SCORES DIALOG', 'event': '00Ws', 'values': {'00Ws': '19'}},
        {'title': 'ABILITY SCORES DIALOG', 'result': 'ok'}]}))
    try:
        with (folder / 'probe.log').open('w') as log:
            result = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(folder / 'probe.json')],
                                    stdout=log, stderr=log, timeout=300,
                                    env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / 'dialogs')))
        data = json.loads((folder / 'probe.json').read_text())
        assert result.returncode == 0 and data['passed'] and not data['diagnostics']['errors']
        assert not data['diagnostics']['console']['messages']
        loaded = style.saved_capture(folder / 'loaded-diagnostic.pdf', data['stages'][3]['result'], source)
        assert loaded == previous['state'], ('Fresh complete loaded state differs', loaded, previous['state'])
        state = style.saved_capture(folder / 'edited-diagnostic.pdf', data['stages'][8]['result'], source)
        assert not state['errors'] and state['feats'] == loaded['feats']
        assert tuple(state['fields'][n] for n in ['Wis', 'Wis ST Prof', 'Wis ST Mod', 'Perc']) == ('20', 'True', '9', '13')
        assert state['stats']['cols'][0]['scores'][4] == 19
        report['fields'] = state_fields.compare(output, state['fields'])
        report['visible'] = inspect(output, {n: state['fields'][n] for n in ['Wis', 'Wis Mod', 'Wis ST Mod', 'Perc']})
        assert report['visible']['passed'] and script_hashes(output) == script_hashes(source)
        report['checkboxes'] = widgets.widgets(output, {n: state['fields'][n] for n in ['Wis ST Prof', 'Perc Prof', 'Perc Exp']})
        report.update(loaded=loaded, edited=state, output=str(output), passed=True)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        path = folder / 'reopen.json'
        path.write_text(json.dumps(report, indent=2) + '\n')
        print(path, flush=True)


if __name__ == '__main__':
    main()
