#!/usr/bin/env python3
"""Changed superiority-die saves and fresh native restores from both origins.

Requires the full paired13-state profile. This covers the one-die counter and
retained maneuver/notes, not every fighting style or class.
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
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--reader',type=Path,required=True);a=p.parse_args();native=json.loads(a.native.read_text());reader=json.loads(a.reader.read_text());assert native['passed'] and reader['passed']
 wanted={v['label']:v['state'] for v in native['phases']};assert len(wanted)==13 and wanted=={v['label']:v['state'] for v in reader['phases']};observer=(ROOT/'tools/native/fighter-superior-observer.js').read_text();assert native['observer_sha256']==reader['observer_sha256']==hashlib.sha256(observer.encode()).hexdigest();assert native['diagnostic_helper_sha256']==reader['diagnostic_helper_sha256']==hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()
 folder=ROOT/'output/testing'/('fighter-superior-persistence-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary);assert hashlib.sha256(binary.read_bytes()).hexdigest()==native['binary_sha256'],'Require the qualified native binary'
 profile=module('profile','fighter-styles.py');style=module('style','default-style-persistence.py');fields=module('fields','field-state-comparison.py');report={'passed':False,'scope':__doc__,'native':str(a.native.resolve()),'reader':str(a.reader.resolve()),'binary_sha256':native['binary_sha256'],'cases':[]}
 def run(source,label,before,used):
  source_hash=hashlib.sha256(source.read_bytes()).hexdigest();after=json.loads(json.dumps(before));after['resources']['Limited Feature Used 4']=used;assert before['resources']['Limited Feature 4']=='Combat Superiority (d6)'
  setup=diagnostics.install(profile.SETUP,observer);steps=[{'op':'advance','ms':4100},{'op':'eval','code':"Value('User Script',"+json.dumps(setup)+");__host.command('RunUserScript(false)')"}];captures=[]
  def capture(state):
   steps.append({'op':'eval','code':diagnostics.native_request()});index=len(steps);pdf=folder/(label+'-'+str(len(captures))+'-diagnostic.pdf');steps.extend([{'op':'eval','code':profile.SUMMARY},{'op':'save','path':str(pdf)}]);captures.append((state,index,pdf))
  capture(before);steps.extend([{'op':'user-edit','field':'Limited Feature Used 4','value':used},{'op':'advance','ms':1000}]);capture(after);output=folder/(label+'.pdf');steps.extend([{'op':'eval','code':"Value('User Script','');Value('PC Name','Champion Superior Technique compatibility')"},{'op':'save','path':str(output)}]);scenario=folder/(label+'-scenario.json');evidence=folder/(label+'-probe.json');scenario.write_text(json.dumps({'steps':steps}))
  with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=480,env=dict(os.environ,MPMB_DIALOG_TRACE_DIR=str(folder/(label+'-dialogs'))))
  d=json.loads(evidence.read_text());assert proc.returncode==0 and d['passed'] and not d['diagnostics']['errors'] and not d['diagnostics']['console']['messages'],d.get('error');assert [s['result'] for s in d['stages'] if isinstance(s.get('result'),str) and s['result'].startswith(diagnostics.DONE)]==[diagnostics.DONE+'1',diagnostics.DONE+'2'];case={'label':label,'input':str(source),'input_sha256':source_hash,'probe':str(evidence),'output':str(output),'states':[]}
  for expected,index,pdf in captures:
   state=style.saved_capture(pdf,d['stages'][index]['result'],source);assert state==expected and not state['errors'];values=dict(state['fields'],**state['resources'],**state['reactions']);values.update({'Class Features':state['featureText'],'Extra.Notes':state['notesText']});canonical=fields.compare(pdf,values);visible=inspect(pdf,{n:v for n,v in state['resources'].items() if v});assert visible['passed'] and script_hashes(pdf)==script_hashes(source);case['states'].append({'pdf':str(pdf),'state':state,'canonical':canonical,'visible':visible})
  assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash;report['cases'].append(case);return output,after
 try:
  for engine,data in [('native',native),('reader',reader)]:
   for kind,key,state in [('spent','spent_pdf' if engine=='native' else 'spent17_pdf',wanted['spent-17']),('final','pdf',wanted['reselected-disarming-17'])]:
    original=state['resources']['Limited Feature Used 4'];used='' if original=='1' else '1';changed,new=run(Path(data[key]),engine+'-'+kind+'-changed',state,used);run(changed,engine+'-'+kind+'-cold-restored',new,original)
  report['passed']=True
 except Exception as e:report['error']=str(e);raise
 finally:(folder/'persistence.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'persistence.json',flush=True)

if __name__=='__main__':main()
