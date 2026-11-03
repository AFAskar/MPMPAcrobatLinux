#!/usr/bin/env python3
"""Native saved styles → Reader changed saves → cold Reader positive controls.

Only the bounded 2014 Champion6 Archery/Defense/Dueling gear conditions are
qualified. No new style is selected here; persisted callbacks must remain live.
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


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--persistence', type=Path, required=True)
    p.add_argument('--readiness', type=Path, required=True)
    a = p.parse_args()
    prior = json.loads(a.persistence.read_text())
    ready = json.loads(a.readiness.read_text())
    assert prior['passed'] and ready['passed'] and len(ready['cases']) == 24
    assert ready['harness_sha256'] == c.harness_fingerprint()
    profile = module('profile', 'fighter-styles.py')
    style = module('style', 'default-style-persistence.py')
    fields = module('fields', 'field-state-comparison.py')
    observer = (ROOT / 'tools/native/fighter-style-observer.js').read_text()
    folder = ROOT / 'output/testing' / ('reader-fighter-style-reopen-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    report = {'passed': False, 'scope': __doc__, 'persistence': str(a.persistence.resolve()),
              'readiness': str(a.readiness.resolve()), 'observer_sha256': hashlib.sha256(observer.encode()).hexdigest(),
              'cases': [], 'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    opened = False
    pending = None
    remote = None
    source = None
    def script(text):
        nonlocal pending
        c.script('set', path=remote, values={'User Script': text})
        pending = c.script_submit('call', path=remote, name='RunUserScript', args=[False])
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
            assert c.script('read', path=remote, fields=[n])['fields'][n] == ''
        c.ensure_document(remote)
        return {'field': n, 'value': v, 'focus': focused, 'input': result}
    def capture(label, expected):
        nonlocal remote
        script(observer)
        summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
        c.script('set', path=remote, values={'User Script': ''})
        saved = base + '-' + label + '-diagnostic.pdf'
        c.script('save', path=remote, output=saved)
        remote = saved
        local = c.fetch(remote, folder / (label + '-diagnostic.pdf'))
        state = style.saved_capture(local, summary, source)
        assert not state['errors'] and state == expected, (label, state, expected)
        canonical = fields.compare(local, dict(state['fields'], **state['resources']))
        visible = inspect(local, {n: state['fields'][n] for n in ['AC', 'Attack.1.To Hit', 'Attack.1.Damage', 'Attack.1.Weapon']})
        assert visible['passed'] and script_hashes(local) == script_hashes(source)
        item['states'].append({'label': label, 'state': state, 'pdf': str(local), 'summary': summary,
                               'canonical': canonical, 'visible': visible})
        (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')
    def save_close(label):
        nonlocal opened, remote
        c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Fighter compatibility'})
        saved = base + '-' + label + '.pdf'
        c.script('save', path=remote, output=saved)
        remote = saved
        closed = c.script('close', path=remote)
        opened = False
        local = c.fetch(remote, folder / (label + '.pdf'))
        assert script_hashes(local) == script_hashes(source)
        return {'pdf': str(local), 'close': closed}
    try:
        with c.desktop_lock():
            assert not [w for w in c.command('inspect') if w.get('class') == 'AcrobatSDIWindow' and '.pdf' in w.get('name', '').lower()], 'Pre-existing Reader document'
            native = [v for v in prior['cases'] if v['label'].startswith('native-')]
            assert len(native) == 3
            # Outputs of the three native epochs contain the NEXT style.
            for index, candidate in enumerate(native):
                source = Path(candidate['pdf'])
                if index == 0:
                    mode = 'defense'
                    negative = native[1]['states'][1]['state']
                    positive = native[1]['states'][2]['state']
                    off = [('AC Armor Description', 'Unarmored')]
                    on = [('AC Armor Description', 'Plate')]
                elif index == 1:
                    mode = 'dueling'
                    negative = native[2]['states'][1]['state']
                    positive = native[2]['states'][0]['state']
                    off = [('AC Shield Bonus Description', ''), ('Attack.1.Weapon Selection', 'Longbow')]
                    on = [('AC Shield Bonus Description', 'Shield'), ('Attack.1.Weapon Selection', 'Longsword')]
                else:
                    mode = 'archery'
                    negative = native[0]['states'][1]['state']
                    positive = native[0]['states'][2]['state']
                    off = [('Attack.1.Weapon Selection', 'Longsword')]
                    on = [('Attack.1.Weapon Selection', 'Longbow')]
                base = c.remote_path('runs/style-reopen-' + str(time.time_ns()))
                remote = base + '.pdf'
                item = {'style': mode, 'input': str(source), 'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'states': []}
                report['cases'].append(item)
                subprocess.run(c.SCP + [str(source), 'mpmb-test@127.0.0.1:MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
                opened = True
                c.ensure_document(remote)
                script(profile.SETUP)
                capture(mode + '-loaded', candidate['states'][-1]['state'])
                item['off_inputs'] = [edit(n, v) for n, v in off]
                capture(mode + '-negative', negative)
                item['changed_save'] = save_close(mode + '-negative-saved')
                opened = True
                c.ensure_document(remote)
                script(profile.SETUP)
                item['on_inputs'] = [edit(n, v) for n, v in on]
                capture(mode + '-cold-positive', positive)
                item['final_save'] = save_close(mode + '-final')
                assert hashlib.sha256(source.read_bytes()).hexdigest() == item['input_sha256']
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    if pending:
                        report['cleanup_pending'] = c.script_result(pending, timeout=90)
                    retained = remote[:-4] + '-failed-retained.pdf'
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = c.script('close', path=retained)
                    c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'reopen.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
