#!/usr/bin/env python3
from pathlib import Path
import sys, json, subprocess, os, time, hashlib, copy, importlib.util
import argparse
root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description='Original2024 Shadow Monk fixed-spell generation, DC/attack progression and Wisdom edits across three runtimes; bounded raw canonical and populated-AP verification. Not full Monk qualification.')
parser.add_argument('--input', type=Path, required=True)
parser.add_argument('--binary', type=Path, default=root / 'target/debug/mpmb-reader')
parser.add_argument('--pdfium', type=Path)
parser.add_argument('--restore-baseline', action='store_true', help='After cold load, perform original Wisdom18 and Shadow Monk3 actions before generation; for changed mixed-engine input')
parser.add_argument('--spent-regeneration', action='store_true', help='Three-state Focus2/Metabolism1 preservation through generation and cold reopen; requires an already generated level17/Wis18 source')
args = parser.parse_args()
assert not (args.restore_baseline and args.spent_regeneration)
folder = root / 'output/testing' / ('monk-shadow-spells-workflow-' + str(time.time_ns()))
folder.mkdir()
print(folder, flush=True)
sys.path[:0] = [str(root / 'tools/native'), str(root / 'tools/acrobat')]
import fighter_additional_diagnostics as diag
import subclass_audit_qualification as qual
from verify import script_hashes, canonical_fields, inspect
from pypdf import PdfReader

def module(n, f):
    s = importlib.util.spec_from_file_location(n, root / 'tools/native' / f)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m
style = module('shadow_style', 'default-style-persistence.py')
fields = module('shadow_fields', 'field-state-comparison.py')
summary = module('shadow_summary', 'fighter-styles.py').SUMMARY
observer = (root / 'tools/native/shadow-monk-spells-observer.js').read_text()
source = args.input.resolve()
binary = args.binary.resolve()
report = {'passed': False, 'restore_baseline': args.restore_baseline, 'scope': 'Original2024 Shadow Monk fixed spell dialogs/generation, level3/17 DC/attack and Wisdom changes across three runtimes; explicit Continue and Generate offered controls. Native only until Reader and changed mixed validation. Initial structural18 abilities are not legal feat/ASI construction.', 'input': str(source), 'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'verifier_sha256': hashlib.sha256((root / 'tools/native/verify-generated-fields.py').read_bytes()).hexdigest(), 'observer_sha256': hashlib.sha256(observer.encode()).hexdigest(), 'phases': []}
steps = []
captures = []
dialogs = []

def install():
    return [{'op': 'advance', 'ms': 5100}, {'op': 'eval', 'code': "Value('User Script'," + json.dumps(observer) + ");__host.command('RunUserScript(false)')"}]

def generate():
    steps.append({'op': 'eval', 'code': "Value('PC Name','Shadow Monk spells workflow');"})
    steps.extend([{'op': 'eval', 'code': "__host.command('GenerateSpellSheet()')"}, {'op': 'advance', 'ms': 1100}])
    dialogs.extend([{'title': 'SPELL SELECTION DIALOG', 'result': 'ok'}, {'title': 'SPELL LIST GENERATION DIALOG', 'result': 'ok'}])

def level(n):
    steps.extend([{'op': 'eval', 'code': '__host.command(' + json.dumps("ApplyClasses('Monk (Warrior of Shadow) " + str(n) + "',false)") + ')'}, {'op': 'advance', 'ms': 1100}])
    dialogs.append({'title': 'CHANGES ALERT DIALOG', 'result': 'ok'})

def wisdom(n):
    steps.extend([{'op': 'user-edit', 'field': 'Wis', 'value': str(n)}, {'op': 'advance', 'ms': 1100}])

def capture(label, lev, wis, dc, attack):
    steps.extend([{'op': 'eval', 'code': "if(!app.calculate||!calculate||delay)throw Error('Not ready');"}, {'op': 'eval', 'code': diag.native_request()}, {'op': 'eval', 'code': summary}])
    pdf = folder / (label + '-diagnostic.pdf')
    captures.append((label, len(steps) - 1, pdf, lev, wis, dc, attack))
    steps.append({'op': 'save', 'path': str(pdf)})

def clean(label):
    p = folder / (label + '.pdf')
    steps.extend([{'op': 'eval', 'code': "Value('PC Name','Shadow Monk spells workflow');Value('User Script','');"}, {'op': 'save', 'path': str(p)}])
    return p

def run(label, input):
    spec = folder / (label + '-scenario.json')
    probe = folder / (label + '-probe.json')
    spec.write_text(json.dumps({'steps': steps, 'dialogs': dialogs}))
    env = dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / (label + '-dialogs')))
    if args.pdfium:
        env['MPMB_PDFIUM'] = str(args.pdfium.resolve())
    with (folder / (label + '.log')).open('w') as log:
        p = subprocess.run([str(binary), str(input), '--probe', str(spec), str(probe)], stdout=log, stderr=log, env=env, timeout=1200)
    d = json.load(open(probe))
    assert [x['text'] for x in d['diagnostics']['console']['messages']] == ['MPMB 2024 Shadow Monk spells workflow sentinel']
    strict = copy.deepcopy(d)
    strict['diagnostics']['console']['messages'] = []
    checked = qual.qualify_probe(p.returncode, strict)
    assert checked['passed'], checked
    for index, (name, stage, pdf, lev, wis, dc, attack) in enumerate(captures):
        assert d['stages'][stage - 1]['result'] == diag.DONE + str(index + 1)
        state = style.saved_capture(pdf, d['stages'][stage]['result'], source)
        assert not state['errors'] and state['calculation'] == {'app': True, 'doc': True, 'delay': False}
        assert state['fields']['Character Level'] == str(lev) and state['fields']['Wis'] == str(wis) and (state['fields']['AC'] == str(14 + (wis - 10) // 2))
        assert state['pages'] == 7 and len(state['spellPages']) == 1
        spell = state['spells']['monk']
        assert spell['level'] == lev and spell['selectBo'][:2] == ['minor illusion', 'darkness']
        assert spell['special'] == {'minor illusion': 'atwill', 'darkness': '1'}
        generated = state['spellPages'][0]['fields']
        assert generated['spellshead.dc.0'] == 'DC ' + str(dc) and generated['spellshead.attack.0'] == '+' + str(attack)
        remember = [v.split('##')[0] for k, v in generated.items() if k.startswith('spells.remember.')]
        assert 'minor illusion' in remember and 'darkness' in remember
        expected = dict(state['fields'], **state['resources'])
        for prefix, page in zip(state['rawPrefixes'], state['spellPages']):
            expected.update({prefix + k: v for k, v in page['fields'].items()})
        api = folder / (name + '-expected.json')
        api.write_text(json.dumps(expected))
        verification = folder / (name + '-verification')
        with (folder / (name + '-verification.log')).open('w') as log:
            verified = subprocess.run([sys.executable, str(root / 'tools/native/verify-generated-fields.py'), str(pdf), str(api), str(verification)], stdout=log, stderr=log, timeout=600)
        canonical = json.loads((verification / 'verification.json').read_text())
        assert verified.returncode == 0 and canonical['passed'] and (canonical['source_sha256'] == report['verifier_sha256']) and (script_hashes(pdf) == script_hashes(source))
        report['phases'].append({'label': name, 'pdf': str(pdf), 'state': state, 'canonical': canonical, 'qualification': checked})
        (folder / 'progress.json').write_text(json.dumps(report, indent=2))

def clean_mirrors(pdf):
    values = canonical_fields(PdfReader(pdf))
    expected = {name: 'Shadow Monk spells workflow' for name in values if name == 'PC Name' or (name.endswith('zAdvLog.PC Name') and 'SSfront.' in name)}
    assert len(expected) == 2, expected
    checked = inspect(pdf, expected)
    assert checked['passed'], checked
    report.setdefault('clean_name_mirrors', []).append(checked)
def spend(label, value):
    code="var selected=[];for(var i=0;i<numFields;i++){var n=getNthFieldName(i);if(/^Limited Feature [0-9]+$/.test(n)&&getField(n).valueAsString.indexOf("+json.dumps(label)+")==0)selected.push('Limited Feature Used '+n.slice(16));}if(selected.length!==1)throw Error('Resource is not unique');__host.userEdit(selected[0],"+json.dumps(value)+");"
    steps.extend([{'op':'eval','code':code},{'op':'advance','ms':1100}])
def assert_spent(state):
    rows=[]
    for k,v in state['resources'].items():
        if k.startswith('Limited Feature ') and k.rsplit(' ',1)[-1].isdigit() and (v.startswith('Focus Points') or v.startswith('Uncanny Metabolism')):
            rows.append(state['resources']['Limited Feature Used '+k.rsplit(' ',1)[-1]])
    assert rows==['2','1'],rows
try:
    if args.spent_regeneration:
        report['scope']='Native-only resource/spell generation integration discovery: spent Focus2 and Metabolism1 retained through original regeneration and cold snapshot; not Reader qualification.'
        steps=install();captures=[];dialogs=[]
        spend('Focus Points','2');spend('Uncanny Metabolism','1')
        capture('spent-before-generation17',17,18,18,10)
        generate();capture('spent-after-generation17',17,18,18,10)
        saved=clean('spent-regenerated17');run('spent-regeneration',source);clean_mirrors(saved)
        steps=install();captures=[];dialogs=[]
        capture('cold-spent-regenerated17',17,18,18,10)
        final=clean('final');run('cold-spent',saved);clean_mirrors(final)
        assert len(report['phases'])==3
        for p in report['phases']:assert_spent(p['state'])
        comparable=lambda state:{k:v for k,v in state.items() if k!='rawPrefixes'}
        assert all(comparable(p['state'])==comparable(report['phases'][0]['state']) for p in report['phases'])
        report.update(passed=True,pdf=str(final))
    else:
        steps = install()
        captures = []
        dialogs = []
        if args.restore_baseline:
            wisdom(18)
            level(3)
        generate()
        capture('generated3', 3, 18, 14, 6)
        level(17)
        generate()
        capture('generated17', 17, 18, 18, 10)
        saved17 = clean('saved17')
        run('generate3-17', source)
        clean_mirrors(saved17)
        steps = install()
        captures = []
        dialogs = []
        wisdom(16)
        generate()
        capture('cold-wis16-17', 17, 16, 17, 9)
        level(3)
        generate()
        capture('lowered3-wis16', 3, 16, 13, 5)
        saved3 = clean('saved3-wis16')
        run('cold-wis16', saved17)
        clean_mirrors(saved3)
        steps = install()
        captures = []
        dialogs = []
        wisdom(18)
        generate()
        capture('final-cold-restored3', 3, 18, 14, 6)
        final = clean('final')
        run('final-restored', saved3)
        clean_mirrors(final)
        assert len(report['phases']) == 5
        report.update(passed=True, pdf=str(final))

except Exception as e:
    report['error'] = str(e)
    raise
finally:
    (folder / 'spells.json').write_text(json.dumps(report, indent=2))
    print(folder, flush=True)
