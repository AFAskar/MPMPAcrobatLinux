#!/usr/bin/env python3
"""Actual Champion additional-style choices, independent slots and edited progression.

The actual feature key is recorded; source reduction removes the choice, and
restoring the level requires a genuine re-selection. Three fresh Reader epochs.
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
from verify import inspect, script_hashes
import fighter_additional_diagnostics as diagnostics
import reader_document_controls as document_controls


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


profile = module('profile', 'fighter-styles.py')
style = module('style', 'default-style-persistence.py')
menus = module('menus', 'warlock-reader-invocations.py')
field_state = module('field_state', 'field-state-comparison.py')
ascii_input = module('ascii_input', 'reader-ascii-input.py')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--readiness', type=Path, required=True)
    p.add_argument('--install-observer-once', action='store_true')
    p.add_argument('--keyboard-focus-cycle', action='store_true', help='Move forward/back only in the named plain Shield field before typing')
    a = p.parse_args()
    native = json.loads(a.native.read_text())
    mode = diagnostics.MODE if a.install_observer_once else 'repeated-RunUserScript'
    assert native.get('diagnostic_mode', 'repeated-RunUserScript') == mode, 'Match the native diagnostic entry sequence'
    if a.install_observer_once:
        assert native.get('diagnostic_helper_sha256') == hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest(), 'Match the actual native timer helper'
    ready = json.loads(a.readiness.read_text())
    assert native['passed'] and ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = Path(native['input'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == native['input_sha256']
    observer = (ROOT / 'tools/native/fighter-additional-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == native['observer_sha256']
    folder = ROOT / 'output/testing' / ('reader-fighter-additional-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/fighter-additional-' + str(time.time_ns()))
    remote = base + '.pdf'
    report = {'passed': False, 'scope': __doc__, 'native': str(a.native.resolve()),
              'input': str(source), 'input_sha256': native['input_sha256'], 'readiness': str(a.readiness),
              'observer_sha256': native['observer_sha256'],
              'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'input_helper_sha256': hashlib.sha256((ROOT / 'tools/native/reader-ascii-input.py').read_bytes()).hexdigest(),
              'diagnostic_mode': mode,
              'keyboard_focus_cycle': a.keyboard_focus_cycle,
              'diagnostic_helper_sha256': hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest(),
              'phases': [], 'inputs': [], 'choices': []}
    pending = None
    opened = False
    def script(text):
        nonlocal pending
        if a.install_observer_once:
            if text == observer:
                report.setdefault('timer_requests', []).append(diagnostics.reader_request(c, remote))
                return
            if text == profile.SETUP:
                text = diagnostics.install(text, observer)
        c.script('set', path=remote, values={'User Script': text})
        pending = c.script_submit('call', path=remote, name='RunUserScript', args=[False])
    def complete():
        nonlocal pending
        if pending is None:
            return None
        result = c.script_result(pending, timeout=120)
        pending = None
        c.ensure_document(remote)
        return result
    def edit(n, v):
        result = ascii_input.commit(c, remote, n, v, cycle_focus=a.keyboard_focus_cycle and n == 'AC Shield Bonus Description')
        report['inputs'].append({'field': n, 'value': v, 'input': result})
    def choose(name, branch='Fighting Style'):
        nonlocal pending
        pending = c.script_submit('call', path=remote, name='ClassFeatureOptions', args=[])
        actions = []
        for label in ['Champion', branch, name]:
            popup = menus.popup(label, folder)
            matches = [(i, x) for i, x in enumerate(popup['children']) if x['name'].split('\t')[0].strip() == label]
            assert len(matches) == 1
            index, selected = matches[0]
            result = c.command('activate_menu', owner=popup['native_window_handle'], position=index, name=selected['name'])
            actions.append({'popup': popup, 'selected': selected, 'action': result})
        report['choices'].append({'style': name, 'branch': branch, 'actions': actions, 'completion': complete()})
    def capture(label):
        nonlocal remote
        script(observer)
        complete()
        summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
        c.script('set', path=remote, values={'User Script': ''})
        diagnostic = base + '-' + label + '-diagnostic.pdf'
        c.script('save', path=remote, output=diagnostic)
        remote = diagnostic
        local = c.fetch(diagnostic, folder / (label + '-diagnostic.pdf'))
        state = style.saved_capture(local, summary, source)
        wanted = next(p for p in native['phases'] if p['label'] == label)
        assert not state['errors'] and state == wanted['state'], (label, state, wanted['state'])
        field_state.compare(local, dict(state['fields'], **state['resources']))
        visible = inspect(local, {n: state['fields'][n] for n in ['AC', 'Attack.1.To Hit', 'Attack.1.Damage', 'Attack.1.Weapon']})
        assert visible['passed'], visible
        report['phases'].append({'label': label, 'state': state, 'pdf': str(local), 'summary': summary, 'visible': visible})
        (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')
    try:
        with c.desktop_lock():
            assert not [w for w in c.command('inspect') if w.get('class') == 'AcrobatSDIWindow' and '.pdf' in w.get('name', '').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP + [str(source), 'mpmb-test@127.0.0.1:MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            first = native['phases'][0]['state']['fields']
            names = ['Class and Levels', 'Character Level', 'Str', 'Dex', 'Con']
            assert c.script('read', path=remote, fields=names)['fields'] == {n: first[n] for n in names}
            script(profile.SETUP)
            complete()
            capture('loaded-17')
            choose('Defense', 'Additional Fighting Style')
            capture('extra-defense')
            edit('AC Armor Description', 'Unarmored')
            capture('extra-defense-unarmored')
            edit('AC Armor Description', 'Plate')
            capture('extra-defense-restored')
            choose('Dueling', 'Additional Fighting Style')
            capture('extra-dueling-bow')
            edit('AC Shield Bonus Description', 'Shield')
            edit('Attack.1.Weapon Selection', 'Longsword')
            capture('extra-dueling-sword')
            choose('Defense')
            capture('primary-defense-extra-dueling')
            choose('Archery')
            capture('primary-archery-extra-dueling')
            report['reduce_level'] = c.script('call', path=remote, name='ApplyClasses', args=['Fighter (Champion) 9', False])
            capture('reduced-9')
            c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Champion additional style compatibility'})
            saved = base + '-lower9.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['lower_close'] = document_controls.close_saved(c, remote)
            opened = False
            report['lower_pdf'] = str(c.fetch(remote, folder / 'reader-lower9.pdf'))
            remote, report['lower_snapshot'] = document_controls.reopen_snapshot(c, remote)
            opened = True
            c.ensure_document(remote)
            script(profile.SETUP)
            complete()
            capture('cold-9')
            report['restore_level'] = c.script('call', path=remote, name='ApplyClasses', args=['Fighter (Champion) 17', False])
            capture('restored-17')
            c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Champion additional style compatibility'})
            saved = base + '-restored17.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['restored_close'] = document_controls.close_saved(c, remote)
            opened = False
            report['restored_pdf'] = str(c.fetch(remote, folder / 'reader-restored17.pdf'))
            remote, report['restored_snapshot'] = document_controls.reopen_snapshot(c, remote)
            opened = True
            c.ensure_document(remote)
            script(profile.SETUP)
            complete()
            choose('Dueling', 'Additional Fighting Style')
            capture('reselected-extra-17')
            c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Champion additional style compatibility'})
            saved = base + '-saved.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['close'] = document_controls.close_saved(c, remote)
            opened = False
            output = c.fetch(remote, folder / 'reader-chosen17.pdf')
            assert script_hashes(output) == script_hashes(source)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == native['input_sha256']
            if a.install_observer_once:
                assert [r['invocation_count'] for r in report['timer_requests']] == list(range(1, 10)) + [1, 2, 1], 'Require each actual observer invocation in its expected Reader process'
            report.update(passed=True, pdf=str(output))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    for _ in range(5):
                        if not any(w.get('class') == '#32768' for w in c.command('inspect')):
                            break
                        c.command('keys', keys='{ESC}')
                    if pending:
                        try:
                            report['cleanup_pending'] = c.script_result(pending, timeout=45)
                        except Exception as pending_error:
                            report['cleanup_pending_error'] = str(pending_error)
                        finally:
                            pending = None
                    saved = base + '-failed-retained.pdf'
                    c.script('save', path=remote, output=saved)
                    report['cleanup_close'] = document_controls.close_saved(c, saved)
                    c.fetch(saved, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'additional.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
