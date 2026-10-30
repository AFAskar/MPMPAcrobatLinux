#!/usr/bin/env python3
"""Qualify scoped, verified text input through an original Reader class dialog.

Harness transport qualification only. The class is cancelled; this does not
qualify character progression or owner-drawn dropdown pointer gestures.
"""
import argparse
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from pypdf import PdfReader
from verify import canonical_fields, script_hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--preflight',type=Path,required=True);args=parser.parse_args()
    preflight=json.loads(args.preflight.read_text());assert preflight['passed'] and preflight['checks']['native-dialog-controls']
    folder=ROOT/'output/testing'/('reader-dialog-input-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    report={'passed':False,'scope':__doc__,'preflight':str(args.preflight.resolve()),'dropdown_pointer_gestures_qualified':False};remote=c.remote_path('runs/dialog-input-'+str(time.time_ns())+'.pdf');report['reader_path']=remote;ident=None;opened=False
    def checkpoint(stage):
        report['stage']=stage;(folder/'input.json').write_text(json.dumps(report,indent=2)+'\n')
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/blank-2024.pdf'))+' '+c.literal(remote)+' -Force;(Get-Item '+c.literal(remote)+').IsReadOnly=$false')
            opened=True;c.ensure_document(remote);before=c.script('read',path=remote,fields=['Class and Levels'])['fields'];checkpoint('ready')
            ident=c.script_submit('call',path=remote,name='SelectClass',args=[]);report['request']=ident
            deadline=time.monotonic()+45
            while True:
                elements=c.command('inspect');roots=[e for e in elements if e.get('class')=='#32770' and 'CLASS SELECTION' in e.get('name','').upper()]
                if roots:break
                assert time.monotonic()<deadline, 'Class dialog did not appear'
            assert len(roots)==1;owner=roots[0]['handle']
            (folder/'before-native.json').write_text(json.dumps(elements,indent=2)+'\n')
            editable=[e for e in elements if e.get('owner')==owner and e.get('class')=='RICHEDIT50W' and e.get('enabled') and e.get('read_only') is False and e.get('name')=='' and e['rect'][2]>0 and e['rect'][3]>0]
            assert len(editable)==1, 'Expected one visible blank class-name text control'
            target=min(editable,key=lambda e:(e['rect'][1],e['rect'][0]));handle=target['handle'];report['target']=target
            states=[dict(c.command('dialog_control',owner=owner,handle=e['handle']),rect=e['rect']) for e in elements if e.get('owner')==owner and e.get('class')=='ComboBox' and e.get('enabled')]
            choices=[e for e in states if e['item_count']>1];assert choices
            combo=min(choices,key=lambda e:(e['rect'][1],e['rect'][0]));report['combo_before']=combo;checkpoint('dialog-observed')
            main=next(e for e in elements if e.get('class')=='AcrobatSDIWindow')
            try:c.command('focus_control',owner=main['handle'],handle=handle)
            except RuntimeError as error:assert 'owner is not' in str(error);report['wrong_owner_rejected']=True
            else:raise AssertionError('Wrong owner was accepted')
            report['focus']=c.command('focus_control',owner=owner,handle=handle);assert report['focus']['focused']
            report['paste']=c.command('paste',value='Barbarian');assert report['paste']['verified']
            report['text_after']=c.command('dialog_control',owner=owner,handle=handle);assert report['text_after']['text']=='Barbarian'
            report['combo_after']=c.command('dialog_control',owner=owner,handle=combo['handle']);assert report['combo_after']['selected_index']>0 and report['combo_after']['selected_index']!=combo['selected_index'], 'Original text-change callback did not update class recognition'
            checkpoint('original-callback-verified')
            shot=c.command('screenshot');c.fetch(shot['path'],folder/'callback.png')
            elements=c.command('inspect');buttons=[e for e in elements if e.get('owner')==owner and e.get('class')=='Button' and e.get('name','').startswith('Cancel')];assert len(buttons)==1
            c.command('invoke',name=buttons[0]['name'],owner=owner);report['completion']=c.script_result(ident,timeout=90);ident=None
            after=c.script('read',path=remote,fields=['Class and Levels'])['fields'];assert after==before;report['cancel_preserved_class']=True
            saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved;report['close']=c.script('close',path=remote);opened=False;local=c.fetch(remote,folder/'reader.pdf')
            source=next((ROOT/'Testing').glob('*_2024_*.pdf'))
            assert script_hashes(local)==script_hashes(source), 'Original document scripts changed'
            fields=canonical_fields(PdfReader(local))
            assert fields['Class and Levels']['/V']==before['Class and Levels'], 'Saved cancelled class changed'
            report['independent_saved_class_and_scripts']=True;report['passed']=True
    except Exception as error:
        report['error']=str(error)
        try:
            shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
        except Exception as diagnostic_error:report['diagnostic_error']=str(diagnostic_error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    elements=c.command('inspect')
                    numeric=[e for e in elements if e.get('class')=='#32770' and any(x.get('owner')==e.get('handle') and x.get('name')=='Invalid numeric value.' for x in elements)]
                    if numeric:
                        assert len(numeric)==1
                        c.command('invoke',name='OK',owner=numeric[0]['handle'])
                        elements=c.command('inspect')
                    buttons=[e for e in elements if e.get('class')=='Button' and e.get('name','').startswith('Cancel') and any(r.get('handle')==e.get('owner') and 'CLASS SELECTION' in r.get('name','').upper() for r in elements)]
                    if len(buttons)==1:c.command('invoke',name=buttons[0]['name'],owner=buttons[0]['owner'])
                    if ident:report['cleanup_completion']=c.script_result(ident,timeout=90)
                    saved=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=saved);report['cleanup_close']=c.script('close',path=saved);c.fetch(saved,folder/'failed-retained.pdf')
            except Exception as cleanup_error:report['cleanup_error']=str(cleanup_error)
        checkpoint('complete' if report['passed'] else 'failed');print(folder/'input.json',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
