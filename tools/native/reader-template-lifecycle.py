#!/usr/bin/env python3
"""2024 shared ASfront origin/deletion and edited-note cold persistence control.

Requires a disposable native hide/reveal output with one /ASfront origin.
Programmatic note assignment is explicit; this is not keyboard-event qualification.
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
sys.path[:0] = [str(ROOT/'tools/acrobat'), str(ROOT/'tools/native')]
import control as c
import reader_document_controls as closing
from reference_2024_qualification import require_2024_reference
from verify import canonical_fields, inspect, script_hashes
from pypdf import PdfReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--readiness', type=Path, required=True)
    parser.add_argument('--startup-observer-sha256', help='Explicit disclosed diagnostic-input script hash, if present')
    args = parser.parse_args()
    source = args.input.resolve()
    ready = json.loads(args.readiness.read_text())
    reference = require_2024_reference(ready, c.harness_fingerprint())
    fixture = next((ROOT/'Testing').glob('*_2024_*.pdf'))
    original_scripts = script_hashes(fixture)
    supplied_scripts = script_hashes(source)
    assert all(supplied_scripts.get(k) == v for k, v in original_scripts.items())
    extras = {k:v for k,v in supplied_scripts.items() if k not in original_scripts}
    expected_extras = ({'zz MPMB diagnostic startup observer': args.startup_observer_sha256}
                       if args.startup_observer_sha256 else {})
    assert extras == expected_extras, extras
    reader = PdfReader(source)
    assert sum(str(p.get('/TemplateInstantiated', '')) == '/ASfront' for p in reader.pages) == 1
    count = len(reader.pages)
    values = canonical_fields(reader)
    note = values['Extra.Notes']['/V']
    assert note and values['Character Level']['/V'] == '3'
    spec = importlib.util.spec_from_file_location('template_console', ROOT/'tools/native/reader-console.py')
    console = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(console)
    folder = ROOT/'output/testing'/('reader-template-lifecycle-'+str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    remote = c.remote_path('runs/template-origin-'+str(time.time_ns())+'.pdf')
    report = {'passed': False, 'scope': __doc__, 'input': str(source),
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'reference': reference, 'states': [], 'console': [],
              'original_script_hashes': original_scripts, 'disclosed_added_scripts': extras}
    opened = False

    def state(label, pages, expected_note):
        result = c.script('read', path=remote, fields=['Extra.Notes', 'Character Level'])
        assert result['pages'] == pages and result['fields'] == {'Extra.Notes': expected_note, 'Character Level': '3'}, result
        assert result['calculation'] == {'app': True, 'doc': True, 'delay': False}, result
        report['states'].append({'label': label, 'result': result})

    def initialized():
        c.ensure_document(remote)
        if extras:
            deadline = time.monotonic()+30
            while True:
                marker = c.script('read', path=remote, fields=['User Script'])['fields']['User Script']
                if marker == '// MPMB workflow observer installed':
                    break
                assert time.monotonic() < deadline, marker
                time.sleep(0.1)

    def check_console(clear=False):
        if clear:
            code = "var iFileName='Template lifecycle console.js';Value('User Script','');console.clear();console.println('Template lifecycle sentinel');"
        else:
            code = "var iFileName='Template lifecycle console.js';Value('User Script','');console.show();"
        c.script('set', path=remote, values={'User Script': code})
        c.script('call', path=remote, name='RunUserScript', args=[False])
        if not clear:
            observed = console.observed_console('Template lifecycle sentinel')
            report['console'].append(observed)
            observed['close'] = console.close_console(observed)

    def saved(label, expected_note):
        nonlocal remote
        output = remote[:-4]+'-'+label+'.pdf'
        c.script('set', path=remote, values={'User Script': ''})
        c.script('save', path=remote, output=output)
        remote = output
        pdf = c.fetch(remote, folder/(label+'.pdf'))
        verified = inspect(pdf, {'Extra.Notes': expected_note, 'Character Level': '3'})
        assert verified['passed'] and script_hashes(pdf) == script_hashes(source), verified
        actual = PdfReader(pdf)
        assert len(actual.pages) == count
        origins = [str(p.get('/TemplateInstantiated', '')) for p in actual.pages]
        assert origins.count('/ASfront') == 1, origins
        report[label] = {'pdf': str(pdf), 'independent': verified, 'origins': origins}

    try:
        with c.desktop_lock():
            assert not [r for r in c.command('inspect') if r['class'] == 'AcrobatSDIWindow' and '.pdf' in r['name'].lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP+[str(source), c.SCP_TARGET + ':MPMB-Testing/runs/'+remote.replace('\\','/').rsplit('/',1)[-1]], check=True, capture_output=True)
            opened = True
            initialized()
            check_console(True)
            state('native-shared-input', count, note)
            for label, pages in [('hidden', count-1), ('revealed', count)]:
                report[label+'_call'] = c.script('call', path=remote, name='DoTemplate', args=['ASfront'])
                c.ensure_document(remote)
                state(label, pages, note)
            check_console()
            edited = note+' Reader changed'
            report['programmatic_note_edit'] = c.script('set', path=remote, values={'Extra.Notes': edited})
            state('changed', count, edited)
            saved('changed-save', edited)
            report['first_close'] = closing.close_saved(c, remote)
            opened = False
            remote, report['snapshot'] = closing.reopen_snapshot(c, remote)
            opened = True
            initialized()
            check_console(True)
            state('cold-changed', count, edited)
            for label, pages in [('cold-hidden', count-1), ('cold-revealed', count)]:
                report[label+'_call'] = c.script('call', path=remote, name='DoTemplate', args=['ASfront'])
                c.ensure_document(remote)
                state(label, pages, edited)
            check_console()
            saved('final', edited)
            report['final_close'] = closing.close_saved(c, remote)
            opened = False
            assert c.harness_fingerprint() == ready['harness_sha256']
            assert hashlib.sha256(source.read_bytes()).hexdigest() == report['input_sha256']
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    retained = remote[:-4]+'-failed-retained.pdf'
                    c.script('save', path=remote, output=retained)
                    remote = retained
                    report['cleanup_close'] = closing.close_saved(c, remote)
                    c.fetch(remote, folder/'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        (folder/'lifecycle.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
