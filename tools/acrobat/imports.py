#!/usr/bin/env python3
"""Exercise original MPMB file import on both rulesets; preserve and verify outputs."""
import json
import ast
import subprocess
import time
import control as c
import resources
from verify import inspect, script_hashes, canonical_fields
from pypdf import PdfReader


def test(rule, run_id):
    path=c.remote_path('runs/file-import-'+rule+'-'+run_id+'.pdf')
    script_path=c.remote_path('runs/file-import-'+rule+'-'+run_id+'.js')
    c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/blank-'+rule+'.pdf'))+' '+c.literal(path)+';(Get-Item '+c.literal(path)+').IsReadOnly=$false')
    subprocess.run(c.SCP+[str(c.REPO/'Testing/addons/readiness-sentinel.js'),c.SCP_TARGET+':MPMB-Testing/runs/file-import-'+rule+'-'+run_id+'.js'],check=True,capture_output=True)
    c.ensure_document(path)
    ident=c.script_submit('call',path=path,name='ImportUserScriptFile',args=[],file_picker=True,import_file=script_path)
    c.command('select_file',request_id=ident,path=script_path)
    result=c.script_result(ident)
    assert result.get('value') is True,result
    executed=c.script('call',path=path,name='RunUserScript',args=[False,False])
    assert executed.get('value') is True,executed
    expected={'Player Name':'MPMB add-on executed','User Script':''}
    value=c.script('read',path=path,fields=list(expected))
    for key,wanted in expected.items():assert value['fields'][key]==wanted,value
    summary=c.script('field_summary',path=path,fields=['User_Imported_Files.Stringified'])['fields']
    bounded_response_checked=False
    if summary['User_Imported_Files.Stringified']['code_units']>12000:
        try:c.script('read',path=path,fields=['User_Imported_Files.Stringified'])
        except RuntimeError as error:
            failure=json.loads(str(error))
            assert failure.get('operation_completed') is True and 'Response exceeds' in failure.get('error',''),failure
            bounded_response_checked=True
        else:raise AssertionError('Oversized reply was not rejected explicitly')
    saved=path[:-4]+'-saved.pdf';reopened=path[:-4]+'-reopened.pdf'
    c.script('save',path=path,output=saved);c.script('close',path=saved)
    c.powershell('Copy-Item '+c.literal(saved)+' '+c.literal(reopened)+";if((Get-FileHash "+c.literal(saved)+').Hash -ne (Get-FileHash '+c.literal(reopened)+").Hash){throw 'Reopen snapshot differs'}")
    again=c.script('read',path=reopened,fields=list(expected))
    assert again['fields']==value['fields'],again
    local=c.fetch(saved,c.STATE/('file-import-'+rule+'-'+run_id+'.pdf'))
    # User Script is nonvisual storage in these fixtures, not a page widget.
    verified=inspect(local,{'Player Name':expected['Player Name']});assert verified['passed'],verified
    fields=canonical_fields(PdfReader(local))
    assert fields['User Script']['/V']=='','Manual script storage was unexpectedly populated'
    payload=str(fields['User_Imported_Files.Stringified']['/V'])
    raw=payload.encode('utf-16-le','surrogatepass');a=1;b=0
    for i in range(0,len(raw),2):a=(a+raw[i]+256*raw[i+1])%65521;b=(b+a)%65521
    assert summary['User_Imported_Files.Stringified']==dict(code_units=len(raw)//2,adler32_utf16=str((b<<16)|a)),'Reader/PDF payload summary differs'
    again_summary=c.script('field_summary',path=reopened,fields=['User_Imported_Files.Stringified'])['fields']
    assert again_summary==summary,'Imported payload changed after reopening'
    scripts=ast.literal_eval(payload)
    assert isinstance(scripts,dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in scripts.items())
    sentinel=[k for k in scripts if k.endswith(' - MPMB readiness sentinel.js')]
    assert len(sentinel)==1 and scripts[sentinel[0]]==(c.REPO/'Testing/addons/readiness-sentinel.js').read_text(),'Imported file content differs'
    original=next((c.REPO/'Testing').glob('*_'+rule+'_*.pdf'))
    original_fields=canonical_fields(PdfReader(original))
    original_scripts=ast.literal_eval(str(original_fields['User_Imported_Files.Stringified']['/V']))
    assert len(scripts)==len(original_scripts)+1 and all(scripts.get(k)==v for k,v in original_scripts.items()),'Existing imports changed'
    assert script_hashes(original)==script_hashes(local),'Document scripts changed'
    c.script('close',path=reopened)
    return dict(import_result=result,execution=executed,reader=again,payload_summary=summary,bounded_response_checked=bounded_response_checked,existing_scripts_preserved=len(original_scripts),pdf=verified)


def main():
    run_id=str(int(time.time()));cases=[];report=c.STATE/('file-import-'+run_id+'.json');started=time.time();oom_start=resources.host()['oom_kills']
    result=dict(run_id=run_id,status='running',passed=False,cases=cases)
    report.write_text(json.dumps(result,indent=2))
    with c.desktop_lock():
        for rule in ['2014','2024']:
            t=time.monotonic()
            try:detail=test(rule,run_id);passed=True
            except Exception as error:detail=dict(error=str(error));passed=False
            cases.append(dict(rule=rule,passed=passed,seconds=round(time.monotonic()-t,3),detail=detail))
            result.update(status='running' if passed else 'failed',elapsed_seconds=round(time.time()-started,3))
            report.write_text(json.dumps(result,indent=2))
            print(rule,'PASS' if passed else 'FAIL',report,flush=True)
            if not passed:return 1
        try:result['resources']=resources.audit(started,oom_start)
        except Exception as error:
            result.update(status='failed',error=str(error));report.write_text(json.dumps(result,indent=2));return 1
        result.update(status='complete',passed=True);report.write_text(json.dumps(result,indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
