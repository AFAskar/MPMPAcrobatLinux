#!/usr/bin/env python3
"""Native/Reader Bard Lore progression with saved-state and displayed totals.

Keeps original class/field actions. ASI, expertise choices and spell selection
are separate gaps; exact selected fields and actual skill displays are checked.
"""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect,script_hashes
spec=importlib.util.spec_from_file_location('field_state',ROOT/'tools/native/field-state-comparison.py');field_state=importlib.util.module_from_spec(spec);spec.loader.exec_module(field_state)

def displays(pdf):
 result={}
 for name in ['Acr','Arc']:
  data=inspect(pdf,{name:''});visible=[w for w in data['widgets'] if w['visible']];assert visible and all(w['appearance'] for w in visible);result[name]=[w['appearance_text'] for w in visible]
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);a=p.parse_args();reference=json.loads(a.reader.read_text());assert reference['passed'];source=Path(reference['input']);assert hashlib.sha256(source.read_bytes()).hexdigest()==reference['input_sha256'];folder=ROOT/'output/testing'/('bard-progression-comparison-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary);report={'passed':False,'scope':__doc__,'reader':str(a.reader),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'phases':[]}
 names=reference['names'];read="(function(){var o={};"+json.dumps(names)+".forEach(function(n){o[n]=getField(n).valueAsString});return o})()";steps=[{'op':'advance','ms':4100}]+[{'op':'edit','field':n,'value':v} for n,v in {'Str':'10','Dex':'14','Con':'12','Int':'12','Wis':'13'}.items()];indices=[];outputs=[]
 def capture(label):
  steps.append({'op':'advance','ms':1000});indices.append(len(steps));steps.append({'op':'eval','code':read});output=folder/(label+'.pdf');outputs.append(output);steps.append({'op':'save','path':str(output)})
 capture('level1');steps.append({'op':'eval','code':"__host.command(\"ApplyClasses('Bard (College of Lore) 5',false)\")"});capture('lore5');steps+=[{'op':'edit','field':'Limited Feature Used '+str(reference['resource_row']),'value':'1'},{'op':'eval','code':"__host.command(\"resetLimFeaUsed('short rest')\")"}];capture('short-rest5');steps.append({'op':'eval','code':"__host.command(\"ApplyClasses('Bard 1',false)\")"});capture('level1-again');steps.append({'op':'eval','code':"__host.command(\"ApplyClasses('',false)\")"});capture('removed');scenario=folder/'scenario.json';scenario.write_text(json.dumps({'dialogs':[{'title':'CHANGES ALERT DIALOG','result':'ok'}]*10,'alerts':[1]*20,'steps':steps}))
 try:
  with (folder/'probe.log').open('w') as log:proc=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(folder/'probe.json')],stdout=log,stderr=log,timeout=420)
  data=json.loads((folder/'probe.json').read_text());assert proc.returncode==0 and data['passed'] and not data['diagnostics']['errors'],data.get('error') or data['diagnostics']['errors']
  for index,output,phase in zip(indices,outputs,reference['phases']):
   actual=data['stages'][index]['result'];same=actual==phase['fields'];differences={k:{'native':actual.get(k),'reader':phase['fields'].get(k)} for k in set(actual)|set(phase['fields']) if actual.get(k)!=phase['fields'].get(k)};native_display=displays(output);reader_display=displays(Path(phase['pdf']));record={'label':phase['label'],'canonical_equal':same,'differences':differences,'native_pdf':str(output),'native_display':native_display,'reader_display':reader_display,'display_equal':native_display==reader_display};report['phases'].append(record)
   record['api_raw_comparison']=field_state.compare(output,actual);assert script_hashes(output)==script_hashes(source);assert same,'Class-derived canonical fields differ';assert native_display==reader_display,'Original displayed skill totals differ'
  report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'comparison.json',flush=True)
if __name__=='__main__':main()
