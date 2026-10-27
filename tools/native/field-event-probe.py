#!/usr/bin/env python3
"""Measure setter/event semantics through MPMB's original manual add-on workflow."""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import canonical_fields, field_text

ADDON = r'''
var iFileName = "Native field event probe.js";
(function(d, originals) {
 var output=[], f=d.getField('Player Name'), g=d.getField('Str Mod');
 var saved={value:f.valueAsString,calculate:d.calculate,appCalculate:app.calculate,delay:d.delay};
 var log="if(tDoc.__fieldProbeEvents.length<80)tDoc.__fieldProbeEvents.push({event:event.name,type:typeof event.value,value:String(event.value),willCommit:event.willCommit===undefined?'absent':event.willCommit});";
 function run(name,fn,field){d.__fieldProbeEvents=[];try{fn();var beforeCalculate=d.__fieldProbeEvents.length;d.calculateNow();output.push({name:name,beforeCalculate:beforeCalculate,value:field.valueAsString,valueType:typeof field.value,events:d.__fieldProbeEvents.slice()});}catch(e){output.push({name:name,error:String(e),events:d.__fieldProbeEvents.slice()});}}
 try {
  d.calculate=true;app.calculate=true;d.delay=false;
  f.setAction('Keystroke',log);f.setAction('Validate',log);f.setAction('Format',log);
  run('script setter numeric',function(){f.value=17},f);
  run('script setter unchanged',function(){f.value=17},f);
  run('text setter plain string',function(){f.value='alpha'},f);
  run('text setter numeric string',function(){f.value='18'},f);
  run('text setter array',function(){f.value=['a','b']},f);
  run('text setter object',function(){f.value={a:1}},f);
  f.setAction('Keystroke','');f.setAction('Validate','');f.setAction('Format','');f.value='7';
  f.setAction('Keystroke',log+'event.rc=!isNaN(event.value);');f.setAction('Validate',log);f.setAction('Format',log);
  run('numeric keystroke rejects undefined',function(){f.value=undefined},f);
  f.setAction('Keystroke','');f.setAction('Validate','');f.setAction('Format','');f.value='7';
  f.setAction('Validate',log+'event.rc=false;');
  run('validate rejects setter',function(){f.value=18},f);
  f.setAction('Keystroke','');f.setAction('Validate','');f.setAction('Format','');
  g.setAction('Keystroke',log+'event.rc=false;');g.setAction('Validate',log+'event.rc=false;');g.setAction('Format',log);
  g.setAction('Calculate','event.value=42;');
  run('calculated value rejection path',function(){d.calculateNow()},g);
  g.setAction('Calculate','event.target.value=43;');
  run('calculate target setter',function(){d.calculateNow()},g);
 } finally {
  for(var name in originals){var field=d.getField(name);for(var type in originals[name])field.setAction(type,originals[name][type]);}
  f.value=saved.value;d.calculateNow();d.calculate=saved.calculate;app.calculate=saved.appCalculate;d.delay=saved.delay;
 }
 Value('PC Name',JSON.stringify(output));
})(tDoc, __RESTORE__);
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--readiness',type=Path);parser.add_argument('--native-only',action='store_true');args=parser.parse_args()
    if not args.native_only:
        assert args.readiness and json.loads(args.readiness.read_text())['passed']
    folder=ROOT/'output/testing'/('field-events-'+str(time.time_ns()));folder.mkdir()
    source=next((ROOT/'Testing').glob('*_2024_*.pdf'));reader=PdfReader(source);fields=canonical_fields(reader)
    originals={}
    for name in ['Player Name','Str Mod']:
        node=reader.get_object(fields[name]['reference']);actions={};nodes=[node]+[ref.get_object() for ref in node.get('/Kids',[])]
        for obj in nodes:
            for key,action in obj.get('/AA',{}).items():
                action=action.get_object()
                if action.get('/JS') is not None and key not in actions:actions[key]=field_text(action['/JS'])
        originals[name]={trigger:actions.get(key,'') for trigger,key in [('Keystroke','/K'),('Validate','/V'),('Format','/F'),('Calculate','/C')]}
    addon=ADDON.replace('__RESTORE__',json.dumps(originals));(folder/'probe-addon.js').write_text(addon)
    report={'passed':False,'readiness':str(args.readiness) if args.readiness else None};print(folder,flush=True)
    try:
        spec={'dialogs':[{'result':'ok'}]*30,'alerts':[1]*30,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':"getField('User Script').value="+json.dumps(addon)},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'advance','ms':1000},{'op':'eval','code':"JSON.parse(What('PC Name'))"}]}
        scenario,evidence=folder/'native-scenario.json',folder/'native-report.json';scenario.write_text(json.dumps(spec))
        with (folder/'native.log').open('w') as log:proc=subprocess.run([str(ROOT/'target/debug/mpmb-reader'),str(source),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=240)
        data=json.loads(evidence.read_text());assert proc.returncode==0 and data['passed'],data.get('error');report['native']=data['stages'][-1]['result']
        (folder/'events.json').write_text(json.dumps(report,indent=2))
        if not args.native_only:
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Reference suite requires no pre-existing document'
                path=c.remote_path('runs/field-events-'+str(time.time_ns())+'.pdf');c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/blank-2024.pdf'))+' '+c.literal(path)+' -Force;(Get-Item '+c.literal(path)+').IsReadOnly=$false')
                c.script('set',path=path,values={'User Script':addon});c.script('call',path=path,name='RunUserScript',args=[False]);result=c.script('read',path=path,fields=['PC Name']);report['reader']=json.loads(result['fields']['PC Name'])
                saved=path[:-4]+'-saved.pdf';c.script('save',path=path,output=saved);c.script('close',path=saved)
            report['equal']=report['native']==report['reader']
        report['execution_completed']=True
        report['passed']=bool(report.get('equal')) if not args.native_only else None
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        (folder/'events.json').write_text(json.dumps(report,indent=2));print(folder/'events.json',flush=True)

    return 0 if args.native_only or report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
