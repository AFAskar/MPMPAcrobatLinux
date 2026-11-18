#!/usr/bin/env python3
"""Real2024 Shadow Monk resources versus22 native checkpoints and cold persistence.

Original application-menu class/rest calls and verified actual counter typing.
Disclosed startup observer, positive live console, retained timer invocations,
ASCII Unicode/checksum transport and independent saved fields/AP/scripts.
Body and Mind remains pending; explicit score application, spells, initiative/healing, feats/ASI legality and actual class-dropdown qualification remain open.
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
    parser.add_argument('--instrumentation', type=Path, help='Relocation of the disclosed input manifest')
    args = parser.parse_args()
    native = json.loads(args.native.read_text())
    assert native['passed'] and len(native['phases']) == 22
    wanted = {p['label']: p['state'] for p in native['phases']}
    assert len(wanted) == 22
    manifest = json.loads((args.instrumentation or Path(native['instrumentation'])).read_text())
    assert manifest['passed'] and manifest['mode'] == 'startup-script-timer'
    source = args.input or Path(native['input'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == native['input_sha256']
    assert manifest['observer_sha256'] == hashlib.sha256((ROOT/'tools/native/monk-2024-resource-observer.js').read_bytes()).hexdigest()
    assert manifest['diagnostic_helper_sha256'] == hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()
    ready = json.loads(args.readiness.read_text())
    reference = require_2024_reference(ready, c.harness_fingerprint())
    typing = module('monk_typing', 'reader-ascii-input.py')
    console = module('monk_console', 'reader-console.py')
    style = module('monk_style', 'default-style-persistence.py')
    fields = module('monk_fields', 'field-state-comparison.py')
    folder = ROOT/'output/testing'/('reader-monk-2024-resources-'+str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/monk-2024-resources-'+str(time.time_ns()))
    remote = base+'.pdf'
    opened = False
    report = {'passed': False, 'scope': __doc__, 'native': str(args.native.resolve()),
              'readiness': str(args.readiness.resolve()), 'reference': reference,
              'input': str(source), 'input_sha256': native['input_sha256'],
              'phases': [], 'observations': [], 'inputs': [], 'console_checks': [],
              'comparison_scope':'All captured data exact except weaponTrace: complete raw traces retained, balanced original Validate/positive weapon edit required; no per-keystroke or automatic reentry sequence equality claimed.',
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'typing_sha256': hashlib.sha256(Path(typing.__file__).read_bytes()).hexdigest(),
              'console_sha256': hashlib.sha256(Path(console.__file__).read_bytes()).hexdigest()}

    def persist():
        (folder/'progress.json').write_text(json.dumps(report, indent=2)+'\n')

    def installed():
        end = time.monotonic()+40
        while True:
            marker = c.script('read', path=remote, fields=['User Script'])['fields']['User Script']
            if marker == '// MPMB workflow observer installed':
                return
            assert time.monotonic() < end, ('Observer installation', marker)

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
        assert observed['live']['text'].rstrip('\r\n') == 'MPMB 2024 Monk resource workflow console sentinel'

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
        assert not observed['errors'] and not observed['weaponTraceOverflow']
        trace = observed['weaponTrace']
        assert all(t['original_sha256'] == manifest['field_action_wrapper']['original_sha256'] for t in trace)
        assert sum(t['phase']=='before' for t in trace) == sum(t['phase']=='after' for t in trace)
        if label == 'weapon-edited3':
            assert any(t.get('field')=='Attack.1.Weapon Selection' and t.get('value')=='Unarmed strike' and t['phase']=='before' for t in trace)
            assert any(t.get('field')=='Attack.1.Weapon Selection' and t['phase']=='after' for t in trace)
        comparable = lambda state: {k:v for k,v in state.items() if k != 'weaponTrace'}
        assert comparable(observed) == comparable(wanted[label]), (label, observed, wanted[label])
        expected = dict(observed['fields'], **observed['resources'])
        canonical = fields.compare(pdf, expected)
        visible = inspect(pdf, dict(observed['fields'], **observed['resources']))
        assert visible['passed'] and script_hashes(pdf) == script_hashes(source)
        for row in observed['rows']:
            name = 'Limited Feature Used '+row['row']
            widgets = [w for w in visible['widgets'] if w['name'] == name and w['visible'] and w['page'] is not None]
            assert widgets and all((w['appearance_text'] or '').strip() == row['used'] for w in widgets)
        point = {'label': label, 'pdf': str(pdf), 'state': observed, 'timer': timer,
                 'canonical': canonical, 'visible': visible, 'console_qualified': False}
        report['observations'].append(point)
        persist()
        check_console()
        point['console_qualified'] = True
        report['phases'].append(point)
        persist()

    def level(n):
        reply = c.script('call', path=remote, name='ApplyClasses', args=['Monk (Warrior of Shadow) '+str(n), False])
        report['inputs'].append({'class_level': n, 'reply': reply})

    def spend(name, value):
        names = [key for key in wanted['spent17']['resources'] if __import__('re').fullmatch(r'Limited Feature \d+', key)]
        labels = c.script('read', path=remote, fields=names)['fields']
        matches = [key for key,value in labels.items() if value.startswith(name)]
        assert len(matches) == 1
        field = 'Limited Feature Used '+matches[0].rsplit(' ', 1)[1]
        report['inputs'].append({'resource':name,'observed_resource_labels':labels,**typing.commit(c,remote,field,value)})

    def rest(kind):
        report['inputs'].append({'rest': kind, 'reply': c.script(
            'call', path=remote, name='resetLimFeaUsed', args=[kind])})

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
            subprocess.run(c.SCP+[str(source), 'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+
                                  remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            installed()
            report['inputs'].append({'weapon_edit':typing.commit(c,remote,'Attack.1.Weapon Selection','Unarmed strike')})
            capture('weapon-edited3')
            for n in [1,2,3,5,10,11,15,17,20,1,9]:
                level(n)
                capture('level'+str(n)+'-'+str(len(report['phases'])))
            spend('Focus Points','7'); spend('Uncanny Metabolism','1'); capture('spent9')
            rest('short rest'); capture('short9')
            rest('long rest'); capture('long9')
            level(17); spend('Focus Points','13'); spend('Uncanny Metabolism','1'); capture('spent17')
            snapshot('spent17')
            capture('cold-spent17')
            rest('short rest'); capture('cold-short17')
            rest('long rest'); capture('cold-long17')
            level(1); capture('removed1')
            level(17); capture('restored17')
            snapshot('restored17')
            capture('final-cold17')
            c.script('set', path=remote, values={'User Script': '', 'PC Name': '2024 Monk resource workflow'})
            saved = base+'-final.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['final_close'] = closing.close_saved(c, remote)
            opened = False
            report['pdf'] = str(c.fetch(remote, folder/'reader-final.pdf'))
            assert len(report['phases']) == 22 and len(report['console_checks']) == 22
            assert [p['timer']['invocation_count'] for p in report['phases']] == list(range(1, 17))+list(range(1, 6))+[1]
            assert all(report[k]['process_terminated'] for k in ['spent17_close', 'restored17_close', 'final_close'])
            assert c.harness_fingerprint() == ready['harness_sha256']
            assert hashlib.sha256(source.read_bytes()).hexdigest() == native['input_sha256']
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
        (folder/'resources.json').write_text(json.dumps(report, indent=2)+'\n')
        print(folder/'resources.json', flush=True)


if __name__ == '__main__':
    main()
