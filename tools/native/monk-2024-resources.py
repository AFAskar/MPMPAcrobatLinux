#!/usr/bin/env python3
"""Bounded2024 Shadow Monk Focus/Metabolism and unarmed progression.

Requires a disclosed all18-score structural input. Body and Mind remains pending;
explicit ability-dialog application, spell choices, initiative/healing and full
class/feat/ASI legality require separate qualification. Native only until Reader.
"""
from pathlib import Path
import argparse, sys, json, subprocess, shutil, os, copy, time, hashlib, importlib.util
root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input', type=Path, required=True)
parser.add_argument('--instrumentation', type=Path, required=True)
parser.add_argument('--binary', type=Path, required=True)
args = parser.parse_args()
folder = root / 'output/testing' / ('native-monk-2024-resources-' + str(time.time_ns()))
folder.mkdir()
print(folder, flush=True)
sys.path[:0] = [str(root / 'tools/acrobat'), str(root / 'tools/native')]
from verify import inspect, script_hashes, canonical_fields
from pypdf import PdfReader
import fighter_additional_diagnostics as diagnostics
import subclass_audit_qualification as qualification

def module(name, file):
    spec = importlib.util.spec_from_file_location(name, root / 'tools/native' / file)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
style = module('monk_style', 'default-style-persistence.py')
fields = module('monk_fields', 'field-state-comparison.py')
summary = module('monk_summary', 'fighter-styles.py').SUMMARY
source = args.input.resolve()
manifest = json.load(open(args.instrumentation))
source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
assert manifest['passed'] and manifest['mode'] == 'startup-script-timer' and (Path(manifest['input']).resolve() == source) and (manifest['input_sha256'] == source_sha)
assert manifest['observer_sha256'] == hashlib.sha256((root / 'tools/native/monk-2024-resource-observer.js').read_bytes()).hexdigest()
assert manifest['diagnostic_helper_sha256'] == hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()
wrapper = manifest['field_action_wrapper']
assert wrapper['original_sha256'] == '92a84010bdc2a82d1362723a396f1f558d5113149047582efd8647aef95d6ac3' and wrapper['original_occurrences'] == 1
action_reader = PdfReader(source)
action_node = action_reader.get_object(canonical_fields(action_reader)['Attack.1.Weapon Selection']['reference'])
action = action_node['/AA']['/V'].get_object()['/JS']
assert hashlib.sha256(str(action).encode()).hexdigest() == wrapper['wrapped_sha256']
binary = folder / 'mpmb-reader'
shutil.copy2(args.binary.resolve(), binary)
report = {'passed': False, 'scope': '2024 Shadow Monk resources plus original unarmed attack/AC progression; native-only until matched with real Reader. Does not qualify manual initiative/Metabolism healing or actual spell choices.', 'input': str(source), 'instrumentation': str(args.instrumentation.resolve()), 'input_sha256': source_sha, 'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'probe_qualifications': [], 'reader_qualified': False, 'ability_bonus_application': 'Body and Mind pending; input scores directly18, explicit application not covered', 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'phases': []}
steps = []
captures = []

def start():
    return ([{'op': 'advance', 'ms': 5100}, {'op': 'assert', 'values': {'User Script': '// MPMB workflow observer installed'}}], [])

def call(code):
    steps.extend([{'op': 'eval', 'code': '__host.command(' + json.dumps(code) + ')'}, {'op': 'advance', 'ms': 1000}])

def level(n):
    call("ApplyClasses('Monk (Warrior of Shadow) " + str(n) + "',false)")

def spend(name, value):
    code = '(function(){for(var i=0;i<numFields;i++){var n=getNthFieldName(i),m=/^Limited Feature (\\d+)$/.exec(n);if(m&&getField(n).valueAsString.indexOf(' + json.dumps(name) + ")===0){getField('Limited Feature Used '+m[1]).value=" + json.dumps(value) + ";return;}}throw Error('Missing resource');})()"
    steps.append({'op': 'eval', 'code': code})

def capture(label, n, used=None):
    steps.extend([{'op': 'advance', 'ms': 1000}, {'op': 'eval', 'code': diagnostics.native_request()}, {'op': 'eval', 'code': summary}])
    pdf = folder / (label + '.pdf')
    captures.append((label, len(steps) - 1, pdf, n, used or {}))
    steps.append({'op': 'save', 'path': str(pdf)})
    return pdf

def run(label, pdf):
    scenario = folder / (label + '-scenario.json')
    probe = folder / (label + '-probe.json')
    scenario.write_text(json.dumps({'steps': steps, 'dialogs': [{'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}] * 18}))
    with open(folder / (label + '.log'), 'w') as log:
        p = subprocess.run([str(binary), str(pdf), '--probe', str(scenario), str(probe)], stdout=log, stderr=log, timeout=1200, env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / (label + '-dialogs'))))
    data = json.load(open(probe))
    messages = data['diagnostics']['console']['messages']
    assert [m['text'] for m in messages] == ['MPMB 2024 Monk resource workflow console sentinel'], messages
    strict = copy.deepcopy(data)
    strict['diagnostics']['console']['messages'] = []
    q = qualification.qualify_probe(p.returncode, strict)
    assert q['passed'], q
    report['probe_qualifications'].append(dict(q, probe=str(probe), expected_console=messages))
    markers = [s['result'] for s in data['stages'] if isinstance(s.get('result'), str) and s['result'].startswith(diagnostics.DONE)]
    assert markers == [diagnostics.DONE + str(i + 1) for i in range(len(captures))]
    for label, index, saved, n, used in captures:
        state = style.saved_capture(saved, data['stages'][index]['result'], source)
        assert not state['errors']
        assert not state['weaponTraceOverflow']
        trace = state['weaponTrace']
        assert all((t['original_sha256'] == wrapper['original_sha256'] for t in trace))
        assert sum((t['phase'] == 'before' for t in trace)) == sum((t['phase'] == 'after' for t in trace))
        if label == 'weapon-edited3':
            assert any((t.get('field') == 'Attack.1.Weapon Selection' and t.get('value') == 'Unarmed strike' and (t['phase'] == 'before') for t in trace)) and any((t.get('field') == 'Attack.1.Weapon Selection' and t['phase'] == 'after' for t in trace))
        assert state['identity'] == {'level': n, 'subclass': 'monk-shadow'}
        assert state['calculation'] == {'app': True, 'doc': True, 'delay': False}
        expected = {'Focus Points': (n, 'short rest'), 'Uncanny Metabolism': (1, 'long rest')} if n >= 2 else {}
        actual = {}
        for row in state['rows']:
            keys = [k for k in expected if row['name'].startswith(k)]
            assert len(keys) == 1 and keys[0] not in actual, (label, row)
            k = keys[0]
            actual[k] = row
            assert (row['max'], row['recovery'], row['used']) == (str(expected[k][0]), expected[k][1], used.get(k, '')), (label, row)
        assert set(actual) == set(expected), (label, actual)
        f = state['fields']
        pb = int(f['Proficiency Bonus'])
        dex = int(f['Dex Mod'])
        wis = int(f['Wis Mod'])
        assert int(f['AC']) == 10 + dex + wis, (label, f)
        die = 6 if n < 5 else 8 if n < 11 else 10 if n < 17 else 12
        assert f['Attack.1.Damage'] == '1d' + str(die) + '+' + str(dex), (label, f)
        assert int(f['Attack.1.To Hit'].lstrip('+')) == pb + dex, (label, f)
        canonical = fields.compare(saved, dict(f, **state['resources']))
        visible = inspect(saved, dict(f, **state['resources']))
        assert visible['passed'] and script_hashes(saved) == script_hashes(source), (label, visible)
        report['phases'].append({'label': label, 'pdf': str(saved), 'state': state, 'canonical': canonical, 'visible': visible, 'probe': str(probe), 'qualification': q})
        (folder / 'progress.json').write_text(json.dumps(report, indent=2))
try:
    steps, captures = start()
    steps.append({'op': 'user-edit', 'field': 'Attack.1.Weapon Selection', 'value': 'Unarmed strike'})
    capture('weapon-edited3', 3)
    for n in [1, 2, 3, 5, 10, 11, 15, 17, 20, 1, 9]:
        level(n)
        capture('level' + str(n) + '-' + str(len(captures)), n)
    spend('Focus Points', '7')
    spend('Uncanny Metabolism', '1')
    capture('spent9', 9, {'Focus Points': '7', 'Uncanny Metabolism': '1'})
    call("resetLimFeaUsed('short rest')")
    capture('short9', 9, {'Uncanny Metabolism': '1'})
    call("resetLimFeaUsed('long rest')")
    capture('long9', 9)
    level(17)
    spend('Focus Points', '13')
    spend('Uncanny Metabolism', '1')
    saved = capture('spent17', 17, {'Focus Points': '13', 'Uncanny Metabolism': '1'})
    run('workflow', source)
    steps, captures = start()
    capture('cold-spent17', 17, {'Focus Points': '13', 'Uncanny Metabolism': '1'})
    call("resetLimFeaUsed('short rest')")
    capture('cold-short17', 17, {'Uncanny Metabolism': '1'})
    call("resetLimFeaUsed('long rest')")
    capture('cold-long17', 17)
    level(1)
    capture('removed1', 1)
    level(17)
    final = capture('restored17', 17)
    run('cold', saved)
    steps, captures = start()
    capture('final-cold17', 17)
    run('final', final)
    assert len(report['phases']) == 22 and hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
    report['passed'] = True
except Exception as e:
    report['error'] = str(e)
    raise
finally:
    (folder / 'resources.json').write_text(json.dumps(report, indent=2))
    print(folder / 'resources.json')
