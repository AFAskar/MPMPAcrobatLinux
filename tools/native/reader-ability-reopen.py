#!/usr/bin/env python3
"""Edit an actual native Resilient state through Reader's original score dialog.

A second cold Reader reopen changes the base again. Uses uniquely observed
editable values in the stated synthetic Bard input, not positional edit indices.
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
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from spells import wait_dialog
from verify import inspect, script_hashes


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


profile = module('profile', 'reader-resilient-feat.py')
style = module('style', 'default-style-persistence.py')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--readiness', type=Path, required=True)
    a = p.parse_args()
    ready = json.loads(a.readiness.read_text())
    assert ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = a.input.resolve()
    observer = (ROOT / 'tools/native/resilient-feat-observer.js').read_text()
    folder = ROOT / 'output/testing' / ('reader-ability-reopen-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/ability-reopen-' + str(time.time_ns()))
    remote = base + '.pdf'
    report = {'passed': False, 'scope': __doc__, 'input': str(source),
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'readiness': str(a.readiness),
              'observer_sha256': hashlib.sha256(observer.encode()).hexdigest(), 'phases': []}
    opened = False
    pending = None

    def script(code):
        nonlocal pending
        c.script('set', path=remote, values={'User Script': code})
        pending = c.script_submit('call', path=remote, name='RunUserScript', args=[False])

    def complete():
        nonlocal pending
        result = c.script_result(pending, timeout=120)
        pending = None
        c.ensure_document(remote)
        return result

    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()]
            subprocess.run(c.SCP + [str(source), c.SCP_TARGET + ':MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            for label, old_base, new_base, old_total, wanted in [
                ('native-input-edit', '13', '15', '14', ('16', '7', '11')),
                ('cold-reader-edit', '15', '17', '16', ('18', '8', '12')),
            ]:
                opened = True
                c.ensure_document(remote)
                before = c.script('read', path=remote, fields=['Wis', 'Wis ST Prof'])['fields']
                assert before == {'Wis': old_total, 'Wis ST Prof': 'True'}
                script(profile.SETUP)
                complete()
                script(profile.APPLY)
                dialog, elements = wait_dialog('ABILITY SCORES DIALOG', time.monotonic() + 60)
                (folder / (label + '-controls.json')).write_text(json.dumps(elements, indent=2) + '\n')
                owned = [e for e in elements if e.get('owner') == dialog['handle']]
                assert any(e.get('name') == 'Wisdom' for e in owned)
                assert any(e.get('name') == 'Score Base' for e in owned)
                candidates = [e for e in owned if re.fullmatch(r'Edit|RICHEDIT[0-9]+W', e.get('class', '')) and e.get('name') == old_base
                              and e.get('enabled') and e.get('read_only') is False]
                assert len(candidates) == 1, ('Base score edit is not unique', candidates)
                edit = candidates[0]
                focused = c.command('focus_control', owner=dialog['handle'], handle=edit['handle'])
                assert focused['focused'] and focused['text'] == old_base
                pasted = c.command('paste', value=new_base)
                assert pasted['verified'] and pasted['value'] == new_base
                readback = c.command('dialog_control', owner=dialog['handle'], handle=edit['handle'])
                assert readback['text'] == new_base
                applied = c.command('invoke', name='Apply', owner=dialog['handle'])
                completed = complete()
                script(observer)
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
                closed = c.script('close', path=remote)
                opened = False
                local = c.fetch(remote, folder / (label + '.pdf'))
                carrier = c.fetch(diagnostic, folder / (label + '-diagnostic.pdf'))
                state = style.saved_capture(carrier, summary, source)
                assert not state['errors']
                assert tuple(state['fields'][n] for n in ['Wis', 'Wis ST Mod', 'Perc']) == wanted
                assert state['fields']['Wis ST Prof'] == 'True'
                assert state['feats']['known'][0] == 'resilient' and state['feats']['choices'][0] == 'wisdom'
                assert state['stats']['cols'][0]['scores'][4] == int(new_base)
                visible = inspect(local, {n: state['fields'][n] for n in ['Wis', 'Wis Mod', 'Wis ST Mod', 'Perc']})
                assert visible['passed'] and script_hashes(local) == script_hashes(source)
                report['phases'].append({'label': label, 'pdf': str(local), 'state': state, 'controls': elements,
                                          'chosen': edit, 'focus': focused, 'paste': pasted, 'readback': readback,
                                          'apply': applied, 'completion': completed, 'close': closed, 'visible': visible})
                (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')
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
                    dialogs = [e for e in elements if e.get('class') == '#32770' and e.get('name') == 'ABILITY SCORES DIALOG']
                    if len(dialogs) == 1:
                        c.command('invoke', name='Cancel', owner=dialogs[0]['handle'])
                    if pending:
                        report['cleanup_result'] = c.script_result(pending, timeout=45)
                    retained = base + '-failed-retained.pdf'
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = c.script('close', path=retained)
                    c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'ability.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
