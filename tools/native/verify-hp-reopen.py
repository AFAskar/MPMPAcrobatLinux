#!/usr/bin/env python3
"""Fresh native edit after the actual Reader HP/removal/progression roundtrip."""
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
    assert reference['passed'] and len(reference['phases']) == 5
    source = Path(reference['final_save']['pdf'])
    expected = reference['phases'][-1]['state']
    level = expected['fields']['Character Level']
    hp_before = expected['fields']['HP Max']
    hp_after = str(int(hp_before) + (12 // 2 - int(expected['fields']['Con']) // 2) * int(level))
    profile = module('profile', 'reader-hp-workflow.py')
    style = module('style', 'default-style-persistence.py')
    field_state = module('field_state', 'field-state-comparison.py')
    code = profile.original_blur(source)
    observer = (ROOT / 'tools/native/hp-workflow-observer.js').read_text()
    folder = ROOT / 'output/testing' / ('hp-final-native-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(a.reader.resolve()), 'input': str(source),
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'comparison': 'All observed loaded state except trace, which is reset in each fresh runtime; all original field/action values retained.'}
    def script(text):
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(text) + ");__host.command('RunUserScript(false)')"}
    summary = "(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    saved = folder / 'native-edited.pdf'
    restore = "var iFileName='Restore HP action.js';tDoc.getField('Con').setAction('OnBlur'," + json.dumps(code) + ');'
    steps = [{'op': 'advance', 'ms': 4100}, script(profile.setup(code)), script(observer),
             {'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(folder / 'loaded-diagnostic.pdf')},
             {'op': 'user-edit', 'field': 'Con', 'value': '12'}, {'op': 'advance', 'ms': 1000}, script(observer),
             {'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(folder / 'edited-diagnostic.pdf')},
             script(restore), {'op': 'eval', 'code': "Value('User Script','');Value('PC Name','HP compatibility')"},
             {'op': 'save', 'path': str(saved)}]
    scenario = folder / 'scenario.json'
    scenario.write_text(json.dumps({'steps': steps}))
    try:
        with (folder / 'probe.log').open('w') as log:
            result = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(folder / 'probe.json')],
                                    stdout=log, stderr=log, timeout=300, env=dict(os.environ))
        data = json.loads((folder / 'probe.json').read_text())
        assert result.returncode == 0 and data['passed'] and not data['diagnostics']['errors']
        assert not data['diagnostics']['console']['messages']
        loaded = style.saved_capture(folder / 'loaded-diagnostic.pdf', data['stages'][3]['result'], source)
        assert loaded['trace'] == [] and loaded == dict(expected, trace=[]), (loaded, expected)
        after = style.saved_capture(folder / 'edited-diagnostic.pdf', data['stages'][8]['result'], source)
        assert after['fields']['HP Max'] == hp_after and after['fields']['Con'] == '12'
        assert after['fields']['Character Level'] == level and after['fields']['HD1 Level'] == level
        assert after['mapping'].split(',')[3] == 'fixed' and after['feats'] == loaded['feats']
        assert after['trace'] == [{'name': 'Blur', 'type': 'Field', 'target': 'Con', 'before': hp_before, 'after': hp_after}]
        assert not after['errors']
        assert tuple(after['fields'][n] for n in ['HP Current', 'HP Temp', 'HD1 Used']) == ('30', '5', '2')
        field_state.compare(saved, after['fields'])
        report['visible'] = inspect(saved, {n: after['fields'][n] for n in ['HP Max', 'HP Current', 'Con', 'Con Mod']})
        assert report['visible']['passed'] and script_hashes(saved) == script_hashes(source)
        assert profile.original_blur(saved) == code
        report.update(loaded=loaded, edited=after, pdf=str(saved), passed=True)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'reopen.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
