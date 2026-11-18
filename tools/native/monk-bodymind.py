#!/usr/bin/env python3
from pathlib import Path
import sys, json, subprocess, os, time, copy, hashlib, importlib.util
import argparse
root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description='Six-state original 2024 Monk Body and Mind application/removal and cold persistence. Requires a pending level20 structural Monk/unarmed source with base18 scores and the retained workflow diagnostic timer. Not full class qualification.')
parser.add_argument('--input', type=Path, required=True)
parser.add_argument('--binary', type=Path, default=root / 'target/debug/mpmb-reader')
parser.add_argument('--pdfium', type=Path)
args = parser.parse_args()
folder = root / 'output/testing' / ('bodymind-workflow-' + str(time.time_ns()))
folder.mkdir()
sys.path[:0] = [str(root / 'tools/native'), str(root / 'tools/acrobat')]
import fighter_additional_diagnostics as diag
import subclass_audit_qualification as qual
from verify import inspect, script_hashes

def module(name, file):
    s = importlib.util.spec_from_file_location(name, root / 'tools/native' / file)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m
style = module('body_style', 'default-style-persistence.py')
fields = module('body_fields', 'field-state-comparison.py')
summary = module('body_summary', 'fighter-styles.py').SUMMARY
observer = (root / 'tools/native/monk-bodymind-observer.js').read_text()
source = args.input.resolve()
binary = args.binary.resolve()
report = {'passed': False, 'input': str(source), 'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'observer_sha256': hashlib.sha256(observer.encode()).hexdigest(), 'phases': [], 'scope': 'Explicit original ability-dialog Body and Mind application/removal, readiness-gated derived fields and cold saves; native only until Reader/mixed qualification.'}
steps = []
captures = []

def install():
    return [{'op': 'advance', 'ms': 5100}, {'op': 'eval', 'code': "Value('User Script'," + json.dumps(observer) + ");__host.command('RunUserScript(false)')"}]

def capture(label, level, score, ac, hit, damage):
    steps.extend([{'op': 'advance', 'ms': 1100}, {'op': 'eval', 'code': "if(!app.calculate||!calculate||delay)throw Error('Not ready');"}, {'op': 'eval', 'code': diag.native_request()}, {'op': 'eval', 'code': summary}])
    pdf = folder / (label + '-diagnostic.pdf')
    captures.append((label, len(steps) - 1, pdf, level, score, ac, hit, damage))
    steps.append({'op': 'save', 'path': str(pdf)})

def call(code):
    command = 'Value("User Script",' + json.dumps(code) + ');__host.command("RunUserScript(false)")' if code == 'AbilityScores_Button();' else '__host.command(' + json.dumps(code) + ')'
    steps.extend([{'op': 'eval', 'code': command}, {'op': 'advance', 'ms': 1100}])

def clean(name):
    pdf = folder / (name + '.pdf')
    steps.extend([{'op': 'eval', 'code': "Value('PC Name','Monk Body and Mind workflow');Value('User Script','');"}, {'op': 'save', 'path': str(pdf)}])
    return pdf

def run(label, input, dialogs):
    spec = folder / (label + '-scenario.json')
    probe = folder / (label + '-probe.json')
    spec.write_text(json.dumps({'steps': steps, 'dialogs': dialogs}))
    env = dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / (label + '-dialogs')))
    if args.pdfium:
        env['MPMB_PDFIUM'] = str(args.pdfium.resolve())
    with (folder / (label + '.log')).open('w') as log:
        p = subprocess.run([str(binary), str(input), '--probe', str(spec), str(probe)], stdout=log, stderr=log, timeout=900, env=env)
    d = json.load(open(probe))
    msgs = d['diagnostics']['console']['messages']
    assert [m['text'] for m in msgs] == ['MPMB 2024 Monk Body and Mind workflow sentinel'], msgs
    strict = copy.deepcopy(d)
    strict['diagnostics']['console']['messages'] = []
    checked = qual.qualify_probe(p.returncode, strict)
    assert checked['passed'], checked
    for name, index, pdf, level, score, ac, hit, damage in captures:
        state = style.saved_capture(pdf, d['stages'][index]['result'], source)
        assert d['stages'][index - 1]['result'] == diag.DONE + str([x[0] for x in captures].index(name) + 1)
        assert not state['errors'] and state['calculation'] == {'app': True, 'doc': True, 'delay': False}
        f = state['fields']
        assert (f['Character Level'], f['Dex'], f['Wis'], f['AC'], f['Attack.1.To Hit'], f['Attack.1.Damage']) == (str(level), str(score), str(score), str(ac), '+' + str(hit), damage), (name, f)
        canonical = fields.compare(pdf, f)
        visible = canonical['independent']
        assert visible['passed'] and script_hashes(pdf) == script_hashes(source)
        report['phases'].append({'label': name, 'pdf': str(pdf), 'state': state, 'canonical': canonical, 'visible': visible, 'qualification': checked})
        (folder / 'progress.json').write_text(json.dumps(report, indent=2))
try:
    steps = install()
    captures = []
    capture('pending20', 20, 18, 18, 10, '1d12+4')
    call('AbilityScores_Button();')
    capture('applied20', 20, 22, 22, 12, '1d12+6')
    applied = clean('applied20')
    run('apply20', source, [{'title': 'ABILITY SCORES DIALOG', 'result': 'ok'}])
    steps = install()
    captures = []
    capture('cold20', 20, 22, 22, 12, '1d12+6')
    call("ApplyClasses('Monk (Warrior of Shadow) 1',false)")
    capture('removed-before-score-apply1', 1, 22, 22, 8, '1d6+6')
    call('AbilityScores_Button();')
    capture('removed-applied1', 1, 18, 18, 6, '1d6+4')
    removed = clean('removed1')
    run('remove1', applied, [{'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}, {'title': 'ABILITY SCORES DIALOG', 'result': 'ok'}])
    steps = install()
    captures = []
    capture('final-cold1', 1, 18, 18, 6, '1d6+4')
    final = clean('final')
    run('final', removed, [])
    assert len(report['phases']) == 6
    report.update(passed=True, pdf=str(final))
except Exception as e:
    report['error'] = str(e)
    raise
finally:
    (folder / 'bodymind.json').write_text(json.dumps(report, indent=2))
    print(folder, flush=True)
