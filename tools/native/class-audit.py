#!/usr/bin/env python3
"""Audit source-defined class progression; never equate this probe with complete table usage."""
import argparse, hashlib, json, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fixture',choices=['2014','2024','ashnar'],action='append');args=parser.parse_args()
 folder=ROOT/'output/testing'/('native-class-audit-'+str(time.time_ns()));folder.mkdir(parents=True)
 report={'passed':False,'full_mpmb_compatibility':False,'scope':'Source-derived base classes at levels 1,3,5,11,17,20, using original class parser, application-context commands and calculations. Subclass choices, spells, resource usage, multiclass combinations and PDF roundtrips require separate evidence. Excluded/ambiguous classes are explicit coverage gaps.','fixtures':[]};print(folder,flush=True)
 def run(pdf,spec,label):
  scenario=folder/(label+'-scenario.json');evidence=folder/(label+'-report.json');scenario.write_text(json.dumps(spec))
  with (folder/(label+'.log')).open('w') as log:
   try:proc=subprocess.run([str(ROOT/'target/debug/mpmb-reader'),str(pdf),'--probe',str(scenario),str(evidence)],cwd=ROOT,stdout=log,stderr=log,timeout=240)
   except subprocess.TimeoutExpired:return 124,{'passed':False,'error':'Probe timed out; inspect '+str(folder/(label+'.log'))},str(evidence)
  data=json.loads(evidence.read_text()) if evidence.exists() else {'passed':False,'error':'No probe report'}
  return proc.returncode,data,str(evidence)
 try:
  for fixture in args.fixture or ['2014','2024','ashnar']:
   pattern='Ashnar*.pdf' if fixture=='ashnar' else '*_'+fixture+'_*.pdf';source=next((ROOT/'Testing').glob(pattern));original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
   inventory_code="Object.keys(ClassList).map(k=>({key:k,name:ClassList[k].name,parsed:ParseClass(ClassList[k].name),subclasses:(ClassList[k].subclasses||[])[1]||[]}))"
   _,data,evidence=run(source,{'dialogs':[{'result':'ok'}]*20,'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':inventory_code}]},fixture+'-inventory')
   assert data['passed'],data.get('error');inventory=data['stages'][-1]['result'];item={'fixture':fixture,'inventory':evidence,'cases':[],'excluded_or_ambiguous':[]};report['fixtures'].append(item)
   for index,cl in enumerate(inventory):
    if not cl['parsed'] or cl['parsed'][0]!=cl['key']:
     item['excluded_or_ambiguous'].append({'key':cl['key'],'reason':'Original parser does not select this key from its name with current source selections','parsed':cl['parsed']});continue
    steps=[{'op':'advance','ms':4100}]
    for ability in ['Str','Dex','Con','Int','Wis','Cha']:steps.append({'op':'edit','field':ability,'value':'18'})
    steps += [{'op':'eval','code':"__host.command(\"ApplyClasses('',false)\")"},{'op':'advance','ms':1000}]
    for level in [1,3,5,11,17,20]:
     command='ApplyClasses('+json.dumps(cl['name']+' '+str(level))+',false)'
     steps += [{'op':'eval','code':'__host.command('+json.dumps(command)+')'},{'op':'advance','ms':1000},{'op':'eval','code':"if(!classes.known["+json.dumps(cl['key'])+"]||classes.known["+json.dumps(cl['key'])+"].level!=="+str(level)+")throw Error('Original parser did not apply requested class/level');({level:What('Character Level'),proficiency:What('Proficiency Bonus'),known:classes.known["+json.dumps(cl['key'])+"].level})"},{'op':'assert','values':{'Character Level':str(level),'Proficiency Bonus':str(2+(level-1)//4)}}]
    rc,data,evidence=run(source,{'dialogs':[{'result':'ok'}]*500,'alerts':[1]*500,'steps':steps},fixture+'-'+str(index))
    case={'key':cl['key'],'passed':rc==0 and data.get('passed',False),'probe':evidence,'error':data.get('error'),'gaps':data.get('diagnostics',{}).get('gaps',[])};item['cases'].append(case);print(fixture,cl['key'],'PASS' if case['passed'] else 'FAIL',case['error'] or '',flush=True)
    (folder/'classes.json').write_text(json.dumps(report,indent=2))
   assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
  report['passed']=bool(report['fixtures']) and all(f['cases'] and all(c['passed'] for c in f['cases']) for f in report['fixtures'])
 finally:(folder/'classes.json').write_text(json.dumps(report,indent=2));print(folder/'classes.json',flush=True)
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
