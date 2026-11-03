#!/usr/bin/env python3
"""Real Reader Champion resource progression/spending and separate rest recovery.

Original ApplyClasses/resetLimFeaUsed callbacks in the target document context;
physical usage commits and cold spent-state reopen. Extra style/feats remain
unselected, so this is a bounded resource workflow only.
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


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


profile = module('profile', 'fighter-styles.py')
style = module('style', 'default-style-persistence.py')
field_state = module('field_state', 'field-state-comparison.py')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--readiness', type=Path, required=True)
    a = p.parse_args()
    native = json.loads(a.native.read_text())
    ready = json.loads(a.readiness.read_text())
    assert native['passed'] and ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = Path(native['input'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == native['input_sha256']
    observer = (ROOT / 'tools/native/fighter-style-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == native['observer_sha256']
    folder = ROOT / 'output/testing' / ('reader-fighter-resources-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/fighter-resources-' + str(time.time_ns()))
    remote = base + '.pdf'
    report = {'passed': False, 'scope': __doc__, 'native': str(a.native.resolve()),
              'input': str(source), 'input_sha256': native['input_sha256'], 'readiness': str(a.readiness),
              'observer_sha256': native['observer_sha256'], 'phases': [], 'inputs': [], 'choices': []}
    pending = None
    opened = False
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
    def edit(n, v):
        focused = c.script('focus', path=remote, field=n)
        if v:
            result = c.command('paste', value=v)
            assert result['verified'] and result['value'] == v
        else:
            result = c.command('keys', keys='^a{BACKSPACE}{TAB}')
            cleared = c.script('read', path=remote, fields=[n])['fields'][n]
            assert cleared == '', ('Observed focused field did not clear', n, cleared)
        c.ensure_document(remote)
        report['inputs'].append({'field': n, 'value': v, 'focus': focused, 'input': result})
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
            assert c.script('read', path=remote, fields=['Class and Levels', 'Character Level', 'Str', 'Dex', 'Con'])['fields'] == {
                'Class and Levels': 'Fighter (Champion)', 'Character Level': '6', 'Str': '18', 'Dex': '18', 'Con': '12'}
            script(profile.SETUP)
            complete()
            capture('loaded-6')
            for level in [9, 11, 17]:
                result = c.script('call', path=remote, name='ApplyClasses', args=['Fighter (Champion) ' + str(level), False])
                report.setdefault('progression', []).append({'level': level, 'result': result})
                c.ensure_document(remote)
                capture('level-' + str(level))
            for row, value in [(1, '1'), (2, '2'), (3, '2')]:
                edit('Limited Feature Used ' + str(row), value)
            capture('spent-17')
            report['short_rest'] = c.script('call', path=remote, name='resetLimFeaUsed', args=['short rest'])
            capture('short-rest')
            c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Fighter resource compatibility'})
            saved = base + '-spent.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['spent_close'] = c.script('close', path=remote)
            opened = False
            report['spent_pdf'] = str(c.fetch(remote, folder / 'reader-spent.pdf'))
            opened = True
            c.ensure_document(remote)
            script(profile.SETUP)
            complete()
            capture('cold-spent')
            report['long_rest'] = c.script('call', path=remote, name='resetLimFeaUsed', args=['long rest'])
            capture('long-rest')
            c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Fighter resource compatibility'})
            saved = base + '-saved.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['close'] = c.script('close', path=remote)
            opened = False
            output = c.fetch(remote, folder / 'reader-rested.pdf')
            assert script_hashes(output) == script_hashes(source)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == native['input_sha256']
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
                        report['cleanup_pending'] = c.script_result(pending, timeout=45)
                    saved = base + '-failed-retained.pdf'
                    c.script('save', path=remote, output=saved)
                    report['cleanup_close'] = c.script('close', path=saved)
                    c.fetch(saved, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'resources.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
