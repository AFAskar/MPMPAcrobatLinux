#!/usr/bin/env python3
"""Compare an original 2024 Swords warning workflow with real Reader.

Original all-source buttons, ApplyClasses parser and three explicit Bard tools.
This is warning attribution, not a clean class pass or full subclass/dialog
qualification. The original class dropdown and fighting-style choice are not
exercised here. Raw console text is retained; only line endings are normalized.
Decoded JSON object member order is ignored; all members and array order remain
strict.
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
from verify import script_hashes
import fighter_additional_diagnostics as diagnostics
import reader_document_controls as closing
from reference_2024_qualification import require_2024_reference


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True, help='Native observation folder')
    parser.add_argument('--instrumentation', type=Path, required=True, help='Startup observer preparation manifest')
    parser.add_argument('--readiness', type=Path, required=True)
    args = parser.parse_args()
    ready = json.loads(args.readiness.read_text())
    qualification = require_2024_reference(ready, c.harness_fingerprint())
    native = json.loads((args.native / 'native-probe.json').read_text())
    manifest = json.loads(args.instrumentation.read_text())
    assert manifest['passed'] and manifest['mode'] == 'startup-script-timer'
    assert native['passed'] and not native['diagnostics']['errors']
    source = args.input.resolve()
    assert source == Path(manifest['input']).resolve()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest['input_sha256']
    assert hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest() == manifest['diagnostic_helper_sha256']
    style = module('style', 'default-style-persistence.py')
    fields = module('fields', 'field-state-comparison.py')
    typing = module('typing_control', 'reader-ascii-input.py')
    console = module('console_control', 'reader-console.py')
    wanted = style.saved_capture(args.native / 'native-diagnostic.pdf', native['stages'][-2]['result'], source)
    assert wanted['identity'] == {'level': 3, 'subclass': 'bard-college of swords'}
    assert wanted['sources'] == {'globalExcl': [], 'classExcl': []}
    assert all(value in json.dumps(wanted['fields']) for value in ['Flute', 'Lute', 'Drum'])
    messages = [m['text'] for m in native['diagnostics']['console']['messages']]
    assert len(messages) == 9 and messages[-1] == 'MPMB 2024 Swords warning observer sentinel'
    assert all('discrepancy between the `choices` array' in message for message in messages[:-1])
    # Original displayError(false, warning) records the same eight warnings in
    # the observer as well as the console. Retain and compare both channels;
    # they are expected observations, never an empty-error/clean-class pass.
    assert len(wanted['errors']) == 8 and all(item['error'] == 'false' for item in wanted['errors'])
    assert [item['context'] for item in wanted['errors']] == [message.rstrip('\n') for message in messages[:-1]]
    folder = ROOT / 'output/testing' / ('reader-swords-2024-warning-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    remote = c.remote_path('runs/swords-2024-warning-' + str(time.time_ns()) + '.pdf')
    opened = False
    pending = None
    report = {'passed': False, 'clean_workflow': False, 'scope': __doc__,
              'input': str(source), 'input_sha256': manifest['input_sha256'],
              'native': str(args.native.resolve()), 'readiness': str(args.readiness.resolve()),
              'reference_qualification': qualification, 'source_controls': [], 'tools': [],
              'early_console': [], 'inputs': []}

    def dialog(title):
        deadline = time.monotonic() + 60
        while True:
            rows = c.command('inspect')
            roots = [r for r in rows if r.get('class') == '#32770' and r.get('name') == title]
            if roots:
                assert len(roots) == 1, rows
                return roots[0]['handle'], rows
            assert time.monotonic() < deadline, ('Dialog not observed', title, rows)
            time.sleep(.1)

    def button(title, label):
        owner, rows = dialog(title)
        offered = [r for r in rows if r.get('owner') == owner and r.get('class') == 'Button'
                   and r.get('name') == label and r.get('enabled')
                   and r['rect'][2] > 0 and r['rect'][3] > 0]
        assert len(offered) == 1, (title, label, rows)
        action = c.command('click_dialog_control', owner=owner, handle=offered[0]['handle'], name=label)
        report['source_controls'].append({'title': title, 'control': offered[0], 'action': action})

    def live_console(rows):
        roots = [r for r in rows if r.get('class') == '#32770' and r.get('name') == 'JavaScript Debugger']
        assert len(roots) == 1, rows
        owner = roots[0]['handle']
        edits = [r for r in rows if r.get('owner') == owner and r.get('class') == 'RICHEDIT50W']
        assert len(edits) == 1, rows
        result = {'owner': owner, 'edit': edits[0]['handle'], 'rows': rows,
                  'live': c.command('dialog_control', owner=owner, handle=edits[0]['handle'])}
        result['close'] = console.close_console(result)
        return result

    try:
        with c.desktop_lock():
            assert not [w for w in c.command('inspect') if w.get('class') == 'AcrobatSDIWindow'
                        and '.pdf' in w.get('name', '').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP + [str(source), 'mpmb-test@127.0.0.1:MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            deadline = time.monotonic() + 60
            while c.script('read', path=remote, fields=['User Script'])['fields']['User Script'] != '// MPMB workflow observer installed':
                assert time.monotonic() < deadline, 'Startup observer was not installed'
            pending = c.script_submit('call', path=remote, name='resourceDecisionDialog', args=[])
            button('SOURCE SELECTION DIALOG', '>>')
            button('SOURCE SELECTION DIALOG', 'Classes/Archetypes')
            button('CLASSES OR ARCHETYPES SOURCE SELECTION DIALOG', '>>')
            button('CLASSES OR ARCHETYPES SOURCE SELECTION DIALOG', 'Apply')
            button('SOURCE SELECTION DIALOG', 'Apply')
            report['source_result'] = c.script_result(pending, timeout=240)
            pending = None
            report['clear_class'] = c.script('call', path=remote, name='ApplyClasses', args=['', False])
            for name in ['Str', 'Dex', 'Con', 'Int', 'Wis', 'Cha']:
                report['inputs'].append(typing.commit(c, remote, name, '18'))
            pending = c.script_submit('call', path=remote, name='ApplyClasses', args=['Bard (College of Swords) 3', False])
            deadline = time.monotonic() + 300
            while True:
                rows = c.command('inspect')
                asks = [r for r in rows if r.get('class') == '#32770' and r.get('name') == 'ASK USER DIALOG']
                if any(r.get('name', '').startswith('MPMB_RESULT') for r in rows):
                    break
                if asks:
                    assert len(asks) == 1 and not report['tools'], rows
                    owner = asks[0]['handle']
                    labels = {r.get('name') for r in rows if r.get('owner') == owner}
                    assert {'Select proficiencies', 'Tools', 'Bard'} <= labels, labels
                    edits = [r for r in rows if r.get('owner') == owner and r.get('class') in ['Edit', 'RICHEDIT50W']
                             and r.get('enabled') and r.get('read_only') is False]
                    live = [(r, c.command('dialog_control', owner=owner, handle=r['handle'])) for r in edits]
                    assert len(live) == 3, live
                    for index, value in enumerate(['Flute', 'Lute', 'Drum'], 1):
                        targets = [(r, state) for r, state in live if state['text'] == 'Musical instrument (' + str(index) + '/3)']
                        assert len(targets) == 1, live
                        target, before = targets[0]
                        focus = c.command('focus_control', owner=owner, handle=target['handle'])
                        assert focus['focused']
                        typed = c.command('paste', value=value)
                        after = c.command('dialog_control', owner=owner, handle=target['handle'])
                        assert after['text'] == value, after
                        report['tools'].append({'control': target, 'before': before, 'value': value, 'focus': focus, 'input': typed, 'after': after})
                    button('ASK USER DIALOG', 'OK')
                elif any(r.get('name') == 'CHANGES ALERT DIALOG' for r in rows):
                    button('CHANGES ALERT DIALOG', 'Close')
                elif any(r.get('name') == 'JavaScript Debugger' for r in rows):
                    # Original warnings show a modeless debugger. Leave it
                    # alone until the class receipt/deferred modals finish.
                    pass
                else:
                    unknown = [r for r in rows if r.get('class') == '#32770']
                    assert not unknown, unknown
                assert time.monotonic() < deadline, 'Class request did not finish'
                time.sleep(.1)
            report['class_result'] = c.script_result(pending, timeout=240)
            pending = None
            assert len(report['tools']) == 3
            # The original deferred summary can appear after result delivery.
            # Do not focus a debugger disabled by that modal or replay the call.
            deadline = time.monotonic() + 60
            while True:
                rows = c.command('inspect')
                summaries = [r for r in rows if r.get('class') == '#32770'
                             and r.get('name') == 'CHANGES ALERT DIALOG']
                debuggers = [r for r in rows if r.get('class') == '#32770'
                             and r.get('name') == 'JavaScript Debugger']
                if summaries and summaries[0].get('enabled'):
                    button('CHANGES ALERT DIALOG', 'Close')
                elif debuggers and debuggers[0].get('enabled') and not summaries:
                    report['early_console'].append(live_console(rows))
                    break
                else:
                    assert time.monotonic() < deadline, ('Deferred class dialogs did not finish', rows)
                    time.sleep(.1)
            report['timer_request'] = diagnostics.reader_request(c, remote)
            summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
            c.script('set', path=remote, values={'User Script': ''})
            saved = remote[:-4] + '-diagnostic.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            pdf = c.fetch(remote, folder / 'reader-diagnostic.pdf')
            state = style.saved_capture(pdf, summary, source)
            report['state'] = state
            assert state == wanted, (state, wanted)
            report['canonical'] = fields.compare(pdf, dict(state['fields'], **state['resources']))
            assert script_hashes(pdf) == script_hashes(source)
            c.script('set', path=remote, values={'User Script': '// MPMB workflow console request'})
            _, rows = dialog('JavaScript Debugger')
            report['console'] = live_console(rows)
            normalize = lambda value: value.replace('\r\n', '\n').replace('\r', '\n').rstrip('\n')
            assert normalize(report['console']['live']['text']) == normalize('\n'.join(messages)), report['console']['live']
            marker = c.script('read', path=remote, fields=['User Script'])['fields']['User Script']
            assert marker == '// MPMB workflow console complete:1', marker
            c.script('set', path=remote, values={'User Script': '', 'PC Name': '2024 Swords warning observation'})
            saved = remote[:-4] + '-final.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['close'] = closing.close_saved(c, remote)
            opened = False
            final = c.fetch(remote, folder / 'reader.pdf')
            report['final_canonical'] = fields.compare(final, dict(state['fields'], **state['resources']))
            assert script_hashes(final) == script_hashes(source)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest['input_sha256']
            assert c.harness_fingerprint() == ready['harness_sha256']
            report.update(passed=True, matching_original_warning_messages=8, pdf=str(final))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    shot = c.command('screenshot')
                    c.fetch(shot['path'], folder / 'original-failure.png')
                    # Never replay an uncertain class/source request or hide an
                    # outstanding modal. Its request and owned document remain.
                    report['retained_request'] = pending
                    report['retained_document'] = remote
                    report['failure_windows'] = c.command('inspect')
            except Exception as cleanup_error:
                report['inspection_error'] = str(cleanup_error)
        (folder / 'observation.json').write_text(json.dumps(report, indent=2) + '\n')
        print(folder / 'observation.json', flush=True)


if __name__ == '__main__':
    main()
