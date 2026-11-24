#!/usr/bin/env python3
"""Create a disposable Druid and exercise the actual wild-shape field event."""
import json
import time
import control as c
from verify import inspect,script_hashes

def test(rule,run_id,on_active=None):
    mark=on_active or (lambda _path:None)
    path=c.remote_path('runs/druid-'+rule+'-'+run_id+'.pdf')
    source=c.remote_path('fixtures/blank-'+rule+'.pdf')
    c.powershell('Copy-Item '+c.literal(source)+' '+c.literal(path)+' -Force;(Get-Item '+c.literal(path)+').IsReadOnly=$false')
    mark(path)
    c.script('set',path=path,values={'PC Name':'MPMB Druid '+rule,'Str':10,'Dex':10,'Con':10,'Int':14,'Wis':16,'Cha':10})
    class_text='Druid (Circle of the Moon) 2' if rule=='2014' else 'Druid 2'
    c.script('call',path=path,name='ApplyClasses',args=[class_text,False])
    before=c.script('read',path=path,fields=['Character Level','Class and Levels','HD1 Level','HD1 Die'])
    assert before['fields']['Character Level']=='2' and 'Druid' in before['fields']['Class and Levels'] and before['fields']['HD1 Level']=='2' and before['fields']['HD1 Die']=='8',before
    template=c.script('call',path=path,name='DoTemplate',args=['WSfront','Add',None,True])
    assert template['pages']==before['pages']+1,template
    prefix=template['value']
    c.script('focus',path=path,field=prefix+'Wildshape.Race.1')
    c.command('paste',value='wolf')
    expected={'PC Name':'MPMB Druid '+rule,'Character Level':'2',prefix+'Wildshape.Race.1':'wolf',prefix+'Wildshape.1.Ability.Str.Score':('12' if rule=='2014' else '14')}
    actual=c.script('read',path=path,fields=list(expected))
    assert actual['fields']==expected,(expected,actual)
    output=path[:-4]+'-saved.pdf'
    c.script('save',path=path,output=output);mark(output);c.script('close',path=output);mark(None)
    reopened=output[:-4]+'-reopened.pdf'
    c.powershell('Copy-Item '+c.literal(output)+' '+c.literal(reopened)+' -Force;if((Get-FileHash '+c.literal(output)+').Hash -ne (Get-FileHash '+c.literal(reopened)+").Hash){throw 'Snapshot hash differs'}")
    mark(reopened)
    again=c.script('read',path=reopened,fields=list(expected));assert again['fields']==expected,again
    local=c.fetch(output,c.STATE/('druid-'+rule+'-'+run_id+'.pdf'));verified=inspect(local,expected);assert verified['passed'],verified
    original=next((c.REPO/'Testing').glob('*_'+rule+'_*.pdf'))
    assert script_hashes(original)==script_hashes(local),'Document scripts changed'
    c.script('close',path=reopened);mark(None)
    return dict(template=template,reader=again,pdf=verified)

if __name__=='__main__':
    import sys
    with c.desktop_lock():
        result=test(sys.argv[1],str(int(time.time())));(c.STATE/('wildshape-'+sys.argv[1]+'.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
