#!/usr/bin/env python3
"""Qualify original 2024 Monk Body and Mind Apply/removal against native six-state evidence.

Actual offered Apply, matched RunUserScript entry points, derived fields,
complete CurrentStats, retained timer/Unicode transport and cold saves.
Not full Monk, legal ASI progression or every ability-score case.
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
sys.path.insert(0, str(ROOT/'tools/acrobat'))
import control as c
import fighter_additional_diagnostics as diagnostics
import reader_document_controls as closing
from reference_2024_qualification import require_2024_reference
from verify import inspect, script_hashes


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools/native'/file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--readiness', type=Path, required=True)
    parser.add_argument('--input', type=Path, help='Byte-identical relocation of the native input; SHA remains strict')
    parser.add_argument('--observer', type=Path, required=True)
    parser.add_argument('--transition-from-reader-report', type=Path, help='One original class1-to20 transition from a completed six-state Reader final; compare the full pending state against the supplied native report')
    args = parser.parse_args()
    native = json.loads(args.native.read_text())
    assert native['passed'] and len(native['phases']) == 6
    wanted = {p['label']: p['state'] for p in native['phases']}
    assert len(wanted) == 6
    prior = None
    if args.transition_from_reader_report:
        prior = json.loads(args.transition_from_reader_report.read_text())
        assert prior['passed'] and len(prior['phases']) == 6 and prior['final_close']['process_terminated']
        assert not args.input, 'Transition input comes from the completed Reader report'
        source = Path(prior['pdf'])
        assert inspect(source, prior['phases'][-1]['state']['fields'])['passed']
        assert script_hashes(source) == script_hashes(Path(native['input']))
    else:
        source = args.input or Path(native['input'])
        assert hashlib.sha256(source.read_bytes()).hexdigest() == native['input_sha256']
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    observer = args.observer.read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == native['observer_sha256']
    ready = json.loads(args.readiness.read_text())
    reference = require_2024_reference(ready, c.harness_fingerprint())
    typing = module('monk_typing', 'reader-ascii-input.py')
    console = module('monk_console', 'reader-console.py')
    style = module('monk_style', 'default-style-persistence.py')
    fields = module('monk_fields', 'field-state-comparison.py')
    folder = ROOT/'output/testing'/('reader-monk-bodymind-'+str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/monk-bodymind-'+str(time.time_ns()))
    remote = base+'.pdf'
    opened = False
    report = {'passed': False, 'scope': __doc__, 'native': str(args.native.resolve()),
              'readiness': str(args.readiness.resolve()), 'reference': reference,
              'input': str(source), 'input_sha256': source_hash,
              'transition_from_reader_report': str(args.transition_from_reader_report) if prior else None,
              'phases': [], 'observations': [], 'inputs': [], 'console_checks': [],
              'comparison_scope':'Complete captured fields, CurrentStats, flags, errors and installed script keys equal as parsed JSON; object member order ignored, arrays/property values retained exactly' ,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'typing_sha256': hashlib.sha256(Path(typing.__file__).read_bytes()).hexdigest(),
              'console_sha256': hashlib.sha256(Path(console.__file__).read_bytes()).hexdigest()}

    def persist():
        (folder/'progress.json').write_text(json.dumps(report, indent=2)+'\n')

    def installed():
        c.script('set', path=remote, values={'User Script': observer})
        report['inputs'].append({'observer_install': c.script('call', path=remote, name='RunUserScript', args=[False])})
        c.ensure_document(remote)

    def check_console(request=True):
        if request:
            c.script('set', path=remote, values={'User Script': '// MPMB workflow console request'})

        end = time.monotonic()+30
        while True:
            rows = c.command('inspect')
            roots = [r for r in rows if r['class'] == '#32770' and r['name'] == 'JavaScript Debugger']
            if roots:
                break
            assert time.monotonic() < end, rows
        assert len(roots) == 1
        owner = roots[0]['handle']
        edits = [r for r in rows if r['owner'] == owner and r['class'] == 'RICHEDIT50W']
        assert len(edits) == 1
        observed = console.read_console_text(owner, edits[0]['handle'])
        report['console_checks'].append(observed)
        observed['close'] = console.close_console(observed)
        assert observed['live']['text'].rstrip('\r\n') == 'MPMB 2024 Monk Body and Mind workflow sentinel'

    def capture(label):
        nonlocal remote
        timer = diagnostics.reader_request(c, remote)
        summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
        c.script('set', path=remote, values={'User Script': ''})
        output = base+'-'+label+'-diagnostic.pdf'
        c.script('save', path=remote, output=output)
        remote = output
        pdf = c.fetch(remote, folder/(label+'-diagnostic.pdf'))
        observed = style.saved_capture(pdf, summary, source)
        assert not observed['errors']
        assert observed == wanted[label], (label, observed, wanted[label])
        canonical = fields.compare(pdf, observed['fields'])
        visible = inspect(pdf, observed['fields'])
        assert visible['passed'] and script_hashes(pdf) == script_hashes(source)
        point = {'label': label, 'pdf': str(pdf), 'state': observed, 'timer': timer,
                 'canonical': canonical, 'visible': visible, 'console_qualified': False}
        report['observations'].append(point)
        persist()
        if timer['invocation_count'] == 1:
            check_console()
        point['console_qualified'] = True
        report['phases'].append(point)
        persist()

    def level(n):
        reply = c.script('call', path=remote, name='ApplyClasses', args=['Monk (Warrior of Shadow) '+str(n), False])
        report['inputs'].append({'class_level': n, 'reply': reply})

    def apply_scores():
        c.script('set', path=remote, values={'User Script': 'AbilityScores_Button();'})
        pending = c.script_submit('call', path=remote, name='RunUserScript', args=[False])
        end = time.monotonic()+60
        while True:
            rows = c.command('inspect')
            dialogs = [r for r in rows if r['class'] == '#32770' and r['name'] == 'ABILITY SCORES DIALOG']
            if dialogs:
                break
            assert time.monotonic() < end, rows
        assert len(dialogs) == 1
        owner = dialogs[0]['handle']
        assert any(r.get('owner') == owner and r['class'] == 'Button' and r['name'] == 'Apply' for r in rows)
        invoked = c.command('invoke', name='Apply', owner=owner)
        completed = c.script_result(pending, timeout=120)
        report['inputs'].append({'ability_dialog': rows, 'apply': invoked, 'completion': completed})
        c.ensure_document(remote)

    def snapshot(label):
        nonlocal remote, opened
        c.script('set', path=remote, values={'User Script': '', 'PC Name': '2024 Monk resource workflow'})
        saved = base+'-'+label+'.pdf'
        c.script('save', path=remote, output=saved)
        remote = saved
        report[label+'_close'] = closing.close_saved(c, remote)
        opened = False
        report[label+'_pdf'] = str(c.fetch(remote, folder/('reader-'+label+'.pdf')))
        remote, report[label+'_snapshot'] = closing.reopen_snapshot(c, remote)
        opened = True
        c.ensure_document(remote)
        installed()

    try:
        with c.desktop_lock():
            assert not [r for r in c.command('inspect') if r['class'] == 'AcrobatSDIWindow'
                        and '.pdf' in r['name'].lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP+[str(source), c.SCP_TARGET + ':MPMB-Testing/runs/'+
                                  remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            installed()
            if prior:
                level(20)
            capture('pending20')
            if not prior:
                apply_scores()
                capture('applied20')
                snapshot('applied20')
                capture('cold20')
                level(1)
                capture('removed-before-score-apply1')
                apply_scores()
                capture('removed-applied1')
                snapshot('removed1')
                capture('final-cold1')
            c.script('set', path=remote, values={'User Script': '', 'PC Name': '2024 Monk resource workflow'})
            saved = base+'-final.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['final_close'] = closing.close_saved(c, remote)
            opened = False
            report['pdf'] = str(c.fetch(remote, folder/'reader-final.pdf'))
            assert len(report['phases']) == (1 if prior else 6) and len(report['console_checks']) == (1 if prior else 3)
            assert [p['timer']['invocation_count'] for p in report['phases']] == ([1] if prior else [1,2,1,2,3,1])
            assert all(report[k]['process_terminated'] for k in (['final_close'] if prior else ['applied20_close', 'removed1_close', 'final_close']))
            assert c.harness_fingerprint() == ready['harness_sha256']
            assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        if hasattr(error, 'read_attempts'):
            report['console_read_attempts'] = error.read_attempts
        if hasattr(error, 'observation_attempts'):
            report['focus_observation_attempts'] = error.observation_attempts
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    rows = c.command('inspect')
                    if any(r['name'] == 'JavaScript Debugger' for r in rows):
                        try:
                            check_console(request=False)
                        except Exception as error:
                            report['cleanup_console_error'] = str(error)
                    if any(r['class'] == '#32768' for r in c.command('inspect')):
                        c.command('keys', keys='{ESC}')
                    retained = base+'-failed-retained.pdf'
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = closing.close_saved(c, retained)
                    c.fetch(retained, folder/'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        (folder/'bodymind.json').write_text(json.dumps(report, indent=2)+'\n')
        print(folder/'bodymind.json', flush=True)


if __name__ == '__main__':
    main()
