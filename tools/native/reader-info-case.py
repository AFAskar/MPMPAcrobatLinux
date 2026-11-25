#!/usr/bin/env python3
"""Read actual Reader Doc.info key/case behavior; no metadata mutations.

Only the disposable diagnostic carrier field is changed. Original scripts,
ASCII transport, Unicode sentinel and Reader shutdown are independently checked.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py')
style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
OBSERVER=r"""var iFileName='Document metadata case observer.js';(function(d){var info=d.info,r={keys:Object.keys(info),values:{},sentinel:'\u00a0\u2028\ud83d\ude00'};['Title','Author','Subject','Keywords','Creator','Producer','CreationDate','ModDate','Trapped','SheetVersion','SheetVersionType','SheetVersionBuild','SheetType'].forEach(function(k){[k,k.toLowerCase(),k.toUpperCase()].forEach(function(n){try{var value=info[n];r.values[n]=value===undefined?{undefined_value:true}:{type:typeof value,text:String(value),epoch_millis:Object.prototype.toString.call(value)==='[object Date]'?value.getTime():null}}catch(e){r.values[n]={getter_error:String(e)}}})});Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readiness',type=Path,required=True)
    args=parser.parse_args();ready=json.loads(args.readiness.read_text())
    assert ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
    source=next((ROOT/'Testing').glob('*_2024_*.pdf'))
    folder=ROOT/'output/testing'/('reader-info-case-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    report={'passed':False,'scope':__doc__,'readiness':str(args.readiness.resolve())}
    remote=c.remote_path('runs/info-case-'+str(time.time_ns())+'.pdf');opened=False;pending=None
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP+[str(source),c.SCP_TARGET + ':MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True)
            report['reader_path']=remote;opened=True;c.ensure_document(remote)
            c.script('set',path=remote,values={'User Script':OBSERVER})
            pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);report['request']=pending
            c.script_result(pending,timeout=90);pending=None
            summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['summary']=summary
            c.script('set',path=remote,values={'User Script':''})
            saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved
            report['close']=c.script('close',path=remote);opened=False
            local=c.fetch(remote,folder/'reader.pdf');report['captured']=style.saved_capture(local,summary,source)
            report['passed']=True
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    if pending:report['original_completion']=c.script_result(pending,timeout=45)
                    retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained)
                    report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
            except Exception as error:report['cleanup_error']=str(error)
        (folder/'info-case.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'info-case.json',flush=True)


if __name__=='__main__':main()
