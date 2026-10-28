#!/usr/bin/env python3
"""Measure popup-edit store values with a synthetic dialog in original MPMB add-ons."""
import argparse,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import canonical_fields,script_hashes
TITLE='Popup Edit Semantics Probe'
ADDON=r'''var iFileName='Popup edit semantics probe.js';
(function(d){var rows=[];var def={description:{name:'Popup Edit Semantics Probe',elements:[
 {type:'edit_text',item_id:'ed01',PopupEdit:true,char_width:20,height:22},
 {type:'edit_text',item_id:'ed02',PopupEdit:true,SpinEdit:true,char_width:20,height:22},
 {type:'edit_text',item_id:'ed03',PopupEdit:true,SpinEdit:true,char_width:20,height:22},{type:'popup',item_id:'po01'},
 {type:'list_box',item_id:'li01'},{type:'edit_text',item_id:'tx01'},{type:'ok',ok_name:'Record'}]},
 initialize:function(dialog){dialog.load({ed01:{Alpha:-1,Beta:2},ed02:{Alpha:-1,Beta:2},ed03:'Beta',po01:{Alpha:-1,Beta:2},li01:{Alpha:-1,Beta:2},tx01:'typed text'});rows.push({stage:'initial',values:dialog.store()});},
 commit:function(dialog){rows.push({stage:'committed',values:dialog.store()});}};
 app.execDialog(def);rows.push({stage:'transport sentinel',value:'\u00a0\u2028\ud83d\ude00'});
 Value('PC Name',JSON.stringify(rows).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);'''


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native-only',action='store_true');parser.add_argument('--readiness',type=Path);args=parser.parse_args()
    if not args.native_only:
        assert args.readiness
        r=json.loads(args.readiness.read_text());assert r['passed'] and len(r['cases'])==24
    folder=ROOT/'output/testing'/('popup-edit-'+str(time.time_ns()));folder.mkdir();binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
    source=next((ROOT/'Testing').glob('*_2024_*.pdf'));report={'passed':False,'scope':__doc__,'readiness':str(args.readiness),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'addon_sha256':hashlib.sha256(ADDON.encode()).hexdigest()};print(folder,flush=True)
    try:
        spec={'dialogs':[{'title':'SOURCE SELECTION DIALOG','result':'ok'},{'title':TITLE,'result':'ok'}],'alerts':[1]*30,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':"getField('User Script').value="+json.dumps(ADDON)},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'advance','ms':1000},{'op':'eval','code':"if(/[^\\x00-\\x7f]/.test(What('PC Name')))throw Error('Non-ASCII diagnostic');JSON.parse(What('PC Name'))"}]}
        scenario,evidence=folder/'scenario.json',folder/'native.json';scenario.write_text(json.dumps(spec))
        with (folder/'native.log').open('w') as log:proc=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=240)
        data=json.loads(evidence.read_text());assert proc.returncode==0 and data['passed'],data.get('error');report['native']=data['stages'][-1]['result'];assert [ord(ch) for ch in report['native'][-1]['value']]==[160,8232,128512]
        if not args.native_only:
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()],'No pre-existing reference document allowed'
                path=c.remote_path('runs/popup-edit-'+str(time.time_ns())+'.pdf');c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/blank-2024.pdf'))+' '+c.literal(path)+' -Force;(Get-Item '+c.literal(path)+').IsReadOnly=$false')
                c.script('set',path=path,values={'User Script':ADDON});ident=c.script_submit('call',path=path,name='RunUserScript',args=[False]);report['request']=ident
                deadline=time.monotonic()+30;dialogs=[]
                while time.monotonic()<deadline:
                    elements=c.command('inspect');dialogs=[e for e in elements if e.get('name')==TITLE]
                    if dialogs:break
                    time.sleep(.1)
                assert len(dialogs)==1,'Expected the exact synthetic popup-edit dialog'
                owner=dialogs[0]['handle'];buttons=[e for e in elements if e.get('owner')==owner and e.get('name')=='Record'];assert len(buttons)==1,buttons
                c.command('invoke',name='Record',owner=owner);completed=c.script_result(ident);assert completed.get('value') is True,completed
                summary=c.script('field_summary',path=path,fields=['PC Name'])['fields']['PC Name'];c.script('set',path=path,values={'User Script':''})
                output=path[:-4]+'-saved.pdf';c.script('save',path=path,output=output);c.script('close',path=output);local=c.fetch(output,folder/'reader.pdf');assert script_hashes(local)==script_hashes(source)
                text=canonical_fields(PdfReader(local))['PC Name']['/V'];assert text.isascii();a,b=1,0
                for ch in text:a=(a+ord(ch))%65521;b=(b+a)%65521
                assert summary=={'code_units':len(text),'adler32_utf16':str((b*65536+a)&0xffffffff)},summary
                report['reader']=json.loads(text);report['reader_summary']=summary;report['reader_saved']=str(local)
                assert [ord(ch) for ch in report['reader'][-1]['value']]==[160,8232,128512]
            report['equal']=report['reader']==report['native'];report['passed']=report['equal']
        else:report['passed']=None
    except Exception as error:report['error']=str(error);raise
    finally:(folder/'popup-edit.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'popup-edit.json',flush=True)
    return 0 if args.native_only or report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
