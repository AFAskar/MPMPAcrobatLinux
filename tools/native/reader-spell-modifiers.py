#!/usr/bin/env python3
"""Qualify original spell-button Shift/Ctrl options, row moves and changed reopens.

Real named-field focus/Space input, guarded actual offered menus and independently
read saved fields. This bounded prepared-spell workflow is not all modifier APIs.
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
spec = importlib.util.spec_from_file_location('menus', ROOT / 'tools/native/warlock-reader-invocations.py')
menus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menus)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--button', required=True)
    p.add_argument('--readiness', type=Path, required=True)
    a = p.parse_args()
    ready = json.loads(a.readiness.read_text())
    assert ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = a.input.resolve()
    fields = canonical_fields(PdfReader(source))
    button = a.button
    row = int(button.rsplit('.', 1)[1])
    prefix = button.rsplit('.', 1)[0]
    names = [prefix.replace('.checkbox', '.check') + '.' + str(n) for n in [row, row + 1]]
    names += [prefix.replace('.checkbox', '.remember') + '.' + str(n) for n in [row, row + 1]]
    assert fields[button]['/FT'] == '/Btn'
    initial = {n: fields[n]['/V'] for n in names}
    assert initial[names[0]] in ['checkbox', 'checkedbox']
    folder = ROOT / 'output/testing' / ('reader-spell-modifiers-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/spell-modifiers-' + str(time.time_ns()))
    remote = base + '.pdf'
    opened = False
    report = {'passed': False, 'scope': __doc__, 'input': str(source),
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'readiness': str(a.readiness), 'button': button, 'names': names, 'phases': [], 'activations': []}

    def persist():
        (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def capture(label):
        nonlocal remote
        state = c.script('read', path=remote, fields=names)['fields']
        output = base + '-' + label + '.pdf'
        c.script('save', path=remote, output=output)
        remote = output
        report['phases'].append({'label': label, 'fields': state, 'reader_path': output})
        persist()
        return state

    def activate(key, selection=None, target=None):
        target = target or button
        focus = c.script('focus', path=remote, field=target)
        before = c.script('read', path=remote, fields=names)['fields']
        reply = c.command('keys', keys=key)
        state = c.command('inspect_focused')
        event = {'button': target, 'key': key, 'selection': selection, 'focus': focus, 'key_reply': reply, 'menu': state, 'before': before}
        report['activations'].append(event)
        persist()
        if key != ' ':
            assert state['in_reader'] and state['class'] == '#32768' and state['type'] == 'ControlType.Menu'
            offered = [e['name'].split('\t')[0].strip() for e in state['children'] if e['type'] == 'ControlType.MenuItem']
            assert 'Move row down' in offered and 'Move row up' in offered
            if selection:
                matches = [(i, e) for i, e in enumerate(state['children']) if e['name'].split('\t')[0].strip() == selection]
                assert len(matches) == 1
                index, item = matches[0]
                event['selection_reply'] = c.command('activate_menu', owner=state['native_window_handle'], position=index, name=item['name'])
            else:
                event['cancel'] = c.command('keys', keys='{ESC}')
        else:
            assert state['class'] != '#32768'
        c.ensure_document(remote)
        event['after'] = c.script('read', path=remote, fields=names)['fields']
        persist()
        return event['after']

    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP + [str(source), c.SCP_TARGET + ':MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            assert capture('loaded') == initial
            toggled = dict(initial)
            toggled[names[0]] = 'checkedbox' if initial[names[0]] == 'checkbox' else 'checkbox'
            assert activate(' ') == toggled
            assert activate('+ ') == toggled
            assert activate('^ ') == toggled
            assert capture('prepared') == toggled
            moved = activate('+ ', 'Move row down')
            assert moved[names[3]] == initial[names[2]]
            assert moved[names[2]] == initial[names[3]]
            capture('moved-down')
            restored = activate('^ ', 'Move row up', prefix + '.' + str(row + 1))
            assert restored[names[2]] == initial[names[2]] and restored[names[3]] == initial[names[3]]
            assert restored[names[0]] == toggled[names[0]] and restored[names[1]] == toggled[names[1]]
            capture('restored')
            report['first_close'] = c.script('close', path=remote)
            opened = False
            opened = True
            c.ensure_document(remote)
            assert capture('reopened') == toggled
            assert activate(' ') == initial
            assert capture('edited-reopen') == initial
            report['close'] = c.script('close', path=remote)
            opened = False
            for phase in report['phases']:
                local = c.fetch(phase['reader_path'], folder / (phase['label'] + '.pdf'))
                saved = canonical_fields(PdfReader(local))
                assert {n: saved[n]['/V'] for n in names} == phase['fields']
                assert script_hashes(local) == script_hashes(source)
                phase['pdf'] = str(local)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == report['input_sha256']
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    state = c.command('inspect_focused')
                    if state.get('class') == '#32768':
                        c.command('keys', keys='{ESC}')
                    retained = base + '-failed-retained.pdf'
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = c.script('close', path=retained)
                    c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'modifiers.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
