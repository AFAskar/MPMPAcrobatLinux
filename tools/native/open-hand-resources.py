#!/usr/bin/env python3
"""2024 Open Hand Wholeness uses/Wisdom/rest/removal and changed cold persistence.

Original class/subclass dropdown controls, nine independently checked states.
Structural18 abilities are not legal feat/ASI construction. Native-only until
matched with Reader; not healing execution, all Monk choices or table readiness.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--input',type=Path,required=True)
p.add_argument('--binary',type=Path,required=True)
p.add_argument('--pdfium',type=Path)
p.add_argument('--restore-baseline',action='store_true')
p.add_argument('--removal-roundtrip',action='store_true',help='Cold removed5, original readd6, changed save and cold6; requires level5/Wis16 input')
args=p.parse_args()
assert not (args.restore_baseline and args.removal_roundtrip)
sys.path[:0]=[str(ROOT/'tools/native'),str(ROOT/'tools/acrobat')]
import fighter_additional_diagnostics as diag
import subclass_audit_qualification as qual
from workflow_state_comparison import encoded_state
from verify import canonical_fields,inspect,script_hashes
from pypdf import PdfReader

def module(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/'tools/native'/file)
 result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
style=module('open_hand_style','default-style-persistence.py')
summary=module('open_hand_summary','fighter-styles.py').SUMMARY
folder=ROOT/'output/testing'/('open-hand-resources-'+str(time.time_ns()));folder.mkdir()
print(folder,flush=True)
source=args.input.resolve();binary=args.binary.resolve();observer=(ROOT/'tools/native/open-hand-resource-observer.js').read_text()
report={'passed':False,'scope':__doc__,'input':str(source),'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'observer_sha256':hashlib.sha256(observer.encode()).hexdigest(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'verifier_sha256':hashlib.sha256((ROOT/'tools/native/verify-generated-fields.py').read_bytes()).hexdigest(),'restore_baseline':args.restore_baseline,'removal_roundtrip':args.removal_roundtrip,'phases':[],'probes':[]}
steps=[];captures=[]
def call(code):
 steps.extend([{'op':'eval','code':'__host.command('+json.dumps(code)+')'},{'op':'advance','ms':1100}])
def install():
 steps.extend([{'op':'advance','ms':5100},{'op':'eval','code':"Value('User Script',"+json.dumps(observer)+");__host.command('RunUserScript(false)')"}])
def edit(wis):
 steps.extend([{'op':'user-edit','field':'Wis','value':str(wis)},{'op':'advance','ms':1100}])
def capture(label,level,wis,used='',other_used=None):
 steps.extend([{'op':'eval','code':diag.native_request()},{'op':'eval','code':summary}]);pdf=folder/(label+'.pdf');captures.append((label,len(steps)-1,pdf,level,wis,used,other_used or {}));steps.append({'op':'save','path':str(pdf)})
def clean(label):
 pdf=folder/(label+'.pdf');steps.extend([{'op':'eval','code':"Value('PC Name','Open Hand resource workflow');Value('User Script','');"},{'op':'save','path':str(pdf)}]);return pdf

def run(label,input,dialogs):
 scenario=folder/(label+'-scenario.json');probe=folder/(label+'-probe.json');scenario.write_text(json.dumps({'steps':steps,'dialogs':dialogs}));env=dict(os.environ,MPMB_DIALOG_TRACE_DIR=str(folder/(label+'-dialogs')))
 if args.pdfium:env['MPMB_PDFIUM']=str(args.pdfium.resolve())
 with (folder/(label+'.log')).open('w') as log:process=subprocess.run([str(binary),str(input),'--probe',str(scenario),str(probe)],stdout=log,stderr=log,env=env,timeout=1500)
 data=json.loads(probe.read_text());messages=[m['text'] for m in data['diagnostics']['console']['messages']];assert messages==['2024 Open Hand resource sentinel'],messages
 strict=copy.deepcopy(data);strict['diagnostics']['console']['messages']=[];q=qual.qualify_probe(process.returncode,strict);assert q['passed'],q;report['probes'].append({'path':str(probe),'qualification':q,'expected_console':messages})
 for invocation,(label,index,pdf,level,wis,used,other_used) in enumerate(captures,1):
  assert data['stages'][index-1]['result']==diag.DONE+str(invocation)
  state=style.saved_capture(pdf,data['stages'][index]['result'],source)
  assert not state['errors'] and state['identity']=={'level':level,'subclass':'monk-open hand'}
  assert state['calculation']=={'app':True,'doc':True,'delay':False}
  assert state['fields']['Wis']==str(wis) and state['fields']['Wis Mod']==str((wis-10)//2)
  assert state['fields']['Character Level']==str(level) and state['fields']['AC']==str(14+(wis-10)//2)
  rows=state['rows'];expected={'Focus Points':(str(level),other_used.get('Focus Points',''),'short rest'),'Uncanny Metabolism':('1',other_used.get('Uncanny Metabolism',''),'long rest')}
  if level>=6:expected['Wholeness of Body']=(str(max(1,(wis-10)//2)),used,'   LR')
  seen=set()
  for row in rows:
   names=[n for n in expected if row['name'].startswith(n)];assert len(names)==1 and names[0] not in seen,(label,row);name=names[0];seen.add(name);assert (row['max'],row['used'],row['recovery'])==expected[name],(label,row,expected[name])
  assert seen==set(expected)
  reader=PdfReader(pdf);fields=canonical_fields(reader);co=reader.trailer['/Root']['/AcroForm'].get('/CO',[]);physical=[]
  for row in rows:
   name='Limited Feature Max Usages '+row['row'];ref=fields[name]['reference'];indexes=[i for i,entry in enumerate(co) if getattr(entry,'idnum',None)==ref];assert indexes==([] if row['calcOrderIndex']==-1 else [row['calcOrderIndex']]),(label,name,indexes,row['calcOrderIndex']);physical.append({'field':name,'indexes':indexes})
  expected_values=dict(state['fields'],**state['resources']);api=folder/(label+'-expected.json');api.write_text(json.dumps(expected_values));verification=folder/(label+'-verification')
  with (folder/(label+'-verification.log')).open('w') as log:p=subprocess.run([sys.executable,str(ROOT/'tools/native/verify-generated-fields.py'),str(pdf),str(api),str(verification)],stdout=log,stderr=log,timeout=600)
  checked=json.loads((verification/'verification.json').read_text());assert p.returncode==0 and checked['passed'] and checked['source_sha256']==report['verifier_sha256']
  assert script_hashes(pdf)==script_hashes(source)
  report['phases'].append({'label':label,'pdf':str(pdf),'state':state,'canonical':checked,'physical_co_slots':len(co),'physical_rows':physical});(folder/'progress.json').write_text(json.dumps(report,indent=2))

try:
 if args.removal_roundtrip:
  report['scope']='Native-only cold removal5/readdition6/cold6 resource persistence; not class-dropdown or full Monk qualification.'
  install();capture('cold-removed5',5,16);call("ApplyClasses('Monk (Warrior of the Open Hand) 6',false)");capture('readded6',6,16);saved=clean('saved');run('cold-removed-readded',source,[{'title':'CHANGES ALERT DIALOG','result':'ok'}])
  steps=[];captures=[];install();capture('cold-readded6',6,16);final=clean('final');run('cold',saved,[])
 else:
  install()
  if args.restore_baseline:call("resetLimFeaUsed('long rest')");edit(18)
  steps.append({'op':'eval','code':"Value('PC Name','Open Hand resource workflow');"});call('SelectClass()');capture('selected6',6,18)
  for resource_name,value in [('Focus Points','2'),('Uncanny Metabolism','1'),('Wholeness of Body','3')]:
   code="var names=[];for(var i=0;i<numFields;i++){var n=getNthFieldName(i),m=/^Limited Feature (\\d+)$/.exec(n);if(m&&getField(n).valueAsString.indexOf("+json.dumps(resource_name)+")===0)names.push('Limited Feature Used '+m[1]);}if(names.length!==1)throw Error('Missing unique resource');__host.userEdit(names[0],"+json.dumps(value)+");"
   steps.extend([{'op':'eval','code':code},{'op':'advance','ms':1100}])
  capture('spent6',6,18,'3',{'Focus Points':'2','Uncanny Metabolism':'1'});call("resetLimFeaUsed('short rest')");capture('short-rest6',6,18,'3',{'Uncanny Metabolism':'1'});edit(8);capture('wis8',6,8,'3',{'Uncanny Metabolism':'1'});call("resetLimFeaUsed('long rest')");capture('long-rest8',6,8);edit(16);capture('wis16',6,16);call("ApplyClasses('Monk (Warrior of the Open Hand) 5',false)");capture('removed5',5,16);call("ApplyClasses('Monk (Warrior of the Open Hand) 6',false)");capture('readded6',6,16);saved=clean('saved')
  dialogs=[{'title':'CLASS SELECTION DIALOG','event':'r0CD','select':{'r0CD':'Monk'}},{'title':'CLASS SELECTION DIALOG','event':'r0SD','select':{'r0SD':'Warrior of the Open Hand'}},{'title':'CLASS SELECTION DIALOG','event':'r0LV','values':{'r0LV':'6'}},{'title':'CLASS SELECTION DIALOG','result':'ok'}]+[{'title':'CHANGES ALERT DIALOG','result':'ok'}]*10
  run('class-resources',source,dialogs)
  steps=[];captures=[];install();capture('cold-readded6',6,16);final=clean('final');run('cold',saved,[])
 assert len(report['phases'])==(3 if args.removal_roundtrip else 9) and encoded_state(report['phases'][-2]['state'])==encoded_state(report['phases'][-1]['state'])
 for pdf in [saved,final]:
  independent=inspect(pdf,{'PC Name':'Open Hand resource workflow','Character Level':'6','Wis':'16'});assert independent['passed'],independent;report.setdefault('clean_saves',[]).append(independent)
 assert hashlib.sha256(source.read_bytes()).hexdigest()==report['input_sha256'] and hashlib.sha256(binary.read_bytes()).hexdigest()==report['binary_sha256']
 report.update(passed=True,pdf=str(final))
except Exception as error:report['error']=str(error);raise
finally:(folder/'resources.json').write_text(json.dumps(report,indent=2));print(folder,flush=True)
