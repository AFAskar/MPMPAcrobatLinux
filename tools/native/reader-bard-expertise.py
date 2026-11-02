#!/usr/bin/env python3
"""Real offered Bard expertise menus, progression/removal and saved skill totals.

Qualifies the explicit native profile in Reader. Other class choices, feats/ASIs,
and fresh native/Reader persistence remain separate gates.
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


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


style = module('style', 'default-style-persistence.py')
field_state = module('field_state', 'field-state-comparison.py')
menus = module('menus', 'warlock-reader-invocations.py')
native_profile = module('profile', 'bard-expertise.py')
widget_state = module('widget_state', 'verify-bard-slot-widgets.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--readiness', type=Path, required=True)
    args = parser.parse_args()
    native = json.loads(args.native.read_text())
    ready = json.loads(args.readiness.read_text())
    assert native['passed'] and ready['passed'] and len(ready['cases']) == 24
    assert ready['harness_sha256'] == c.harness_fingerprint()
    source = Path(native['input'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == native['source_sha256']
    observer = (ROOT / 'tools/native/bard-expertise-observer.js').read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == native['observer_sha256']
    folder = ROOT / 'output/testing' / ('reader-bard-expertise-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/bard-expertise-' + str(time.time_ns()))
    remote = base + '.pdf'
    opened = False
    pending = None
    report = {'passed': False, 'scope': __doc__, 'native': str(args.native), 'input': str(source),
              'source_sha256': native['source_sha256'], 'readiness': str(args.readiness),
              'observer_sha256': native['observer_sha256'], 'phases': [], 'menu_selections': []}

    def checkpoint():
        (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def choose(skill, count, maximum):
        nonlocal pending
        pending = c.script_submit('call', path=remote, name='ClassFeatureOptions', args=[])
        actions = []
        phase_folder = folder / ('menu-' + str(len(report['menu_selections'])))
        phase_folder.mkdir()
        for label in ['Bard (College of Lore)', f'Expertise (selected {count} of {maximum})', skill]:
            popup = menus.popup(label, phase_folder)
            matches = [(i, item) for i, item in enumerate(popup['children'])
                       if item.get('type') == 'ControlType.MenuItem' and item['name'].split('\t')[0].strip() == label]
            assert len(matches) == 1, ('Missing/ambiguous actual offered menu item', label)
            index, item = matches[0]
            action = c.command('activate_menu', owner=popup['native_window_handle'], position=index, name=item['name'])
            actions.append({'menu': popup, 'chosen': item, 'action': action})
        completion = c.script_result(pending, timeout=120)
        pending = None
        c.ensure_document(remote)
        report['menu_selections'].append({'skill': skill, 'count_before': count,
                                          'maximum': maximum, 'actions': actions, 'completion': completion})
        checkpoint()

    def capture(label):
        nonlocal remote, pending
        c.script('set', path=remote, values={'User Script': observer})
        pending = c.script_submit('call', path=remote, name='RunUserScript', args=[False])
        c.script_result(pending, timeout=120)
        pending = None
        summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
        c.script('set', path=remote, values={'User Script': ''})
        diagnostic = base + '-' + label + '-diagnostic.pdf'
        c.script('save', path=remote, output=diagnostic)
        remote = diagnostic
        c.script('set', path=remote, values={'PC Name': 'Bard compatibility'})
        saved = base + '-' + label + '.pdf'
        c.script('save', path=remote, output=saved)
        remote = saved
        report['phases'].append({'label': label, 'diagnostic': diagnostic, 'reader_path': saved, 'summary': summary})
        checkpoint()

    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow'
                        and '.pdf' in e.get('name', '').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP + [str(source), 'mpmb-test@127.0.0.1:MPMB-Testing/runs/' +
                                    remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            c.script('set', path=remote, values={'PC Name': 'Bard compatibility'})
            initial = c.script('read', path=remote, fields=native_profile.PROFS)['fields']
            assert all(value == 'Off' for value in initial.values())
            report['proficiency_activations'] = []
            for name in native_profile.PROFS:
                focus = c.script('focus', path=remote, field=name)
                key = c.command('keys', keys=' ')
                value = c.script('read', path=remote, fields=[name])['fields'][name]
                assert value == 'True'
                report['proficiency_activations'].append({'name': name, 'focus': focus, 'key': key, 'value': value})
            choose('Acrobatics', 0, 2)
            choose('Arcana', 1, 2)
            capture('expertise5')
            c.script('call', path=remote, name='ApplyClasses', args=['Bard (College of Lore) 9', False])
            choose('Perception', 2, 4)
            choose('Persuasion', 3, 4)
            capture('expertise9')
            choose('Arcana', 4, 4)
            capture('removed-arcana')
            c.script('call', path=remote, name='ApplyClasses', args=['Bard 1', False])
            capture('downleveled')
            report['close'] = c.script('close', path=remote)
            opened = False
            for phase in report['phases']:
                local = c.fetch(phase['reader_path'], folder / (phase['label'] + '.pdf'))
                diagnostic = c.fetch(phase['diagnostic'], folder / (phase['label'] + '-diagnostic.pdf'))
                observed = style.saved_capture(diagnostic, phase['summary'], source)
                phase['state'] = observed
                phase['pdf'] = str(local)
                expected = next(p for p in native['phases'] if p['label'] == phase['label'])
                assert observed == expected['state'], ('Complete expertise observation differs', phase['label'])
                phase['api_raw_comparison'] = field_state.compare(local, observed['fields'])
                phase['displays'] = {}
                for name in native_profile.SKILLS:
                    checked = inspect(local, {name: observed['fields'][name]})
                    phase['displays'][name] = [w['appearance_text'] for w in checked['widgets'] if w['visible']]
                assert phase['displays'] == expected['displays'], ('Actual calculated skill displays differ', phase['label'])
                boxes = {name: value for name, value in observed['fields'].items() if name.endswith((' Prof', ' Exp'))}
                phase['checkbox_appearances'] = widget_state.widgets(local, boxes)
                assert script_hashes(local) == script_hashes(source)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == native['source_sha256']
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    for _ in range(5):
                        if not any(e.get('class') == '#32768' for e in c.command('inspect')):
                            break
                        c.command('keys', keys='{ESC}')
                    shot = c.command('screenshot')
                    c.fetch(shot['path'], folder / 'failure.png')
                    if pending:
                        report['original_completion'] = c.script_result(pending, timeout=90)
                    retained = base + '-failed-retained.pdf'
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = c.script('close', path=retained)
                    c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'expertise.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
