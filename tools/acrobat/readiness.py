#!/usr/bin/env python3
"""Measured Acrobat readiness cases with independent saved-PDF verification."""
import argparse
import json
import time
import subprocess
from pathlib import Path
import control as c
from verify import inspect,script_hashes,canonical_fields
import resources

def case_plan(scope):
    fixtures=[('blank-'+x if x!='ashnar' else x) for x in scope]
    names=['desktop-session','reader-bridge','reject-outside-workspace']
    for fixture in fixtures:
        names.append(fixture+'-read')
        names.extend(([fixture+'-keyboard-and-calculation',fixture+'-multiclass',fixture+'-manual-addon',fixture+'-companion-page'] if fixture!='ashnar' else ['ashnar-class-dialog-cancel','ashnar-regenerate-spells']))
        names.append(fixture+'-roundtrip')
    for suffix in ['wildshape-roundtrip','spell-generation-roundtrip']:
        names.extend(['druid-'+x+'-'+suffix for x in scope if x!='ashnar'])
    names.append('no-new-reader-crash-or-resource-exhaustion')
    return names


def cases_complete(cases, plan):
    return (isinstance(plan, list) and bool(plan)
            and [case['name'] for case in cases] == plan
            and all(case.get('passed') is True for case in cases))


def retain_and_close_active(active_path):
    """Retain and close the active disposable PDF while still holding desktop_lock()."""
    info = {'active_path': active_path, 'retained_path': None, 'closed': False}
    try:
        windows = c.command('inspect')
    except Exception as error:
        info['inspect_error'] = str(error)
        windows = None
    open_pdfs = [
        w for w in (windows or [])
        if w.get('class') == 'AcrobatSDIWindow' and '.pdf' in w.get('name', '').lower()
    ]
    if windows is not None and not open_pdfs:
        info['open_windows'] = []
        info['closed'] = True
        return info
    info['open_windows'] = [w.get('name', '') for w in open_pdfs] if windows is not None else None
    retained = (active_path[:-4] + '-failed-retained.pdf') if active_path.lower().endswith('.pdf') else (active_path + '-failed-retained.pdf')
    close_target = active_path
    try:
        info['save'] = c.raw_script('save', path=active_path, output=retained)
        info['retained_path'] = retained
        close_target = retained
    except Exception as error:
        info['save_error'] = str(error)
    try:
        close_result = c.command('close_document', path=close_target)
        info['close'] = close_result
        info['closed'] = True
        if isinstance(close_result, dict) and close_result.get('process_terminated'):
            (c.STATE / 'reader-session.json').unlink(missing_ok=True)
    except Exception as error:
        info['close_error'] = str(error)
    return info


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',action='append',choices=['2014','2024','ashnar'])
    args=parser.parse_args()
    scope=args.fixture or ['2014','2024','ashnar']
    if len(scope)!=len(set(scope)):parser.error('Duplicate fixtures are not allowed')
    fixtures=[('blank-'+x if x!='ashnar' else x) for x in scope]
    planned=case_plan(scope)
    cases=[];started=time.time();run_id=str(int(started));report=c.STATE/('readiness-'+run_id+'.json');fingerprint=c.harness_fingerprint();host_start=resources.host()
    cleanup=None
    active_doc={'path':None}
    def set_active(path):
        active_doc['path']=path
    def write_report(status):
        data=dict(started=started,run_id=run_id,status=status,planned_cases=len(planned),fixture_scope=scope,expected_cases=planned,harness_sha256=fingerprint,host_start=host_start,elapsed_seconds=round(time.time()-started,3),cases=cases,passed=status=='complete' and cases_complete(cases,planned))
        if cleanup is not None:
            data['cleanup']=cleanup
        rendered=json.dumps(data,indent=2);report.write_text(rendered)
        temporary=c.STATE/'readiness-latest.tmp';temporary.write_text(rendered);temporary.replace(c.STATE/'readiness-latest.json')
    write_report('running')
    def record(name,fn):
        t=time.monotonic()
        try: detail=fn();passed=True
        except Exception as e: detail={'error':str(e)};passed=False
        cases.append(dict(name=name,passed=passed,seconds=round(time.monotonic()-t,3),detail=detail))
        write_report('running' if passed else 'failed')
        print(name, 'PASS' if passed else 'FAIL',flush=True)
        if not passed: raise RuntimeError('Readiness stopped: '+name+'; evidence: '+str(report))
    def assert_fields(result,expected):
        actual=result['fields'];assert all(actual.get(k)==str(v) for k,v in expected.items()),(expected,actual)
        return result
    with c.desktop_lock():
        try:
            def isolated_desktop():
                windows=c.command('inspect')
                assert not [w for w in windows if w.get('class')=='AcrobatSDIWindow' and '.pdf' in w.get('name','').lower()], 'Pre-existing document must be retained/closed before readiness'
                return c.command('health')
            record('desktop-session',isolated_desktop)
            record('reader-bridge',lambda:c.script('ping'))
            def reject_outside():
                try:c.command('open',path=r'C:\Windows\win.ini')
                except RuntimeError as error:
                    assert 'Path outside testing workspace' in str(error),str(error)
                    return {'refused':True}
                raise AssertionError('Outside path was accepted')
            record('reject-outside-workspace',reject_outside)
            for fixture in fixtures:
                path=c.remote_path('runs/'+fixture+'-'+run_id+'-readiness.pdf')
                c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/'+fixture+'.pdf'))+' '+c.literal(path)+' -Force;(Get-Item '+c.literal(path)+').IsReadOnly=$false')
                expected={'PC Name':'Ashnar','Str':'8','Str Mod':'-1','Character Level':'12'} if fixture=='ashnar' else {'PC Name':''}
                set_active(path)
                record(fixture+'-read',lambda p=path,e=expected:assert_fields(c.script('read',path=p,fields=list(e)),e))
                if fixture!='ashnar':
                    expected={'PC Name':'MPMB-'+fixture+'-4827','Str':'18','Str Mod':'4'}
                    def edit(p=path,e=expected):
                        c.script('focus',path=p,field='PC Name')
                        c.command('paste',value=e['PC Name'])
                        c.script('focus',path=p,field='Str')
                        c.command('paste',value=e['Str'])
                        return assert_fields(c.script('read',path=p,fields=list(e)),e)
                    record(fixture+'-keyboard-and-calculation',edit)
                    def multiclass(p=path,e=expected):
                        c.script('call',path=p,name='ApplyClasses',args=['Fighter 1 / Wizard 1',False])
                        extra={'Class and Levels':'Fighter 1 / Wizard 1','Character Level':'2','Proficiency Bonus':'2','HD1 Level':'1','HD2 Level':'1'}
                        value=assert_fields(c.script('read',path=p,fields=list(extra)),extra)
                        e.update(extra);return value
                    record(fixture+'-multiclass',multiclass)
                    def addon(p=path,e=expected):
                        code=(c.REPO/'Testing/addons/readiness-sentinel.js').read_text()
                        c.script('set',path=p,values={'User Script':code})
                        result=c.script('call',path=p,name='RunUserScript',args=[False])
                        extra={'Player Name':'MPMB add-on executed'}
                        value=assert_fields(c.script('read',path=p,fields=list(extra)),extra)
                        e.update(extra);return dict(import_result=result,execution=value)
                    record(fixture+'-manual-addon',addon)
                    def companion(p=path,e=expected):
                        before=c.script('read',path=p,fields=[])['pages']
                        result=c.script('call',path=p,name='DoTemplate',args=['AScomp','Add',None,True])
                        prefix=result['value'];assert result['pages']==before+1,result
                        c.script('call',path=p,name='ApplyCompRace',args=['wolf',prefix])
                        extra={prefix+'Comp.Race':'wolf',prefix+'Comp.Use.Ability.Str.Score':('12' if fixture=='blank-2014' else '14')}
                        value=assert_fields(c.script('read',path=p,fields=list(extra)),extra)
                        e.update(extra)
                        return dict(template=result,companion=value)
                    record(fixture+'-companion-page',companion)
                else:
                    from dialog_probe import probe
                    record('ashnar-class-dialog-cancel',lambda p=path:probe(p))
                    def regenerate_spells(p=path):
                        result=c.script('call',path=p,name='GenerateSpellSheet',args=[True]);assert result.get('value') is True,result
                        prefixes=c.script('read',path=p,fields=['Template.extras.SSfront'])['fields']['Template.extras.SSfront']
                        prefix=[x for x in prefixes.split(',') if x][-1]
                        expected_spells={prefix+'spells.remember.1':'minor illusion##atwill##monk',prefix+'spells.remember.5':'darkness##2##monk',prefix+'spells.remember.24':'darkness##oncelr##dark elf'}
                        return dict(generated=result,spells=assert_fields(c.script('read',path=p,fields=list(expected_spells)),expected_spells))
                    record(fixture+'-regenerate-spells',regenerate_spells)
                output=c.remote_path('runs/'+fixture+'-'+run_id+'-roundtrip.pdf')
                def roundtrip(p=path,o=output,e=expected,f=fixture):
                    c.script('save',path=p,output=o)
                    set_active(o)
                    c.script('close',path=o)
                    set_active(None)
                    # Reopen an immutable, byte-identical snapshot after Reader releases the save.
                    # Reader's protected-mode broker can reject an immediate same-path reopen.
                    reopened_path=o[:-4]+'-reopened.pdf'
                    snapshot=c.powershell("$p="+c.literal(o)+";$deadline=[DateTime]::UtcNow.AddSeconds(20);while($true){try{$h=[IO.File]::Open($p,'Open','Read','None');$h.Dispose();break}catch{if([DateTime]::UtcNow -gt $deadline){throw};Start-Sleep -Milliseconds 100}};Copy-Item $p "+c.literal(reopened_path)+" -Force;if((Get-FileHash $p).Hash -ne (Get-FileHash "+c.literal(reopened_path)+").Hash){throw 'Reopen snapshot differs'}")
                    set_active(reopened_path)
                    reopened=assert_fields(c.script('read',path=reopened_path,fields=list(e)),e)
                    local=c.fetch(o,c.STATE/(f+'-'+run_id+'-roundtrip.pdf'))
                    verified=inspect(local,e);assert verified['passed'],verified
                    source=next(x for x in (c.REPO/'Testing').glob('*.pdf') if ('Ashnar' in x.name if f=='ashnar' else ('_2014_' in x.name if f=='blank-2014' else '_2024_' in x.name)))
                    assert script_hashes(source)==script_hashes(local),'Embedded document JavaScript changed'
                    verified['document_scripts_preserved']=True
                    if f!='ashnar':
                        from pypdf import PdfReader
                        saved_fields=canonical_fields(PdfReader(local))
                        assert str(saved_fields['User Script'].get('/V','')).replace('\r\n','\n').replace('\r','\n')==(c.REPO/'Testing/addons/readiness-sentinel.js').read_text(),'Manual add-on did not persist'
                        verified['manual_addon_preserved']=True
                    if f=='ashnar':
                        from pypdf import PdfReader
                        original_fields=canonical_fields(PdfReader(source));saved_fields=canonical_fields(PdfReader(local))
                        key='User_Imported_Files.Stringified'
                        assert original_fields[key].get('/V')==saved_fields[key].get('/V'),'Imported scripts changed'
                        verified['imported_content_preserved']=True
                        remembered=[str(v.get('/V','')) for k,v in saved_fields.items() if 'spells.remember.' in k]
                        assert any('minor illusion' in x for x in remembered) and any('darkness' in x for x in remembered),'Ashnar spell entries lost'
                        verified['saved_spell_entries_preserved']=True
                    c.script('close',path=reopened_path)
                    set_active(None)
                    return dict(reader=reopened,pdf=verified)
                record(fixture+'-roundtrip',roundtrip)
            from wildshape import test as wildshape_test
            for rule in [x for x in scope if x!='ashnar']:
                record('druid-'+rule+'-wildshape-roundtrip',lambda r=rule:wildshape_test(r,run_id,on_active=set_active))
            from spells import test as spell_test
            for rule in [x for x in scope if x!='ashnar']:
                record('druid-'+rule+'-spell-generation-roundtrip',lambda r=rule:spell_test(r,run_id,on_active=set_active))
            def audit_resources():
                assert c.harness_fingerprint()==fingerprint,'Harness or fixture configuration changed during this run'
                evidence=resources.snapshot(started)
                assert evidence['host']['oom_kills']==host_start['oom_kills'],'Host OOM kill occurred during the suite'
                assert not evidence['guest']['reader_events'],evidence['guest']['reader_events']
                assert not evidence['guest']['resource_exhaustion'],evidence['guest']['resource_exhaustion']
                return evidence
            record('no-new-reader-crash-or-resource-exhaustion',audit_resources)
            write_report('complete')
            print(report)
        except Exception:
            if active_doc['path']:
                cleanup=retain_and_close_active(active_doc['path'])
                set_active(None)
                write_report('failed')
            raise
    return 0 if cases_complete(cases,planned) else 1

if __name__=='__main__':raise SystemExit(main())
