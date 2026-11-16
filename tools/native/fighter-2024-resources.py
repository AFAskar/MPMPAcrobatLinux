#!/usr/bin/env python3
"""2024 Champion resource breakpoints, partial rests and changed cold saves.

Original class/rest functions, programmatic Field.value spending and default
feature replies. Fighting-style, mastery, feats/ASI, HP/combat and actual native
keyboard choices remain separate. Requires a disclosed startup observer input.
"""
import argparse
import copy
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
sys.path.insert(0, str(ROOT/'tools/acrobat'))
from verify import inspect, script_hashes
import fighter_additional_diagnostics as diagnostics
import subclass_audit_qualification as qualification


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools/native'/file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--instrumentation', type=Path, required=True)
    parser.add_argument('--binary', type=Path, default=ROOT/'target/debug/mpmb-reader')
    args = parser.parse_args()
    source = args.input.resolve()
    manifest = json.loads(args.instrumentation.read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest['passed'] and manifest['mode'] == 'startup-script-timer'
    assert Path(manifest['input']).resolve() == source and manifest['input_sha256'] == sha(source)
    assert manifest['observer_sha256'] == sha(ROOT/'tools/native/fighter-2024-resource-observer.js')
    assert manifest['diagnostic_helper_sha256'] == sha(Path(diagnostics.__file__))
    folder = ROOT/'output/testing'/('native-fighter-2024-resources-'+str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder/'mpmb-reader'
    shutil.copy2(args.binary.resolve(), binary)
    report = {'passed': False, 'reader_qualified': False, 'scope': __doc__,
              'input': str(source), 'input_sha256': sha(source),
              'instrumentation': str(args.instrumentation.resolve()),
              'binary_sha256': sha(binary), 'phases': [], 'probe_qualifications': []}
    style = module('fighter_style', 'default-style-persistence.py')
    profile = module('fighter_profile', 'fighter-styles.py')
    fields = module('fighter_fields', 'field-state-comparison.py')
    steps, captures = [], []

    def start():
        return [{'op': 'advance', 'ms': 5100}, {'op': 'assert', 'values': {
            'User Script': '// MPMB workflow observer installed'}}], []

    def call(code):
        steps.extend([{'op': 'eval', 'code': '__host.command('+json.dumps(code)+')'},
                      {'op': 'advance', 'ms': 1000}])

    def level(value):
        call("ApplyClasses('Fighter (Champion) "+str(value)+"',false)")

    def spend(name, value):
        # Resolve actual labels/rows after progression; do not assume row counts.
        code = "(function(){for(var i=0;i<numFields;i++){var n=getNthFieldName(i),m=/^Limited Feature (\\d+)$/.exec(n);if(m&&getField(n).valueAsString.indexOf("+json.dumps(name)+")===0){getField('Limited Feature Used '+m[1]).value="+json.dumps(value)+";return;}}throw Error('Missing resource');})()"
        steps.append({'op': 'eval', 'code': code})

    def capture(label, value, used=None):
        steps.extend([{'op': 'advance', 'ms': 1000},
                      {'op': 'eval', 'code': diagnostics.native_request()},
                      {'op': 'eval', 'code': profile.SUMMARY}])
        pdf = folder/(label+'.pdf')
        captures.append((label, len(steps)-1, pdf, value, used or {}))
        steps.append({'op': 'save', 'path': str(pdf)})
        return pdf

    def run(label, pdf):
        scenario, probe = folder/(label+'-scenario.json'), folder/(label+'-probe.json')
        scenario.write_text(json.dumps({'steps': steps, 'dialogs': [
            {'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}]*16}))
        with (folder/(label+'.log')).open('w') as out:
            proc = subprocess.run([str(binary), str(pdf), '--probe', str(scenario), str(probe)],
                                  stdout=out, stderr=out, timeout=1200,
                                  env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder/(label+'-dialogs'))))
        data = json.loads(probe.read_text())
        messages = data['diagnostics']['console']['messages']
        assert [m['text'] for m in messages] == ['MPMB 2024 Fighter resource workflow console sentinel'], messages
        strict = copy.deepcopy(data)
        strict['diagnostics']['console']['messages'] = []
        checked = qualification.qualify_probe(proc.returncode, strict)
        report['probe_qualifications'].append(dict(checked, probe=str(probe), expected_console=messages))
        assert checked['passed'], checked
        markers = [s['result'] for s in data['stages'] if isinstance(s.get('result'), str)
                   and s['result'].startswith(diagnostics.DONE)]
        assert markers == [diagnostics.DONE+str(i+1) for i in range(len(captures))]
        for name, index, saved, n, used in captures:
            state = style.saved_capture(saved, data['stages'][index]['result'], source)
            assert not state['errors']
            assert state['identity'] == {'level': n, 'subclass': 'fighter-champion'}
            assert state['calculation'] == {'app': True, 'doc': True, 'delay': False}
            expected = {'Second Wind': (2 if n < 4 else 3 if n < 10 else 4, 'long rest')}
            if n >= 2:
                expected['Action Surge'] = (1 if n < 17 else 2, 'short rest')
            if n >= 9:
                expected['Indomitable'] = (1 if n < 13 else 2 if n < 17 else 3, 'long rest')
            actual = {}
            for row in state['rows']:
                names = [k for k in expected if row['name'].startswith(k)]
                assert len(names) == 1 and names[0] not in actual, (name, row)
                key = names[0]
                actual[key] = row
                assert (row['max'], row['recovery'], row['used']) == (
                    str(expected[key][0]), expected[key][1], used.get(key, '')), (name, row)
            assert set(actual) == set(expected)
            canonical = fields.compare(saved, dict(state['fields'], **state['resources']))
            visible = inspect(saved, state['resources'])
            assert visible['passed'] and script_hashes(saved) == script_hashes(source)
            for row in state['rows']:
                name_used = 'Limited Feature Used '+row['row']
                widgets = [w for w in visible['widgets'] if w['name'] == name_used and w['visible'] and w['page'] is not None]
                assert widgets and all((w['appearance_text'] or '').strip() == row['used'] for w in widgets)
            report['phases'].append({'label': name, 'pdf': str(saved), 'state': state,
                                     'canonical': canonical, 'visible': visible, 'probe': str(probe)})
            (folder/'progress.json').write_text(json.dumps(report, indent=2))

    try:
        steps, captures = start()
        for n in [1, 2, 3, 4, 5, 9, 10, 13, 17, 20, 1, 9]:
            level(n)
            capture('level'+str(n)+'-'+str(len(captures)), n)
        for name in ['Second Wind', 'Action Surge', 'Indomitable']:
            spend(name, '2' if name == 'Second Wind' else '1')
        capture('spent9', 9, {'Second Wind': '2', 'Action Surge': '1', 'Indomitable': '1'})
        call("resetLimFeaUsed('short rest')")
        capture('short9', 9, {'Second Wind': '1', 'Indomitable': '1'})
        call("resetLimFeaUsed('short rest')")
        capture('second-short9', 9, {'Second Wind': '0', 'Indomitable': '1'})
        call("resetLimFeaUsed('short rest')")
        capture('third-short9-no-extra', 9, {'Second Wind': '0', 'Indomitable': '1'})
        call("resetLimFeaUsed('long rest')")
        capture('long9', 9)
        level(17)
        capture('restored17', 17)
        for name, value in [('Second Wind', '3'), ('Action Surge', '2'), ('Indomitable', '3')]:
            spend(name, value)
        saved = capture('spent17', 17, {'Second Wind': '3', 'Action Surge': '2', 'Indomitable': '3'})
        run('workflow', source)
        steps, captures = start()
        capture('cold-spent17', 17, {'Second Wind': '3', 'Action Surge': '2', 'Indomitable': '3'})
        call("resetLimFeaUsed('short rest')")
        capture('cold-short17', 17, {'Second Wind': '2', 'Indomitable': '3'})
        call("resetLimFeaUsed('long rest')")
        capture('cold-long17', 17)
        level(1)
        capture('removed-resources1', 1)
        level(17)
        final = capture('restored-empty17', 17)
        run('cold', saved)
        steps, captures = start()
        capture('final-cold17', 17)
        run('final', final)
        assert len(report['phases']) == 25 and sha(source) == report['input_sha256']
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (folder/'resources.json').write_text(json.dumps(report, indent=2)+'\n')
        print(folder/'resources.json', flush=True)


if __name__ == '__main__':
    main()
