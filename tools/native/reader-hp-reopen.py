#!/usr/bin/env python3
"""Reader opens native automatic HP, removes Tough and progresses after cold reopen."""
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
from verify import inspect, script_hashes


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


profile = module('profile', 'reader-hp-workflow.py')
style = module('style', 'default-style-persistence.py')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--readiness', type=Path, required=True)
    a = p.parse_args()
    native = json.loads(a.native.read_text())
    ready = json.loads(a.readiness.read_text())
    assert native['passed'] and ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = Path(native['output'])
    current = native['phases'][-1]['state']
    hp_before = int(current['fields']['HP Max'])
    con_before = int(current['fields']['Con'])
    level = int(current['fields']['Character Level'])
    die = int(current['fields']['HD1 Die'])
    assert int(current['fields']['HD1 Level']) == level
    assert current['fields']['Class and Levels'].split()[0] in ['Bard', 'Fighter', 'Monk']
    assert hp_before == current['totals']['fixed'] + 2 * level, 'This bounded profile requires Tough as its only extra HP contribution'
    previous = json.loads(Path(native['reader']).read_text())
    feat_field = previous.get('feat_field', 'Feat Name 1')
    feat_index = int(feat_field.split()[-1]) - 1
    assert current['feats']['known'][feat_index] == 'tough'
    removed_feats = list(current['feats']['known'])
    removed_feats[feat_index] = ''
    first_con, second_con = con_before + 2, con_before + 4
    first_hp, removed_hp = hp_before + level, hp_before - level
    progression = re.sub(r'\s*\d+\s*$', '', current['fields']['Class and Levels']).strip() + ' ' + str(level + 1)
    progression_hp = removed_hp + die // 2 + 1 + first_con // 2 - 5
    code = profile.original_blur(source)
    observer = (ROOT / 'tools/native/hp-workflow-observer.js').read_text()
    folder = ROOT / 'output/testing' / ('reader-hp-reopen-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/hp-reopen-' + str(time.time_ns()))
    remote = base + '.pdf'
    report = {'passed': False, 'scope': __doc__, 'native': str(a.native.resolve()), 'input': str(source),
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'readiness': str(a.readiness), 'phases': [],
              'feat_field': feat_field, 'progression_input': progression,
              'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    opened = False
    pending = None

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

    def capture(label, hp, con, level, tough):
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
        assert not state['errors'] and state['trace']
        assert tuple(state['fields'][n] for n in ['HP Max', 'Con', 'Character Level', 'HD1 Level']) == (str(hp), str(con), str(level), str(level))
        assert state['mapping'].split(',')[3] == 'fixed'
        assert state['feats']['known'] == (current['feats']['known'] if tough else removed_feats)
        assert tuple(state['fields'][n] for n in ['HP Current', 'HP Temp', 'HD1 Used']) == ('30', '5', '2')
        assert inspect(local, {n: state['fields'][n] for n in ['HP Max', 'HP Current', 'Con', 'Con Mod']})['passed']
        report['phases'].append({'label': label, 'state': state, 'diagnostic': str(local), 'summary': summary})
        (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def con(value):
        focus = c.script('focus', path=remote, field='Con')
        result = c.command('paste', value=str(value))
        assert result['verified'] and result['value'] == str(value)
        return {'focus': focus, 'paste': result}

    def save_close(label):
        nonlocal remote, opened
        restore = "var iFileName='Restore HP action.js';tDoc.getField('Con').setAction('OnBlur'," + json.dumps(code) + ');'
        script(restore)
        complete()
        c.script('set', path=remote, values={'User Script': '', 'PC Name': 'HP compatibility'})
        saved = base + '-' + label + '.pdf'
        c.script('save', path=remote, output=saved)
        remote = saved
        result = c.script('close', path=remote)
        opened = False
        local = c.fetch(remote, folder / (label + '.pdf'))
        assert profile.original_blur(local) == code and script_hashes(local) == script_hashes(source)
        return {'pdf': str(local), 'close': result}

    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()]
            subprocess.run(c.SCP + [str(source), c.SCP_TARGET + ':MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            initial = c.script('read', path=remote, fields=['HP Max', 'Con'])['fields']
            assert initial == {'HP Max': str(hp_before), 'Con': str(con_before)}
            script(profile.setup(code))
            complete()
            report['first_con_edit'] = con(first_con)
            capture('native-input-con' + str(first_con), first_hp, first_con, level, True)
            c.script('set', path=remote, values={feat_field: ''})
            capture('removed-tough', removed_hp, first_con, level, False)
            report['second_con_edit'] = con(second_con)
            capture('con' + str(second_con) + '-without-tough', hp_before, second_con, level, False)
            report['first_save'] = save_close('reader-before-reopen')
            opened = True
            c.ensure_document(remote)
            assert c.script('read', path=remote, fields=['HP Max', 'Con'])['fields'] == {'HP Max': str(hp_before), 'Con': str(second_con)}
            script(profile.setup(code))
            complete()
            report['cold_con_edit'] = con(first_con)
            capture('cold-reader-con' + str(first_con), removed_hp, first_con, level, False)
            report['progression'] = c.script('call', path=remote, name='ApplyClasses', args=[progression, False])
            capture('progressed-' + str(level + 1), progression_hp, first_con, level + 1, False)
            report['final_save'] = save_close('reader-final')
            assert hashlib.sha256(source.read_bytes()).hexdigest() == report['input_sha256']
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    if pending:
                        report['cleanup_result'] = c.script_result(pending, timeout=45)
                    retained = base + '-failed-retained.pdf'
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
