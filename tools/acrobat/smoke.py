#!/usr/bin/env python3
"""One measured real-Reader roundtrip, with host pressure and guest crash evidence."""
import json
import threading
import time
import control as c
import resources
from verify import inspect, script_hashes


def main():
    started=time.time();run_id=str(int(started));steps=[];samples=[];stop=threading.Event()
    report=c.STATE/('smoke-'+run_id+'.json')
    def sample():
        while not stop.is_set():
            samples.append(dict(epoch=time.time(),**resources.host()));stop.wait(2)
    sampler=threading.Thread(target=sample,daemon=True);sampler.start()
    result=dict(started=started,run_id=run_id,status='running',steps=steps)
    def step(name,fn):
        t=time.monotonic();value=fn();steps.append(dict(name=name,seconds=round(time.monotonic()-t,3),result=value))
        report.write_text(json.dumps(result,indent=2));print(name,'PASS',flush=True);return value
    try:
        with c.desktop_lock():
            result['before']=resources.snapshot(started)
            if result['before']['host']['available_mib']<1024:raise RuntimeError('Less than 1 GiB host RAM available; suite refused')
            path=c.remote_path('runs/smoke-'+run_id+'.pdf');saved=path[:-4]+'-saved.pdf';reopened=path[:-4]+'-reopened.pdf'
            c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/blank-2014.pdf'))+' '+c.literal(path)+';(Get-Item '+c.literal(path)+').IsReadOnly=$false')
            step('ready',lambda:c.ensure_document(path))
            step('focus-name',lambda:c.script('focus',path=path,field='PC Name'))
            step('keyboard-name',lambda:c.command('paste',value='MPMB bridge smoke 4827'))
            step('strength',lambda:c.script('set',path=path,values={'Str':'18'}))
            expected={'PC Name':'MPMB bridge smoke 4827','Str':'18','Str Mod':'4'}
            def read(p):
                value=c.script('read',path=p,fields=list(expected));assert value['fields']==expected,value;return value
            step('read-calculated',lambda:read(path))
            step('save',lambda:c.script('save',path=path,output=saved))
            step('close',lambda:c.script('close',path=saved))
            c.powershell('$p='+c.literal(saved)+";$until=[DateTime]::UtcNow.AddSeconds(20);while($true){try{$h=[IO.File]::Open($p,'Open','Read','None');$h.Dispose();break}catch{if([DateTime]::UtcNow -gt $until){throw};Start-Sleep -Milliseconds 100}};Copy-Item $p "+c.literal(reopened)+";if((Get-FileHash $p).Hash -ne (Get-FileHash "+c.literal(reopened)+").Hash){throw 'Snapshot differs'}")
            step('reopen',lambda:read(reopened))
            local=c.fetch(saved,c.STATE/('smoke-'+run_id+'.pdf'))
            verified=step('independent-pdf',lambda:inspect(local,expected));assert verified['passed'],verified
            original=next((c.REPO/'Testing').glob('*_2014_*.pdf'));assert script_hashes(original)==script_hashes(local),'Original scripts changed'
            step('close-reopened',lambda:c.script('close',path=reopened))
            result['after']=resources.snapshot(started)
            assert not result['after']['guest']['reader_events'],result['after']['guest']['reader_events']
            assert not result['after']['guest']['resource_exhaustion'],result['after']['guest']['resource_exhaustion']
            result.update(status='complete',passed=True)
    except Exception as error:
        result.update(status='failed',passed=False,error=str(error))
        try:result['after']=resources.snapshot(started)
        except Exception as audit_error:result['audit_error']=str(audit_error)
    finally:
        stop.set();sampler.join(3)
        result.update(elapsed_seconds=round(time.time()-started,3),host_samples=samples)
        result['minimum_host_available_mib']=min(s['available_mib'] for s in samples)
        report.write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ['status','passed','elapsed_seconds','minimum_host_available_mib']},indent=2));print(report)
    if not result['passed']:print(result['error'])
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
