#!/usr/bin/env python3
"""Isolated resetForm event observation with synthetic, restored field actions.

This is an API diagnostic, not an original MPMB reset/import workflow pass.
"""
import argparse,importlib.util,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from pypdf import PdfReader
from verify import canonical_fields
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
OBSERVER=r"""var iFileName='Isolated reset event observer.js';(function(d){d.__resetTrace=[];d.__resetPhase='';var f=d.getField('Player Name'),snapshots=[];var log="(function(){var r={phase:tDoc.__resetPhase};['name','type','value','willCommit'].forEach(function(k){try{var v=event[k];r[k]=v===undefined?{undefined_value:true}:v}catch(e){r[k]={getter_error:String(e)}}});tDoc.__resetTrace.push(r)})();";['Keystroke','Validate','Format'].forEach(function(k){f.setAction(k,log)});function snapshot(phase){snapshots.push({phase:phase,value:f.valueAsString,eventCount:d.__resetTrace.length,appCalculate:app.calculate,docCalculate:d.calculate})}d.__resetPhase='assignment';f.value='reset diagnostic';d.calculateNow();snapshot('assigned');d.__resetPhase='changed';d.resetForm(['Player Name']);snapshot('changed');d.__resetPhase='unchanged';d.resetForm(['Player Name']);snapshot('unchanged');d.__resetPhase='setup-app-off';f.value='reset diagnostic';app.calculate=false;d.__resetPhase='app-off';d.resetForm(['Player Name']);snapshot('app-off');app.calculate=true;d.__resetPhase='setup-doc-off';f.value='reset diagnostic';d.calculate=false;d.__resetPhase='doc-off';d.resetForm(['Player Name']);snapshot('doc-off');d.calculate=true;var failures=[];function failure(name,kind,reset){['Keystroke','Validate','Format'].forEach(function(k){f.setAction(k,log)});d.__resetPhase='setup-'+name;f.value='baseline';f.setAction(kind,log+"throw Error('MPMB field exception sentinel');");d.__resetPhase=name;var item={name:name};try{if(reset)d.resetForm(['Player Name']);else f.value='changed';item.threw=false}catch(e){item.threw=true;item.error=String(e)}item.value=f.valueAsString;failures.push(item)}failure('format-assignment','Format',false);failure('format-reset','Format',true);failure('keystroke-assignment','Keystroke',false);failure('keystroke-reset','Keystroke',true);failure('validate-assignment','Validate',false);failure('validate-reset','Validate',true);['Keystroke','Validate','Format'].forEach(function(k){f.setAction(k,'')});f.value='';var r={trace:d.__resetTrace,snapshots:snapshots,failures:failures,sentinel:'\u00a0\u2028\ud83d\ude00'};delete d.__resetTrace;delete d.__resetPhase;Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--readiness',type=Path,required=True);args=p.parse_args()
    ready=json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
    source=next((ROOT/'Testing').glob('*_2024_*.pdf'));reader=PdfReader(source);field=reader.get_object(canonical_fields(reader)['Player Name']['reference'])
    assert not field.get('/AA'), 'Diagnostic requires Player Name with no original field actions'
    folder=ROOT/'output/testing'/('reader-reset-events-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    remote=c.remote_path('runs/reset-events-'+str(time.time_ns())+'.pdf');opened=False;pending=None;report={'passed':False,'scope':__doc__,'readiness':str(args.readiness.resolve()),'reader_path':remote}
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True)
            opened=True;c.ensure_document(remote);c.script('set',path=remote,values={'User Script':OBSERVER})
            pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);report['request']=pending;c.script_result(pending,timeout=90);pending=None
            summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['summary']=summary
            c.script('set',path=remote,values={'User Script':''});saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved
            report['close']=c.script('close',path=remote);opened=False;local=c.fetch(remote,folder/'reader.pdf');report['captured']=style.saved_capture(local,summary,source)
            assert canonical_fields(PdfReader(local))['Player Name']['/V']==''
            assert any(event['phase']=='assignment' for event in report['captured']['trace']), 'Positive assignment event control did not run'
            report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    if pending:report['original_completion']=c.script_result(pending,timeout=45)
                    retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
            except Exception as error:report['cleanup_error']=str(error)
        (folder/'reset-events.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'reset-events.json',flush=True)


if __name__=='__main__':main()
