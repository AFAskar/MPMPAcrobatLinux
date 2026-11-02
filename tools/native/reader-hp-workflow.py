#!/usr/bin/env python3
"""Choose real automatic HP, commit Constitution by typing/Tab, then add Tough.

Preserves the original Constitution Blur action while observing its actual event.
Each input is a bounded class profile; this does not qualify all HP/class/multiclass workflows.
"""
import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import sys
import time
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import canonical_fields, script_hashes


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


style = module('style', 'default-style-persistence.py')
menus = module('menus', 'warlock-reader-invocations.py')
MENU = "var iFileName='HP menu qualification.js';MakeHPMenu_HPOptions();"


def original_blur(source):
    pdf = PdfReader(source)
    fields = canonical_fields(pdf)
    action = pdf.get_object(fields['Con']['reference'])['/AA']['/Bl'].get_object()
    code = str(action['/JS'])
    assert code.strip(), 'Expected nonempty original Constitution Blur action'
    return code


def setup(code):
    before = "var iFileName='HP event observation.js';tDoc.__hpTrace=[];tDoc.__hpErrors=[];if(typeof displayError==='function'){tDoc.__hpOriginalDisplayError=displayError;displayError=function(e,s){try{tDoc.__hpErrors.push({error:String(e),context:String(s)})}catch(ignore){}return tDoc.__hpOriginalDisplayError.apply(this,arguments)}};tDoc.__hpRecord=function(e){var r={};function read(k,f){try{r[k]=f()}catch(x){r[k]={getter_error:String(x)}}}read('name',function(){return e.name});read('type',function(){return e.type});read('target',function(){return e.target.name});read('before',function(){return String(What('HP Max'))});try{tDoc.__hpTrace.push(r)}catch(ignore){}return r};"
    wrapped = "var __hpObserved=tDoc.__hpRecord(event);try{\n" + code + "\n}finally{try{__hpObserved.after=String(What('HP Max'))}catch(ignore){}}"
    return before + "tDoc.getField('Con').setAction('OnBlur'," + json.dumps(wrapped) + ');'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--readiness', type=Path, required=True)
    p.add_argument('--constitution', type=int)
    p.add_argument('--feat-field')
    a = p.parse_args()
    ready = json.loads(a.readiness.read_text())
    assert ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = a.input.resolve()
    code = original_blur(source)
    input_fields = canonical_fields(PdfReader(source))
    initial_con = int(str(input_fields['Con']['/V']))
    constitution = a.constitution if a.constitution is not None else initial_con + 2
    feat_fields = sorted((n for n in input_fields if re.fullmatch(r'Feat Name \d+', n)), key=lambda n: int(n.split()[-1]))
    feat_field = a.feat_field or next(n for n in feat_fields if not str(input_fields[n].get('/V', '')))
    assert not str(input_fields[feat_field].get('/V', '')), 'Choose an empty feat control'
    assert constitution > initial_con and constitution % 2 == initial_con % 2
    observer = (ROOT / 'tools/native/hp-workflow-observer.js').read_text()
    folder = ROOT / 'output/testing' / ('reader-hp-workflow-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/hp-workflow-' + str(time.time_ns()))
    remote = base + '.pdf'
    report = {'passed': False, 'scope': __doc__, 'input': str(source),
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'readiness': str(a.readiness),
              'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'original_blur_sha256': hashlib.sha256(code.encode()).hexdigest(),
              'observer_sha256': hashlib.sha256(observer.encode()).hexdigest(), 'phases': [],
              'constitution': constitution, 'reopen_constitution': constitution + 2, 'feat_field': feat_field}
    opened = False
    pending = None

    def persist():
        (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def script(text):
        nonlocal pending
        c.script('set', path=remote, values={'User Script': text})
        pending = c.script_submit('call', path=remote, name='RunUserScript', args=[False])

    def complete():
        nonlocal pending
        result = c.script_result(pending, timeout=120)
        pending = None
        c.ensure_document(remote)
        return result

    def capture(label):
        nonlocal remote
        script(observer)
        complete()
        summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
        c.script('set', path=remote, values={'User Script': ''})
        diagnostic = base + '-' + label + '-diagnostic.pdf'
        c.script('save', path=remote, output=diagnostic)
        remote = diagnostic
        report['phases'].append({'label': label, 'diagnostic': diagnostic, 'summary': summary})
        persist()

    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()]
            subprocess.run(c.SCP + [str(source), 'mpmb-test@127.0.0.1:MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            initial = c.script('read', path=remote, fields=['Con', 'Character Level', 'HP Max', 'Feat Name 1'])['fields']
            assert initial['Con'] == str(initial_con)
            assert initial['Character Level'] == str(input_fields['Character Level']['/V'])
            script(setup(code))
            complete()
            c.script('set', path=remote, values={'HP Current': '30', 'HP Temp': '5', 'HD1 Used': '2'})
            capture('initial')
            first = report['phases'][-1]
            local = c.fetch(first['diagnostic'], folder / 'initial-diagnostic.pdf')
            initial_state = style.saved_capture(local, first['summary'], source)
            assert not initial_state['errors']
            fixed = initial_state['totals']['fixed']
            report['fixed_menu_value'] = fixed
            script(MENU)
            actions = []
            for label in ['Set the Max HP to automatically assume', 'The total HP using fixed values (' + str(fixed) + ')']:
                popup = menus.popup(label, folder)
                matches = [(i, e) for i, e in enumerate(popup['children']) if e['name'].split('\t')[0].strip() == label]
                assert len(matches) == 1
                index, item = matches[0]
                selected = c.command('activate_menu', owner=popup['native_window_handle'], position=index, name=item['name'])
                actions.append({'menu': popup, 'selected': item, 'action': selected})
            report['menu'] = {'actions': actions, 'completion': complete()}
            capture('auto-fixed')
            focus = c.script('focus', path=remote, field='Con')
            pasted = c.command('paste', value=str(constitution))
            assert pasted['verified'] and pasted['value'] == str(constitution)
            report['constitution_commit'] = {'focus': focus, 'paste': pasted}
            c.ensure_document(remote)
            capture('constitution-user-commit')
            c.script('set', path=remote, values={feat_field: 'Tough'})
            capture('tough')
            restore = "var iFileName='Restore HP action.js';tDoc.getField('Con').setAction('OnBlur'," + json.dumps(code) + ');'
            script(restore)
            complete()
            c.script('set', path=remote, values={'User Script': '', 'PC Name': 'HP compatibility'})
            saved = base + '-saved.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['close'] = c.script('close', path=remote)
            opened = False
            output = c.fetch(remote, folder / 'reader.pdf')
            assert original_blur(output) == code and script_hashes(output) == script_hashes(source)
            report['pdf'] = str(output)
            for phase in report['phases']:
                local = c.fetch(phase['diagnostic'], folder / (phase['label'] + '-diagnostic.pdf'))
                state = style.saved_capture(local, phase['summary'], source)
                phase['state'] = state
                assert not state['errors']
                if phase['label'] != 'initial':
                    assert state['fields']['HP Max'] == state['mapping'].split(',')[1]
                    assert state['mapping'].split(',')[3] == 'fixed'
                assert tuple(state['fields'][n] for n in ['HP Current', 'HP Temp', 'HD1 Used']) == ('30', '5', '2')
            states = {p['label']: p['state'] for p in report['phases']}
            con_state = states['constitution-user-commit']
            before_hp = states['auto-fixed']['fields']['HP Max']
            after_hp = con_state['fields']['HP Max']
            assert before_hp != after_hp
            assert int(after_hp) == fixed + (constitution // 2 - initial_con // 2) * initial_state['totals']['count']
            assert int(states['tough']['fields']['HP Max']) == int(after_hp) + 2 * initial_state['totals']['count']
            assert any(e == {'name': 'Blur', 'type': 'Field', 'target': 'Con', 'before': before_hp, 'after': after_hp} for e in con_state['trace']), con_state['trace']
            assert states['tough']['feats']['known'][int(feat_field.split()[-1]) - 1] == 'tough'
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    focused = c.command('inspect_focused')
                    if focused.get('class') == '#32768':
                        c.command('keys', keys='{ESC}')
                    if pending:
                        report['cleanup_result'] = c.script_result(pending, timeout=45)
                    retained = base + '-failed-retained.pdf'
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = c.script('close', path=retained)
                    c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'hp.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
