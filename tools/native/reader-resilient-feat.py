#!/usr/bin/env python3
"""Choose genuine Resilient/Wisdom, apply/remove its score bonus and save.

Bounded 2024 Bard9 workflow. Other feats and complete progression remain open.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from spells import wait_dialog
spec = importlib.util.spec_from_file_location('style', ROOT / 'tools/native/default-style-persistence.py')
style = importlib.util.module_from_spec(spec)
spec.loader.exec_module(style)
APPLY = "var iFileName='Apply ability scores.js';AbilityScores_Button();"
SETUP = "var iFileName='Observe feat errors.js';tDoc.__featErrors=[];tDoc.__featOriginalDisplayError=displayError;displayError=function(e,s){try{tDoc.__featErrors.push({error:String(e),context:String(s)})}catch(ignore){}return tDoc.__featOriginalDisplayError.apply(this,arguments)};"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--readiness', type=Path, required=True)
    a = p.parse_args()
    ready = json.loads(a.readiness.read_text())
    assert ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = a.input.resolve()
    observer = (ROOT / 'tools/native/resilient-feat-observer.js').read_text()
    folder = ROOT / 'output/testing' / ('reader-resilient-feat-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    (folder / 'observer.js').write_text(observer)
    base = c.remote_path('runs/resilient-feat-' + str(time.time_ns()))
    remote = base + '.pdf'
    report = {'passed': False, 'scope': __doc__, 'input': str(source),
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'readiness': str(a.readiness),
              'observer_sha256': hashlib.sha256(observer.encode()).hexdigest(), 'apply_script': APPLY,
              'setup_script': SETUP, 'phases': [], 'ability_dialogs': []}
    opened = False
    pending = None

    def persist():
        (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def run_script(script):
        nonlocal pending
        c.script('set', path=remote, values={'User Script': script})
        pending = c.script_submit('call', path=remote, name='RunUserScript', args=[False])

    def complete():
        nonlocal pending
        result = c.script_result(pending, timeout=120)
        pending = None
        c.ensure_document(remote)
        return result

    def capture(label):
        nonlocal remote
        run_script(observer)
        complete()
        summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
        c.script('set', path=remote, values={'User Script': ''})
        diagnostic = base + '-' + label + '-diagnostic.pdf'
        c.script('save', path=remote, output=diagnostic)
        remote = diagnostic
        c.script('set', path=remote, values={'PC Name': 'Feat compatibility'})
        saved = base + '-' + label + '.pdf'
        c.script('save', path=remote, output=saved)
        remote = saved
        report['phases'].append({'label': label, 'diagnostic': diagnostic, 'reader_path': saved, 'summary': summary})
        persist()

    def apply_scores():
        run_script(APPLY)
        dialog, elements = wait_dialog('ABILITY SCORES DIALOG', time.monotonic() + 60)
        assert any(e.get('owner') == dialog['handle'] and e.get('class') == 'Button' and e.get('name') == 'Apply' for e in elements)
        action = c.command('invoke', name='Apply', owner=dialog['handle'])
        result = complete()
        report['ability_dialogs'].append({'controls': elements, 'action': action, 'completion': result})
        persist()

    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()]
            subprocess.run(c.SCP + [str(source), c.SCP_TARGET + ':MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            fields = c.script('read', path=remote, fields=['Feat Name 1', 'Wis', 'Wis ST Prof', 'Perc'])['fields']
            assert fields == {'Feat Name 1': '', 'Wis': '13', 'Wis ST Prof': 'Off', 'Perc': '9'}
            run_script(SETUP)
            complete()
            pending = c.script_submit('set', path=remote, values={'Feat Name 1': 'Resilient'})
            dialog, elements = wait_dialog('ASK USER DIALOG', time.monotonic() + 60)
            assert any(e.get('owner') == dialog['handle'] and e.get('name') == 'Select Resilient Type' for e in elements)
            assert any(e.get('owner') == dialog['handle'] and e.get('class') == 'Button' and e.get('name') == 'Wisdom' for e in elements)
            radio = c.command('invoke', name='Wisdom', owner=dialog['handle'])
            ok = c.command('invoke', name='OK', owner=dialog['handle'])
            report['choice'] = {'controls': elements, 'radio': radio, 'ok': ok, 'completion': complete()}
            capture('selected')
            apply_scores()
            capture('applied')
            c.script('set', path=remote, values={'Feat Name 1': ''})
            capture('removed-pending')
            apply_scores()
            capture('removed-applied')
            report['close'] = c.script('close', path=remote)
            opened = False
            expected = {'selected': ('13', 'True', '5', '9'), 'applied': ('14', 'True', '6', '10'),
                        'removed-pending': ('14', 'Off', '2', '10'), 'removed-applied': ('13', 'Off', '1', '9')}
            for phase in report['phases']:
                label = phase['label']
                diagnostic = c.fetch(phase['diagnostic'], folder / (label + '-diagnostic.pdf'))
                local = c.fetch(phase['reader_path'], folder / (label + '.pdf'))
                phase['state'] = style.saved_capture(diagnostic, phase['summary'], source)
                phase['pdf'] = str(local)
                state = phase['state']
                assert not state['errors']
                assert tuple(state['fields'][n] for n in ['Wis', 'Wis ST Prof', 'Wis ST Mod', 'Perc']) == expected[label]
                assert state['feats']['known'][0] == ('resilient' if label in ['selected', 'applied'] else '')
                assert state['feats']['choices'][0] == ('wisdom' if label in ['selected', 'applied'] else '')
            assert hashlib.sha256(source.read_bytes()).hexdigest() == report['input_sha256']
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    elements = c.command('inspect')
                    titles = ['ASK USER DIALOG', 'ABILITY SCORES DIALOG']
                    dialogs = [e for e in elements if e.get('class') == '#32770' and e.get('name') in titles]
                    if len(dialogs) == 1:
                        title = dialogs[0]['name']
                        if title == 'ASK USER DIALOG':
                            c.command('invoke', name='Wisdom', owner=dialogs[0]['handle'])
                        c.command('invoke', name='OK' if title == 'ASK USER DIALOG' else 'Cancel', owner=dialogs[0]['handle'])
                    if pending:
                        report['cleanup_result'] = c.script_result(pending, timeout=45)
                    retained = base + '-failed-retained.pdf'
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = c.script('close', path=retained)
                    c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'feat.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
