#!/usr/bin/env python3
"""Exercise original hide/reveal and generated-page removal against both fixtures."""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect,script_hashes

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--fixture',choices=['2014','2024'],action='append')
 parser.add_argument('--binary',type=Path,default=ROOT/'target/debug/mpmb-reader')
 args=parser.parse_args();binary=args.binary.resolve();binary_hash=hashlib.sha256(binary.read_bytes()).hexdigest()
 folder=ROOT/'output/testing'/('native-lifecycle-'+str(time.time_ns()));folder.mkdir(parents=True);report={'passed':False,'cases':[],'binary':str(binary),'binary_sha256':binary_hash,'selected_fixtures':args.fixture or ['2014','2024']}
 def run(pdf,spec,label):
  scenario=folder/(label+'-scenario.json');evidence=folder/(label+'-report.json');scenario.write_text(json.dumps(spec))
  with (folder/(label+'.log')).open('w') as out:result=subprocess.run([str(binary),str(pdf),'--probe',str(scenario),str(evidence)],stdout=out,stderr=out,cwd=ROOT,timeout=360)
  data=json.loads(evidence.read_text());assert result.returncode==0 and data['passed'] and not data['diagnostics']['errors'] and not data['diagnostics']['console']['messages'],data
  return evidence
 try:
  for rule in report['selected_fixtures']:
   source=next((ROOT/'Testing').glob('*_'+rule+'_*.pdf'));saved=folder/('native-lifecycle-'+rule+'.pdf');expected={'PC Name':'Native Lifecycle','Str':'18','Str Mod':'4','Player Name':'Native action persisted'}
   code="""var before=numPages;DoTemplate('ASfront');if(numPages!==before-1)throw Error('Hide page failed');DoTemplate('ASfront');if(numPages!==before)throw Error('Reveal page failed');var prefix=DoTemplate('AScomp','Add',null,true);ApplyCompRace('wolf',prefix);DoTemplate('AScomp','Remove',prefix,true);if(numPages!==before||getField(prefix+'Comp.Race')!==null)throw Error('Companion removal failed');var finalPrefix=DoTemplate('AScomp','Add',null,true);ApplyCompRace('wolf',finalPrefix);"""
   probe=run(source,{'dialogs':[{'result':'ok'}],'alerts':[1]*8,'steps':[{'op':'advance','ms':4100},{'op':'edit','field':'PC Name','value':expected['PC Name']},{'op':'edit','field':'Str','value':'18'},{'op':'eval','code':'__host.command('+json.dumps(code)+')'},{'op':'eval','code':"var actionField=getField('Player Name');actionField.setAction('Calculate',\"event.value='Native action persisted'\");actionField.calcOrderIndex=0;calculateNow()"},{'op':'advance','ms':1000},{'op':'assert','values':expected},{'op':'save','path':str(saved)}]},rule)
   independent=inspect(saved,expected);assert independent['passed'],independent;assert script_hashes(source)==script_hashes(saved)
   original_origins=[str(page.get('/TemplateInstantiated','')) for page in PdfReader(source).pages]
   origins=[str(page.get('/TemplateInstantiated','')) for page in PdfReader(saved).pages]
   assert origins.count('/ASfront')==max(1,original_origins.count('/ASfront')),origins
   assert origins.count('/AScomp')==original_origins.count('/AScomp')+1,origins
   (folder/(rule+'-independent.json')).write_text(json.dumps(independent,indent=2))
   reopen=run(saved,{'alerts':[1]*4,'steps':[{'op':'advance','ms':4100},{'op':'assert','values':expected}]},rule+'-reopen')
   report['cases'].append({'ruleset':rule,'workflow':'lifecycle','passed':True,'output':str(saved),'expected':expected,'probe':str(probe),'reopen':str(reopen),'original_page_origins':original_origins,'spawned_page_origins':origins});print(rule,'lifecycle PASS',flush=True)
  assert hashlib.sha256(binary.read_bytes()).hexdigest()==binary_hash,'Runtime changed during qualification'
  report['passed']=True
 finally:(folder/'lifecycle.json').write_text(json.dumps(report,indent=2));print(folder/'lifecycle.json',flush=True)
if __name__=='__main__':main()
