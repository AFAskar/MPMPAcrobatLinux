#!/usr/bin/env python3
"""Qualify original2024 Shadow Monk generated spells, progression and changed cold saves.

Actual offered fixed-spell Continue/Generate dialogs, matched observer installation,
complete captured spell data/fields/resources, positive console/timer and saved AP.
Not all Monk spells, subclass choices or whole-character qualification.
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
from verify import inspect, script_hashes, canonical_fields
from pypdf import PdfReader


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
    parser.add_argument('--spent-regeneration', action='store_true', help='Three-state actual resource typing, regeneration and cold preservation against a spent native profile')
    args = parser.parse_args()
    count=3 if args.spent_regeneration else 5
    native = json.loads(args.native.read_text())
    assert native['passed'] and len(native['phases']) == count
    wanted = {p['label']: p['state'] for p in native['phases']}
    assert len(wanted) == count
    source = args.input or Path(native['input'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == native['input_sha256']
    observer = args.observer.read_text()
    assert hashlib.sha256(observer.encode()).hexdigest() == native['observer_sha256']
    ready = json.loads(args.readiness.read_text())
    reference = require_2024_reference(ready, c.harness_fingerprint())
    typing = module('monk_typing', 'reader-ascii-input.py')
    console = module('monk_console', 'reader-console.py')
    style = module('monk_style', 'default-style-persistence.py')
    fields = module('monk_fields', 'field-state-comparison.py')
    folder = ROOT/'output/testing'/('reader-shadow-monk-spells-'+str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    base = c.remote_path('runs/shadow-monk-spells-'+str(time.time_ns()))
    remote = base+'.pdf'
    opened = False
    report = {'passed': False, 'scope': __doc__, 'native': str(args.native.resolve()), 'spent_regeneration':args.spent_regeneration,
              'readiness': str(args.readiness.resolve()), 'reference': reference,
              'input': str(source), 'input_sha256': native['input_sha256'],
              'phases': [], 'observations': [], 'inputs': [], 'console_checks': [],
              'comparison_scope':'All captured data except rawPrefixes equal as parsed JSON; generated fields mapped by actual page prefix to exact suffix keys, raw addresses retained separately; object member order ignored, array order and all property values retained' ,
              'closing_sha256': hashlib.sha256(Path(closing.__file__).read_bytes()).hexdigest(),
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'verifier_sha256':hashlib.sha256((ROOT/'tools/native/verify-generated-fields.py').read_bytes()).hexdigest(),
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
        assert observed['live']['text'].rstrip('\r\n') == 'MPMB 2024 Shadow Monk spells workflow sentinel'

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
        comparable = lambda state: {k:v for k,v in state.items() if k != 'rawPrefixes'}
        assert comparable(observed) == comparable(wanted[label]), (label, observed, wanted[label])
        expected = dict(observed['fields'], **observed['resources'])
        for prefix, page in zip(observed['rawPrefixes'], observed['spellPages']):
            expected.update({prefix+k:v for k,v in page['fields'].items()})
        api=folder/(label+'-expected.json')
        api.write_text(json.dumps(expected))
        verification=folder/(label+'-verification')
        with (folder/(label+'-verification.log')).open('w') as log:
            verified=subprocess.run([sys.executable,str(ROOT/'tools/native/verify-generated-fields.py'),str(pdf),str(api),str(verification)],stdout=log,stderr=log,timeout=600)
        canonical=json.loads((verification/'verification.json').read_text())
        assert verified.returncode==0 and canonical['passed'] and canonical['source_sha256']==report['verifier_sha256'] and script_hashes(pdf)==script_hashes(source)
        point = {'label': label, 'pdf': str(pdf), 'state': observed, 'timer': timer,
                 'verification': canonical, 'console_qualified': False}
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

    def generate():
        c.script('set', path=remote, values={'PC Name':'Shadow Monk spells workflow'})
        pending = c.script_submit('call', path=remote, name='GenerateSpellSheet', args=[])
        evidence = []
        for title, name in [('SPELL SELECTION DIALOG','Continue to Next Dialog >>'),
                            ('SPELL LIST GENERATION DIALOG','Generate the Spell Sheet')]:
            end = time.monotonic()+120
            while True:
                rows = c.command('inspect')
                dialogs = [r for r in rows if r['class']=='#32770' and r['name']==title]
                if dialogs:
                    break
                assert time.monotonic()<end, rows
            assert len(dialogs)==1
            owner=dialogs[0]['handle']
            assert any(r.get('owner')==owner and r['class']=='Button' and r['name']==name for r in rows), rows
            evidence.append({'title':title,'controls':rows,'button':name,'invocation':c.command('invoke', name=name, owner=owner)})
        completed=c.script_result(pending,timeout=240)
        c.ensure_document(remote)
        report['inputs'].append({'generation':evidence,'completion':completed})

    def wisdom(value):
        report['inputs'].append({'wisdom_edit':typing.commit(c,remote,'Wis',str(value))})
        c.ensure_document(remote)

    def spend(label,value):
        import re
        names=[key for key in wanted['spent-before-generation17']['resources'] if re.fullmatch(r'Limited Feature [0-9]+',key)]
        observed=c.script('read',path=remote,fields=names)['fields']
        selected=[key for key,v in observed.items() if v.startswith(label)]
        assert len(selected)==1, observed
        field='Limited Feature Used '+selected[0].rsplit(' ',1)[-1]
        report['inputs'].append({'resource':label,'labels':observed,'typing':typing.commit(c,remote,field,value)})
        c.ensure_document(remote)

    def clean_mirrors(pdf):
        values=canonical_fields(PdfReader(pdf))
        expected={name:'Shadow Monk spells workflow' for name in values if name=='PC Name' or (name.endswith('zAdvLog.PC Name') and 'SSfront.' in name)}
        assert len(expected)==2, expected
        checked=inspect(pdf,expected)
        assert checked['passed'],checked
        report.setdefault('clean_name_mirrors',[]).append(checked)

    def close_saved(path):
        for attempt in range(3):
            try:
                return closing.close_saved(c,path)
            except AssertionError as error:
                # This precise guard occurs before any close input is sent.
                # All other failures, including uncertain post-input failures,
                # propagate without retrying document mutations.
                if str(error) != 'A dialog blocks saved-document closure':
                    raise
                observation=closing.cancel_reading_preparation(c,path)
                report.setdefault('reading_preparation_cancellations',[]).append(observation)
                persist()
        raise AssertionError('Reading preparation repeatedly blocked saved-document closure')

    def snapshot(label):
        nonlocal remote, opened
        c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Shadow Monk spells workflow'})
        saved = base+'-'+label+'.pdf'
        c.script('save', path=remote, output=saved)
        remote = saved
        report[label+'_close'] = close_saved(remote)
        opened = False
        report[label+'_pdf'] = str(c.fetch(remote, folder/('reader-'+label+'.pdf')))
        clean_mirrors(Path(report[label+'_pdf']))
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
            if args.spent_regeneration:
                spend('Focus Points','2')
                spend('Uncanny Metabolism','1')
                capture('spent-before-generation17')
                generate()
                capture('spent-after-generation17')
                snapshot('spent-regenerated17')
                capture('cold-spent-regenerated17')
            else:
                generate()
                capture('generated3')
                level(17)
                generate()
                capture('generated17')
                snapshot('generated17')
                wisdom(16)
                generate()
                capture('cold-wis16-17')
                level(3)
                generate()
                capture('lowered3-wis16')
                snapshot('lowered3-wis16')
                wisdom(18)
                generate()
                capture('final-cold-restored3')
            c.script('set', path=remote, values={'User Script': '', 'PC Name': 'Shadow Monk spells workflow'})
            saved = base+'-final.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['final_close'] = close_saved(remote)
            opened = False
            report['pdf'] = str(c.fetch(remote, folder/'reader-final.pdf'))
            clean_mirrors(Path(report['pdf']))
            assert len(report['phases']) == count and len(report['console_checks']) == (2 if args.spent_regeneration else 3)
            assert [p['timer']['invocation_count'] for p in report['phases']] == ([1,2,1] if args.spent_regeneration else [1,2,1,2,1])
            assert all(report[k]['process_terminated'] for k in (['spent-regenerated17_close','final_close'] if args.spent_regeneration else ['generated17_close', 'lowered3-wis16_close', 'final_close']))
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
                    report['cleanup_close'] = close_saved(retained)
                    c.fetch(retained, folder/'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        (folder/'spells.json').write_text(json.dumps(report, indent=2)+'\n')
        print(folder/'spells.json', flush=True)


if __name__ == '__main__':
    main()
