#!/usr/bin/env python3
"""Native additional-style saves → changed Reader saves and cold Reader edits.

Qualifies compound Archery/Dueling conditional callbacks and a native level9
snapshot restoring17 with an empty additional slot, followed by genuine choice.
Only the bounded2014 Champion profile; no full class/subclass coverage claim.
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
    p.add_argument('--reader-profile', type=Path, required=True)
    a = p.parse_args()
    native = json.loads(a.native.read_text())
    reader = json.loads(a.reader_profile.read_text())
    mode = native.get('diagnostic_mode', 'repeated-RunUserScript')
    assert mode in (diagnostics.MODE, 'repeated-RunUserScript')
    assert reader.get('diagnostic_mode', 'repeated-RunUserScript') == mode
    if mode == diagnostics.MODE:
        assert native.get('diagnostic_helper_sha256') == reader.get('diagnostic_helper_sha256') == hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()
    assert reader['passed'] and {p['label']:p['state'] for p in reader['phases']} == {p['label']:p['state'] for p in native['phases']}
    wanted = {p['label']:p['state'] for p in native['phases']}
    bow = json.loads(json.dumps(wanted['extra-dueling-bow']))
    bow['fields'].update({'AC':'20','AC Shield Bonus':'2','AC Shield Bonus Description':'Shield','Attack.1.Weapon':'Longbow'})
    ready = json.loads(a.readiness.read_text())
    assert native['passed'] and ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = Path(native['pdf'])
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    observer = (ROOT / 'tools/native/fighter-additional-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == native['observer_sha256']
    folder = ROOT / 'output/testing' / ('reader-fighter-additional-reopen-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/fighter-additional-' + str(time.time_ns()))
    remote = base + '.pdf'
    report = {'passed': False, 'scope': __doc__, 'native': str(a.native.resolve()),
              'input': str(source), 'input_sha256': source_hash, 'reader_profile':str(a.reader_profile.resolve()), 'cases':[], 'readiness': str(a.readiness),
              'observer_sha256': native['observer_sha256'], 'phases': [], 'inputs': [], 'choices': []}
    report['diagnostic_helper_sha256'] = hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()
    report['diagnostic_mode'] = mode
    report['test_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['input_helper_sha256'] = hashlib.sha256((ROOT / 'tools/native/reader-ascii-input.py').read_bytes()).hexdigest()
    pending = None
    opened = False
    def script(text):
        nonlocal pending
        if mode == diagnostics.MODE:
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
        result = ascii_input.commit(c, remote, n, v)
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
    def capture(label, expected):
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
        assert not state['errors'] and state == expected, (label, state, expected)
        field_state.compare(local, dict(state['fields'], **state['resources']))
        visible = inspect(local, {n: state['fields'][n] for n in ['AC', 'Attack.1.To Hit', 'Attack.1.Damage', 'Attack.1.Weapon']})
        assert visible['passed'], visible
        report['phases'].append({'label': label, 'state': state, 'pdf': str(local), 'summary': summary, 'visible': visible})
        (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')
    try:
        with c.desktop_lock():
            assert not [w for w in c.command('inspect') if w.get('class') == 'AcrobatSDIWindow' and '.pdf' in w.get('name', '').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP + [str(source), c.SCP_TARGET + ':MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            script(profile.SETUP)
            complete()
            capture('compound-loaded-17', wanted['reselected-extra-17'])
            edit('Attack.1.Weapon Selection', 'Longbow')
            capture('compound-bow-17', bow)
            c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Champion additional style compatibility'})
            saved = base + '-changed-bow.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['bow_close'] = document_controls.close_saved(c, remote)
            opened = False
            report['bow_pdf'] = str(c.fetch(remote, folder / 'reader-bow.pdf'))
            remote, report['bow_snapshot'] = document_controls.reopen_snapshot(c, remote)
            opened = True
            c.ensure_document(remote)
            script(profile.SETUP)
            complete()
            capture('compound-cold-bow-17', bow)
            edit('Attack.1.Weapon Selection', 'Longsword')
            capture('compound-cold-sword-17', wanted['extra-dueling-sword'])
            c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Champion additional style compatibility'})
            saved = base + '-final-sword.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['sword_close'] = document_controls.close_saved(c, remote)
            opened = False
            report['sword_pdf'] = str(c.fetch(remote, folder / 'reader-sword.pdf'))
            assert script_hashes(Path(report['sword_pdf'])) == script_hashes(source)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
            source = Path(native['reduced_pdf'])
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            report['reduced_input'] = {'path':str(source),'sha256':source_hash}
            remote = base + '-native-lower9.pdf'
            subprocess.run(c.SCP + [str(source), c.SCP_TARGET + ':MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            script(profile.SETUP)
            complete()
            capture('native-cold-9', wanted['cold-9'])
            report['restore_level'] = c.script('call', path=remote, name='ApplyClasses', args=['Fighter (Champion) 17', False])
            capture('native-restored-17', wanted['restored-17'])
            choose('Dueling', 'Additional Fighting Style')
            capture('native-reselected-extra-17', wanted['reselected-extra-17'])
            c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Champion additional style compatibility'})
            saved = base + '-saved.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['close'] = document_controls.close_saved(c, remote)
            opened = False
            output = c.fetch(remote, folder / 'reader-chosen17.pdf')
            assert script_hashes(output) == script_hashes(source)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
            if mode == diagnostics.MODE:
                assert [r['invocation_count'] for r in report['timer_requests']] == [1, 2, 1, 2, 1, 2, 3]
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
