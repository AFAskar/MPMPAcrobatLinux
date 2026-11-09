#!/usr/bin/env python3
"""Bounded Champion Superior Technique maneuvers, resource use and removal.

Original offered choices and actions only. Native creation is not a Reader or
complete-class pass; paired reference and changed mixed-engine saves are gates.
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
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);a=p.parse_args();source=a.input.resolve()
 folder=ROOT/'output/testing'/('native-fighter-superior-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
 profile=module('profile','fighter-styles.py');style=module('style','default-style-persistence.py');fields=module('fields','field-state-comparison.py')
 observer=(ROOT/'tools/native/fighter-superior-observer.js').read_text();binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
 report={'passed':False,'scope':__doc__,'input':str(source),'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'observer_sha256':hashlib.sha256(observer.encode()).hexdigest(),'diagnostic_mode':diagnostics.MODE,'diagnostic_helper_sha256':hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest(),'test_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'phases':[],'full_class_coverage':False,'reader_qualified':False}
 def start():
  setup=diagnostics.install(profile.SETUP,observer)
  return [{'op':'advance','ms':4100},{'op':'eval','code':"Value('User Script',"+json.dumps(setup)+");__host.command('RunUserScript(false)')"}],[],[]
 def capture(steps,captures,label,level,selected,maneuver,used=''):
  steps.append({'op':'eval','code':diagnostics.native_request()});index=len(steps);pdf=folder/(label+'-diagnostic.pdf');steps.extend([{'op':'eval','code':profile.SUMMARY},{'op':'save','path':str(pdf)}]);captures.append((label,index,pdf,level,selected,maneuver,used))
 def call(steps,code):steps.extend([{'op':'eval','code':'__host.command('+json.dumps(code)+')'},{'op':'advance','ms':1000}])
 def choose(steps,dialogs,path,ack=True):
  call(steps,'ClassFeatureOptions()');dialogs.append({'title':'MPMB menu','button_path':path})
  if ack:dialogs.append({'title':'CHANGES ALERT DIALOG','result':'ok'})
 def save(steps,label):
  pdf=folder/(label+'.pdf');steps.extend([{'op':'eval','code':"Value('User Script','');Value('PC Name','Champion Superior Technique compatibility')"},{'op':'save','path':str(pdf)}]);return pdf
 def run(label,pdf,steps,dialogs,captures):
  scenario=folder/(label+'-scenario.json');evidence=folder/(label+'-probe.json');scenario.write_text(json.dumps({'steps':steps,'dialogs':dialogs}))
  with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(pdf),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=480,env=dict(os.environ,MPMB_DIALOG_TRACE_DIR=str(folder/(label+'-dialogs'))))
  d=json.loads(evidence.read_text());assert proc.returncode==0 and d['passed'],d.get('error');assert not d['diagnostics']['errors'] and not d['diagnostics']['console']['messages'],d['diagnostics']
  observed=[json.loads(p.read_text())['description']['name'] for p in sorted((folder/(label+'-dialogs')).glob('dialog-*.json'))];assert observed==[r['title'] for r in dialogs],('Dialog profile did not execute exactly',observed,dialogs)
  markers=[s['result'] for s in d['stages'] if isinstance(s.get('result'),str) and s['result'].startswith(diagnostics.DONE)];assert markers==[diagnostics.DONE+str(i+1) for i in range(len(captures))]
  for name,index,path,level,selected,maneuver,used in captures:
   state=style.saved_capture(path,d['stages'][index]['result'],pdf);assert not state['errors'];assert state['identity']=={'level':level,'subclass':'fighter-champion'};assert state['additional']==selected;assert state['maneuvers']==([maneuver] if maneuver else [])
   resources=state['resources'];names=[n for n,v in resources.items() if n.startswith('Limited Feature ') and v.startswith('Combat Superiority')]
   if selected=='superior technique':
    assert len(names)==1;row=names[0].split()[-1];assert resources[names[0]]=='Combat Superiority (d6)';assert resources['Limited Feature Max Usages '+row]=='1' and resources['Limited Feature Recovery '+row]=='short rest';assert resources['Limited Feature Used '+row]==used
    assert state['bonus']=={'fighter':{'fighter-battle master':{'subclassfeature3.1':1}}}
   else:assert not names and not state['bonus']
   for text in ['disarming attack','riposte']:assert (text in state['notesText'].lower())==(maneuver==text),(name,text,state['notesText'])
   assert any('riposte' in v.lower() for v in state['reactions'].values())==(maneuver=='riposte')
   expected=dict(state['fields'],**resources,**state['reactions']);expected.update({'Class Features':state['featureText'],'Extra.Notes':state['notesText']});canonical=fields.compare(path,expected)
   visible=inspect(path,{n:v for n,v in resources.items() if v});assert visible['passed'];assert script_hashes(path)==script_hashes(source)
   report['phases'].append({'label':name,'state':state,'pdf':str(path),'summary':d['stages'][index]['result'],'canonical':canonical,'visible':visible,'probe':str(evidence)})
 try:
  steps,dialogs,captures=start();capture(steps,captures,'loaded-dueling-17',17,'dueling','')
  choose(steps,dialogs,['Champion','Additional Fighting Style','Superior Technique']);capture(steps,captures,'superior-17',17,'superior technique','')
  choose(steps,dialogs,['Bonus Battle Master Maneuver (selected 0 of 1)','Disarming Attack']);capture(steps,captures,'disarming-17',17,'superior technique','disarming attack')
  steps.extend([{'op':'user-edit','field':'Limited Feature Used 4','value':'1'},{'op':'advance','ms':1000}]);capture(steps,captures,'spent-17',17,'superior technique','disarming attack','1');spent=save(steps,'native-spent17');run('creation',source,steps,dialogs,captures)
  steps,dialogs,captures=start();capture(steps,captures,'cold-spent-17',17,'superior technique','disarming attack','1');call(steps,"resetLimFeaUsed('short rest')");capture(steps,captures,'short-reset-17',17,'superior technique','disarming attack')
  choose(steps,dialogs,['Bonus Battle Master Maneuver (selected 1 of 1)','Disarming Attack'],ack=False);capture(steps,captures,'maneuver-removed-17',17,'superior technique','')
  choose(steps,dialogs,['Bonus Battle Master Maneuver (selected 0 of 1)','Riposte']);capture(steps,captures,'riposte-17',17,'superior technique','riposte')
  call(steps,"ApplyClasses('Fighter (Champion) 9',false)");dialogs.append({'title':'CHANGES ALERT DIALOG','result':'ok'});capture(steps,captures,'removed-9',9,'','');removed=save(steps,'native-removed9');run('spent-reopen',spent,steps,dialogs,captures)
  steps,dialogs,captures=start();capture(steps,captures,'cold-removed-9',9,'','');call(steps,"ApplyClasses('Fighter (Champion) 17',false)");dialogs.append({'title':'CHANGES ALERT DIALOG','result':'ok'});capture(steps,captures,'restored-empty-17',17,'','')
  choose(steps,dialogs,['Champion','Additional Fighting Style','Superior Technique'],ack=False);capture(steps,captures,'restored-superior-17',17,'superior technique','');choose(steps,dialogs,['Bonus Battle Master Maneuver (selected 0 of 1)','Disarming Attack']);capture(steps,captures,'reselected-disarming-17',17,'superior technique','disarming attack');final=save(steps,'native-final17');run('removed-reopen',removed,steps,dialogs,captures)
  assert hashlib.sha256(source.read_bytes()).hexdigest()==report['input_sha256'];report.update(passed=True,pdf=str(final),spent_pdf=str(spent),removed_pdf=str(removed))
 except Exception as e:report['error']=str(e);raise
 finally:(folder/'superior.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'superior.json',flush=True)

if __name__=='__main__':main()
