#!/usr/bin/env python3
"""Two genuine Champion fighting-style slots, conditional effects and level removal.

2014 previously qualified Fighter17 input. Source feature key is discovered from
its actual definition, not its display name. Other styles/classes/ASIs stay open.
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
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--install-observer-once',action='store_true');a=p.parse_args();source=a.input.resolve()
 profile=module('profile','fighter-styles.py');style=module('style','default-style-persistence.py');fields=module('fields','field-state-comparison.py')
 observer=(ROOT/'tools/native/fighter-additional-observer.js').read_text();folder=ROOT/'output/testing'/('native-fighter-additional-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
 binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
 report={'passed':False,'scope':__doc__,'input':str(source),'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'observer_sha256':hashlib.sha256(observer.encode()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'phases':[],'full_class_coverage':False}
 report['diagnostic_mode']=diagnostics.MODE if a.install_observer_once else 'repeated-RunUserScript'
 report['diagnostic_helper_sha256']=hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()
 report['test_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 def script(text):
  if a.install_observer_once:
   if text==observer:return {'op':'eval','code':diagnostics.native_request()}
   if text==profile.SETUP:text=diagnostics.install(text,observer)
  return {'op':'eval','code':"Value('User Script',"+json.dumps(text)+");__host.command('RunUserScript(false)')"}
 def run(label,pdf,steps,dialogs,captures):
  scenario=folder/(label+'-scenario.json');evidence=folder/(label+'-probe.json');scenario.write_text(json.dumps({'steps':steps,'dialogs':dialogs,'alerts':[1]*100}))
  with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(pdf),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=480,env=dict(os.environ,MPMB_DIALOG_TRACE_DIR=str(folder/(label+'-dialogs'))))
  data=json.loads(evidence.read_text());assert proc.returncode==0 and data['passed'],data.get('error');assert not data['diagnostics']['errors'] and not data['diagnostics']['console']['messages']
  if a.install_observer_once:
   markers=[stage['result'] for stage in data['stages'] if isinstance(stage.get('result'),str) and stage['result'].startswith(diagnostics.DONE)]
   assert markers==[diagnostics.DONE+str(i+1) for i in range(len(captures))],('Missing/repeated actual observer executions',markers,len(captures))
   report.setdefault('timer_requests',[]).append({'probe':str(evidence),'markers':markers})
  for name,index,diagnostic,expected in captures:
   state=style.saved_capture(diagnostic,data['stages'][index]['result'],pdf);assert not state['errors'] and len(state['resources'])==64
   assert state['identity']['subclass']=='fighter-champion' and state['additionalDefinition']=={'key':'subclassfeature10','name':'Additional Fighting Style','minlevel':10}
   for key,value in expected.items():
    actual=state['fields'].get(key) if key in state['fields'] else state.get(key)
    assert actual==value,(name,key,actual,value)
   assert state['additional'] in ('','defense','dueling')
   canonical=fields.compare(diagnostic,dict(state['fields'],**state['resources']));visible=inspect(diagnostic,{n:state['fields'][n] for n in ['AC','Attack.1.To Hit','Attack.1.Damage','Attack.1.Weapon']});assert visible['passed']
   assert script_hashes(diagnostic)==script_hashes(source)
   report['phases'].append({'label':name,'state':state,'pdf':str(diagnostic),'canonical':canonical,'visible':visible,'probe':str(evidence)})
  return data
 def capture(steps,captures,name,expected):
  steps.append(script(observer));index=len(steps);pdf=folder/(name+'-diagnostic.pdf');steps.extend([{'op':'eval','code':profile.SUMMARY},{'op':'save','path':str(pdf)}]);captures.append((name,index,pdf,expected))
 def edit(steps,n,v):steps.extend([{'op':'user-edit','field':n,'value':v},{'op':'advance','ms':1000}])
 def choose(steps,dialogs,branch,name):
  steps.extend([{'op':'eval','code':"__host.command('ClassFeatureOptions()')"},{'op':'advance','ms':1000}]);dialogs.append({'title':'MPMB menu','button_path':['Champion',branch,name]})
 try:
  steps=[{'op':'advance','ms':4100},script(profile.SETUP)];dialogs=[];captures=[]
  capture(steps,captures,'loaded-17',{'Character Level':'17','HP Max':'123','choice':'archery','additional':'','AC':'18','Attack.1.To Hit':'+12','Attack.1.Damage':'1d8+4'})
  choose(steps,dialogs,'Additional Fighting Style','Defense');capture(steps,captures,'extra-defense',{'choice':'archery','additional':'defense','AC':'19','Attack.1.To Hit':'+12'})
  edit(steps,'AC Armor Description','Unarmored');capture(steps,captures,'extra-defense-unarmored',{'additional':'defense','AC':'14','Attack.1.To Hit':'+12'})
  edit(steps,'AC Armor Description','Plate');capture(steps,captures,'extra-defense-restored',{'additional':'defense','AC':'19','Attack.1.To Hit':'+12'})
  choose(steps,dialogs,'Additional Fighting Style','Dueling');dialogs.append({'title':'CHANGES ALERT DIALOG','result':'ok'});capture(steps,captures,'extra-dueling-bow',{'choice':'archery','additional':'dueling','AC':'18','Attack.1.To Hit':'+12','Attack.1.Damage':'1d8+4'})
  edit(steps,'AC Shield Bonus Description','Shield');edit(steps,'Attack.1.Weapon Selection','Longsword');capture(steps,captures,'extra-dueling-sword',{'choice':'archery','additional':'dueling','AC':'20','Attack.1.To Hit':'+10','Attack.1.Damage':'1d8+6'})
  choose(steps,dialogs,'Fighting Style','Defense');dialogs.append({'title':'CHANGES ALERT DIALOG','result':'ok'});capture(steps,captures,'primary-defense-extra-dueling',{'choice':'defense','additional':'dueling','AC':'21','Attack.1.To Hit':'+10','Attack.1.Damage':'1d8+6'})
  choose(steps,dialogs,'Fighting Style','Archery');dialogs.append({'title':'CHANGES ALERT DIALOG','result':'ok'});capture(steps,captures,'primary-archery-extra-dueling',{'choice':'archery','additional':'dueling','AC':'20','Attack.1.To Hit':'+10','Attack.1.Damage':'1d8+6'})
  steps.extend([{'op':'eval','code':"__host.command(\"ApplyClasses('Fighter (Champion) 9',false)\")"},{'op':'advance','ms':1000}]);dialogs.extend([{'result':'ok'}]*30)
  expected9={'Character Level':'9','HP Max':'67','choice':'archery','AC':'20','Attack.1.To Hit':'+8','Attack.1.Damage':'1d8+4'}
  capture(steps,captures,'reduced-9',expected9)
  lower=folder/'native-level9.pdf';steps.extend([{'op':'eval','code':"Value('User Script','');Value('PC Name','Champion additional style compatibility')"},{'op':'save','path':str(lower)}]);run('workflow',source,steps,dialogs,captures)
  steps=[{'op':'advance','ms':4100},script(profile.SETUP)];captures=[];capture(steps,captures,'cold-9',expected9)
  steps.extend([{'op':'eval','code':"__host.command(\"ApplyClasses('Fighter (Champion) 17',false)\")"},{'op':'advance','ms':1000}]);capture(steps,captures,'restored-17',{'Character Level':'17','HP Max':'123','choice':'archery','AC':'20','Attack.1.To Hit':'+10'})
  output=folder/'native-restored17.pdf';steps.extend([{'op':'eval','code':"Value('User Script','');Value('PC Name','Champion additional style compatibility')"},{'op':'save','path':str(output)}]);run('reopen',lower,steps,[{'result':'ok'}]*30,captures)
  final=report['phases'][-1]['state'];assert final['fields']['Attack.1.Damage']==('1d8+6' if final['additional']=='dueling' else '1d8+4')
  restored=output
  steps=[{'op':'advance','ms':4100},script(profile.SETUP)];dialogs=[];captures=[]
  choose(steps,dialogs,'Additional Fighting Style','Dueling');dialogs.extend([{'title':'CHANGES ALERT DIALOG','result':'ok'}]+[{'result':'ok'}]*20)
  capture(steps,captures,'reselected-extra-17',{'Character Level':'17','HP Max':'123','choice':'archery','additional':'dueling','AC':'20','Attack.1.To Hit':'+10','Attack.1.Damage':'1d8+6'})
  output=folder/'native-chosen17.pdf';steps.extend([{'op':'eval','code':"Value('User Script','');Value('PC Name','Champion additional style compatibility')"},{'op':'save','path':str(output)}]);run('reselect',restored,steps,dialogs,captures)
  assert hashlib.sha256(source.read_bytes()).hexdigest()==report['input_sha256'] and script_hashes(output)==script_hashes(source);report.update(passed=True,reduced_pdf=str(lower),restored_pdf=str(restored),pdf=str(output))
 except Exception as error:report['error']=str(error);raise
 finally:
  target=folder/'additional.json';target.write_text(json.dumps(report,indent=2)+'\n');print(target,flush=True)

if __name__=='__main__':main()
