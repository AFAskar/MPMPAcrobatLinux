#!/usr/bin/env python3
"""Measure the popup cancellation return value using a real Reader menu.

This isolated host API control complements the original spell-menu workflow.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
spec = importlib.util.spec_from_file_location('style', ROOT / 'tools/native/default-style-persistence.py')
style = importlib.util.module_from_spec(spec)
spec.loader.exec_module(style)
LABEL = 'Popup cancellation qualification'
OBSERVER = r"""var iFileName='Popup cancellation observer.js';(function(d){var v=app.popUpMenuEx({cName:'Popup cancellation qualification',cReturn:'unexpected-selection'});var r={kind:typeof v,value:v,sentinel:'\u00a0\u2028\ud83d\ude00'};Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}))})(tDoc);"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--readiness', type=Path, required=True)
    a = p.parse_args()
    ready = json.loads(a.readiness.read_text())
    assert ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = a.input.resolve()
    folder = ROOT / 'output/testing' / ('reader-popup-cancel-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    remote = c.remote_path('runs/popup-cancel-' + str(time.time_ns()) + '.pdf')
    report = {'passed': False, 'scope': __doc__, 'input': str(source), 'readiness': str(a.readiness)}
    opened = False
    pending = None
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()]
            subprocess.run(c.SCP + [str(source), 'mpmb-test@127.0.0.1:MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            c.script('set', path=remote, values={'User Script': OBSERVER})
            pending = c.script_submit('call', path=remote, name='RunUserScript', args=[False])
            deadline = time.monotonic() + 20
            while True:
                menu = c.command('inspect_focused')
                if menu.get('class') == '#32768' and any(e.get('name') == LABEL for e in menu.get('children', [])):
                    break
                assert time.monotonic() < deadline, 'Actual offered cancellation menu missing'
            report['menu'] = menu
            report['cancel'] = c.command('keys', keys='{ESC}')
            report['completion'] = c.script_result(pending, timeout=120)
            pending = None
            summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
            c.script('set', path=remote, values={'User Script': ''})
            saved = remote.replace('.pdf', '-saved.pdf')
            c.script('save', path=remote, output=saved)
            remote = saved
            report['close'] = c.script('close', path=remote)
            opened = False
            local = c.fetch(remote, folder / 'reader.pdf')
            report['state'] = style.saved_capture(local, summary, source)
            assert report['state'] == {'kind': 'object', 'value': None}
            report['summary'] = summary
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    state = c.command('inspect_focused')
                    if state.get('class') == '#32768':
                        c.command('keys', keys='{ESC}')
                    if pending:
                        report['cleanup_result'] = c.script_result(pending, timeout=30)
                    retained = remote.replace('.pdf', '-failed-retained.pdf')
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = c.script('close', path=retained)
                    c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'cancellation.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
