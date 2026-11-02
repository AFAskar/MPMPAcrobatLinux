#!/usr/bin/env python3
"""Choose real automatic HP, commit Constitution by typing/Tab, then add Tough.

Preserves the original Constitution Blur action while observing its actual event.
This bounded Bard9 case does not qualify all HP/class/multiclass workflows.
"""
import argparse
import hashlib
import importlib.util
import json
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
    before = "var iFileName='HP event observation.js';tDoc.__hpTrace=[];tDoc.__hpErrors=[];tDoc.__hpOriginalDisplayError=displayError;displayError=function(e,s){try{tDoc.__hpErrors.push({error:String(e),context:String(s)})}catch(ignore){}return tDoc.__hpOriginalDisplayError.apply(this,arguments)};tDoc.__hpRecord=function(e){var r={};function read(k,f){try{r[k]=f()}catch(x){r[k]={getter_error:String(x)}}}read('name',function(){return e.name});read('type',function(){return e.type});read('target',function(){return e.target.name});read('before',function(){return String(What('HP Max'))});try{tDoc.__hpTrace.push(r)}catch(ignore){}return r};"
    wrapped = "var __hpObserved=tDoc.__hpRecord(event);try{\n" + code + "\n}finally{try{__hpObserved.after=String(What('HP Max'))}catch(ignore){}}"
    return before + "tDoc.getField('Con').setAction('OnBlur'," + json.dumps(wrapped) + ');'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--readiness', type=Path, required=True)
    a = p.parse_args()
    ready = json.loads(a.readiness.read_text())
    assert ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = a.input.resolve()
    code = original_blur(source)
    observer = (ROOT / 'tools/native/hp-workflow-observer.js').read_text()
    folder = ROOT / 'output/testing' / ('reader-hp-workflow-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/hp-workflow-' + str(time.time_ns()))
    remote = base + '.pdf'
    report = {'passed': False, 'scope': __doc__, 'input': str(source),
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'readiness': str(a.readiness),
              'original_blur_sha256': hashlib.sha256(code.encode()).hexdigest(),
              'observer_sha256': hashlib.sha256(observer.encode()).hexdigest(), 'phases': []}
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
            assert initial == {'Con': '12', 'Character Level': '9', 'HP Max': '', 'Feat Name 1': ''}
            script(setup(code))
            complete()
            c.script('set', path=remote, values={'HP Current': '30', 'HP Temp': '5', 'HD1 Used': '2'})
            script(MENU)
            actions = []
            for label in ['Set the Max HP to automatically assume', 'The total HP using fixed values (57)']:
                popup = menus.popup(label, folder)
                matches = [(i, e) for i, e in enumerate(popup['children']) if e['name'].split('\t')[0].strip() == label]
                assert len(matches) == 1
                index, item = matches[0]
                selected = c.command('activate_menu', owner=popup['native_window_handle'], position=index, name=item['name'])
                actions.append({'menu': popup, 'selected': item, 'action': selected})
            report['menu'] = {'actions': actions, 'completion': complete()}
            capture('auto-fixed')
            focus = c.script('focus', path=remote, field='Con')
            pasted = c.command('paste', value='16')
            assert pasted['verified'] and pasted['value'] == '16'
            report['constitution_commit'] = {'focus': focus, 'paste': pasted}
            c.ensure_document(remote)
            capture('constitution-user-commit')
            c.script('set', path=remote, values={'Feat Name 1': 'Tough'})
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
                assert state['fields']['HP Max'] == {'auto-fixed': '57', 'constitution-user-commit': '75', 'tough': '93'}[phase['label']]
                assert state['mapping'].split(',')[3] == 'fixed'
                assert tuple(state['fields'][n] for n in ['HP Current', 'HP Temp', 'HD1 Used']) == ('30', '5', '2')
            con_state = report['phases'][1]['state']
            assert any(e == {'name': 'Blur', 'type': 'Field', 'target': 'Con', 'before': '57', 'after': '75'} for e in con_state['trace']), con_state['trace']
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
