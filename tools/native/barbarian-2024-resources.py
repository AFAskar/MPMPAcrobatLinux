#!/usr/bin/env python3
"""2024 Berserker Rage spending, partial short-rest recovery and persistence.

Original field actions/rest callback on an explicitly instrumented input.
Native-only until actual Reader comparison and changed mixed saves pass.
"""
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect,script_hashes
import fighter_additional_diagnostics as diagnostics

def module(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/'tools/native'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--instrumentation',type=Path,required=True);a=p.parse_args();source=a.input.resolve();instrumentation=json.loads(a.instrumentation.read_text());assert instrumentation['passed'] and Path(instrumentation['input'])==source and hashlib.sha256(source.read_bytes()).hexdigest()==instrumentation['input_sha256']
 folder=ROOT/'output/testing'/('native-barbarian-2024-resources-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
 profile=module('profile','fighter-styles.py');style=module('style','default-style-persistence.py');fields=module('fields','field-state-comparison.py')
 observer=(ROOT/'tools/native/barbarian-2024-observer.js').read_text();binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
 report={'passed':False,'scope':__doc__,'input':str(source),'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'observer_sha256':hashlib.sha256(observer.encode()).hexdigest(),'diagnostic_mode':'startup-script-timer','instrumentation':str(a.instrumentation.resolve()),'diagnostic_helper_sha256':hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest(),'test_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'phases':[],'full_class_coverage':False,'reader_qualified':False}
 def start():
  assert instrumentation['observer_sha256']==hashlib.sha256(observer.encode()).hexdigest()
  return [{'op':'advance','ms':5100},{'op':'assert','values':{'User Script':'// MPMB workflow observer installed'}}],[],[]
 def capture(steps,captures,label,used=''):
  steps.append({'op':'eval','code':diagnostics.native_request()});index=len(steps);pdf=folder/(label+'-diagnostic.pdf');steps.extend([{'op':'eval','code':profile.SUMMARY},{'op':'save','path':str(pdf)}]);captures.append((label,index,pdf,used))
 def call(steps,code):steps.extend([{'op':'eval','code':'__host.command('+json.dumps(code)+')'},{'op':'advance','ms':1000}])
 def choose(steps,dialogs,path,ack=True):
  call(steps,'ClassFeatureOptions()');dialogs.append({'title':'MPMB menu','button_path':path})
  if ack:dialogs.append({'title':'CHANGES ALERT DIALOG','result':'ok'})
 def save(steps,label):
  pdf=folder/(label+'.pdf');steps.extend([{'op':'eval','code':"Value('User Script','');Value('PC Name','2024 Berserker resource compatibility')"},{'op':'save','path':str(pdf)}]);return pdf
 def run(label,pdf,steps,dialogs,captures):
  scenario=folder/(label+'-scenario.json');evidence=folder/(label+'-probe.json');scenario.write_text(json.dumps({'steps':steps,'dialogs':dialogs}))
  with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(pdf),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=480,env=dict(os.environ,MPMB_DIALOG_TRACE_DIR=str(folder/(label+'-dialogs'))))
  d=json.loads(evidence.read_text());assert proc.returncode==0 and d['passed'],d.get('error');assert not d['diagnostics']['errors'] ,d['diagnostics'];assert [m['text'] for m in d['diagnostics']['console']['messages']]==['MPMB 2024 Barbarian workflow console sentinel'],d['diagnostics']['console']
  observed=[json.loads(p.read_text())['description']['name'] for p in sorted((folder/(label+'-dialogs')).glob('dialog-*.json'))];assert observed==[r['title'] for r in dialogs],('Dialog profile did not execute exactly',observed,dialogs)
  markers=[s['result'] for s in d['stages'] if isinstance(s.get('result'),str) and s['result'].startswith(diagnostics.DONE)];assert markers==[diagnostics.DONE+str(i+1) for i in range(len(captures))]
  for name,index,path,used in captures:
   state=style.saved_capture(path,d['stages'][index]['result'],pdf);assert not state['errors'];assert state['identity']=={'level':3,'subclass':'barbarian-berserker'};assert state['calculation']=={'app':True,'doc':True,'delay':False};assert state['subclassDefinition']=={'name':'Path of the Berserker','source':[['SRD24',30],['PHB24',54]]}
   resources=state['resources'];assert resources['Limited Feature 1']=='Rage (+2 damage, regain 1/SR)' and resources['Limited Feature Max Usages 1']=='3' and resources['Limited Feature Recovery 1']=='long rest' and resources['Limited Feature Used 1']==used,(name,resources)
   assert state['fields']['AC']=='15' and state['fields']['Attack.1.Damage']=='1d12+4';assert state['fields']['Str']=='18' and state['fields']['Dex']=='14' and state['fields']['Con']=='16'
   expected=dict(state['fields'],**resources,**state['reactions']);canonical=fields.compare(path,expected);visible=inspect(path,{n:v for n,v in resources.items() if v});assert visible['passed'];assert script_hashes(path)==script_hashes(source)
   report['phases'].append({'label':name,'state':state,'pdf':str(path),'summary':d['stages'][index]['result'],'canonical':canonical,'visible':visible,'probe':str(evidence)})

 try:
  steps,dialogs,captures=start()
  for field,value in [('Str','18'),('Dex','14'),('Con','16'),('Int','10'),('Wis','12'),('Cha','8')]:steps.extend([{'op':'user-edit','field':field,'value':value},{'op':'advance','ms':1000}])
  call(steps,"ApplyClasses('Barbarian (Berserker) 3',false)");dialogs.append({'title':'CHANGES ALERT DIALOG','result':'ok'});steps.extend([{'op':'user-edit','field':'Attack.1.Weapon Selection','value':'Greataxe'},{'op':'advance','ms':1000}]);capture(steps,captures,'berserker3')
  steps.extend([{'op':'user-edit','field':'Limited Feature Used 1','value':'3'},{'op':'advance','ms':1000}]);capture(steps,captures,'spent3','3');call(steps,"resetLimFeaUsed('short rest')");capture(steps,captures,'short-rest3','2');call(steps,"resetLimFeaUsed('long rest')");capture(steps,captures,'long-rest3')
  steps.extend([{'op':'user-edit','field':'Limited Feature Used 1','value':'2'},{'op':'advance','ms':1000}]);capture(steps,captures,'spent-again3','2');spent=save(steps,'native-spent3');run('creation',source,steps,dialogs,captures)
  steps,dialogs,captures=start();capture(steps,captures,'cold-spent3','2');call(steps,"resetLimFeaUsed('short rest')");capture(steps,captures,'cold-short-rest3','1');call(steps,"resetLimFeaUsed('long rest')");capture(steps,captures,'cold-long-rest3');final=save(steps,'native-rested3');run('spent-reopen',spent,steps,dialogs,captures)
  assert hashlib.sha256(source.read_bytes()).hexdigest()==report['input_sha256'];report.update(passed=True,pdf=str(final),spent_pdf=str(spent))

 except Exception as e:report['error']=str(e);raise
 finally:(folder/'resources.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'resources.json',flush=True)

if __name__=='__main__':main()
