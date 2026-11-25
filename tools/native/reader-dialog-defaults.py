#!/usr/bin/env python3
"""Measure Reader dialog defaults before initialize/load and at actual OK commit.

Isolated host API diagnostic, not an original MPMB progression workflow pass.
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
from spells import wait_dialog
spec = importlib.util.spec_from_file_location('style', ROOT / 'tools/native/default-style-persistence.py')
style = importlib.util.module_from_spec(spec)
spec.loader.exec_module(style)
TITLE = 'DIALOG DEFAULTS QUALIFICATION'
OBSERVER = r"""var iFileName='Dialog default observer.js';(function(d){var r={sentinel:'\u00a0\u2028\ud83d\ude00'};var def={description:{name:'DIALOG DEFAULTS QUALIFICATION',elements:[{type:'edit_text',item_id:'text',name:'7'},{type:'edit_text',item_id:'spin',name:'0',SpinEdit:true},{type:'edit_text',item_id:'read',name:'9',readonly:true},{type:'edit_text',item_id:'empt'},{type:'edit_text',item_id:'spn7',name:'7',SpinEdit:true},{type:'edit_text',item_id:'spno',SpinEdit:true},{type:'edit_text',item_id:'spnr',name:'9',SpinEdit:true,readonly:true},{type:'button',item_id:'butn',name:'Unused button'},{type:'static_text',item_id:'stat',name:'Label'},{type:'check_box',item_id:'chek',name:'Check'},{type:'radio',item_id:'radi',name:'Radio',group_id:'opts'},{type:'ok'}]},initialize:function(dialog){r.before=dialog.store();dialog.load({text:'11'});r.loaded=dialog.store()},commit:function(dialog){r.committed=dialog.store()}};r.result=app.execDialog(def);Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}))})(tDoc);"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--readiness', type=Path, required=True)
    a = p.parse_args()
    ready = json.loads(a.readiness.read_text())
    assert ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = a.input.resolve()
    folder = ROOT / 'output/testing' / ('reader-dialog-defaults-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    remote = c.remote_path('runs/dialog-defaults-' + str(time.time_ns()) + '.pdf')
    report = {'passed': False, 'scope': __doc__, 'input': str(source), 'readiness': str(a.readiness), 'observer_sha256': hashlib.sha256(OBSERVER.encode()).hexdigest()}
    opened = False
    pending = None
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()]
            subprocess.run(c.SCP + [str(source), c.SCP_TARGET + ':MPMB-Testing/runs/' + remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            c.script('set', path=remote, values={'User Script': OBSERVER})
            pending = c.script_submit('call', path=remote, name='RunUserScript', args=[False])
            dialog, elements = wait_dialog(TITLE, time.monotonic() + 60)
            report['controls'] = elements
            assert any(e.get('owner') == dialog['handle'] and e.get('class') == 'Button' and e.get('name') == 'OK' for e in elements)
            report['ok'] = c.command('invoke', name='OK', owner=dialog['handle'])
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
            report['summary'] = summary
            assert report['state']['result'] == 'ok'
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    elements = c.command('inspect')
                    dialogs = [e for e in elements if e.get('class') == '#32770' and e.get('name') == TITLE]
                    if len(dialogs) == 1:
                        c.command('invoke', name='OK', owner=dialogs[0]['handle'])
                    if pending:
                        report['cleanup_result'] = c.script_result(pending, timeout=30)
                    retained = remote.replace('.pdf', '-failed-retained.pdf')
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = c.script('close', path=retained)
                    c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'defaults.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
