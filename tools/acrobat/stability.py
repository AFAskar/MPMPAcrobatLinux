#!/usr/bin/env python3
"""Repeat verified keyboard/save/reopen cases with different Reader layouts."""
import json
import time
from pathlib import Path
import control as c
import resources
from verify import inspect

def main(report):
    baseline=json.loads(Path(report).read_text())
    assert baseline['passed'] and len(baseline['cases'])==24,'A completed readiness baseline is required'
    suite_started=time.time();oom_start=resources.host()['oom_kills'];run_id=str(int(suite_started));cases=[];output=c.STATE/('stability-'+run_id+'.json')
    with c.desktop_lock():
        c.script('ping')
        for rule in ['2014','2024']:
            source=c.remote_path('runs/blank-'+rule+'-'+baseline['run_id']+'-roundtrip.pdf')
            for index,score in enumerate([18,14,20],1):
                started=time.monotonic();ident='stability-'+rule+'-'+run_id+'-'+str(index)
                path=c.remote_path('runs/'+ident+'.pdf');saved=c.remote_path('runs/'+ident+'-saved.pdf');reopened=c.remote_path('runs/'+ident+'-reopened.pdf')
                try:
                    c.powershell('Copy-Item '+c.literal(source)+' '+c.literal(path)+' -Force;(Get-Item '+c.literal(path)+').IsReadOnly=$false')
                    c.ensure_document(path)
                    c.command('keys',keys=['^0','^1','^2'][index-1])
                    if index==2:c.command('keys',keys='{F4}')
                    expected={'PC Name':'MPMB-'+rule+'-'+str(index)+'-4827','Str':str(score),'Str Mod':str((score-10)//2)}
                    if index==3:expected['PC Name']='MPMB-'+rule+'-é•-4827'
                    for field,value in [('PC Name',expected['PC Name']),('Str',str(score))]:
                        c.script('focus',path=path,field=field);c.command('paste',value=value)
                    actual=c.script('read',path=path,fields=list(expected));assert actual['fields']==expected,actual
                    c.script('save',path=path,output=saved);c.script('close',path=saved)
                    c.powershell('Copy-Item '+c.literal(saved)+' '+c.literal(reopened)+' -Force;if((Get-FileHash '+c.literal(saved)+').Hash -ne (Get-FileHash '+c.literal(reopened)+").Hash){throw 'Reopen snapshot differs'}")
                    actual=c.script('read',path=reopened,fields=list(expected));assert actual['fields']==expected,actual
                    local=c.fetch(saved,c.STATE/(ident+'.pdf'));verified=inspect(local,expected);assert verified['passed'],verified
                    c.script('close',path=reopened)
                    case=dict(id=ident,passed=True,pdf=verified)
                except Exception as error:case=dict(id=ident,passed=False,error=str(error))
                case['seconds']=round(time.monotonic()-started,3);cases.append(case)
                result=dict(status='running' if case['passed'] else 'failed',passed=False,cases=cases,timing='Includes input, calculations, save, reopen, download and independent PDF verification')
                output.write_text(json.dumps(result,indent=2));print(ident,'PASS' if case['passed'] else 'FAIL',flush=True)
                if not case['passed']:raise RuntimeError('Stability failed; evidence: '+str(output))
    try:result['resources']=resources.audit(suite_started,oom_start)
    except Exception as error:
        result.update(status='failed',passed=False,error=str(error));output.write_text(json.dumps(result,indent=2));raise
    result.update(status='complete',passed=True);output.write_text(json.dumps(result,indent=2));print(output)
if __name__=='__main__':
    import sys
    main(sys.argv[1])
