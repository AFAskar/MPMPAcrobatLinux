#!/usr/bin/env python3
"""Imports and supplied Ashnar regression character. Generated workflows have a separate suite."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from pypdf import PdfReader
from verify import canonical_fields,script_hashes,inspect

def main():
 folder=ROOT/'output/testing'/('native-extended-'+str(time.time_ns()));folder.mkdir(parents=True);report={'passed':False,'workflows':{}}
 def run(pdf,scenario,label,expected_failure=False):
  spec=folder/(label+'-scenario.json');evidence=folder/(label+'-report.json');spec.write_text(json.dumps(scenario))
  with (folder/(label+'.log')).open('w') as out:proc=subprocess.run([str(ROOT/'target/debug/mpmb-reader'),str(pdf),'--probe',str(spec),str(evidence)],cwd=ROOT,stdout=out,stderr=out,timeout=300)
  data=json.loads(evidence.read_text());assert (proc.returncode!=0) if expected_failure else (proc.returncode==0 and data['passed'] and not data['diagnostics']['errors']),(label,data)
  return data,evidence
 try:
  blank=next((ROOT/'Testing').glob('*_2024_*.pdf'));sentinel=ROOT/'Testing/addons/readiness-sentinel.js';saved=folder/'native-import-2024.pdf'
  imports={'dialogs':[{'result':'ok'}],'alerts':[1,1],'steps':[{'op':'advance','ms':4100},{'op':'eval','code':'ImportUserScriptFile('+json.dumps(str(sentinel))+');RunUserScript(false,false)'},{'op':'assert','values':{'Player Name':'MPMB add-on executed'}},{'op':'save','path':str(saved)}]}
  _,e=run(blank,imports,'import');verify=inspect(saved,{'Player Name':'MPMB add-on executed'});assert verify['passed'];assert script_hashes(blank)==script_hashes(saved)
  _,reopened=run(saved,{'alerts':[1,1],'steps':[{'op':'advance','ms':4100},{'op':'assert','values':{'Player Name':'MPMB add-on executed'}},{'op':'eval','code':"if(!WeaponsList['mpmb readiness blade'])throw Error('Imported weapon definition missing');"}]},'import-reopen')
  report['workflows']['imports']={'passed':True,'probe':str(e),'reopen':str(reopened),'output':str(saved)};print('Original file import, execution, persistence and native reopen PASS',flush=True)
  original=ROOT/'Testing/Ashnar_TestingCharacter_.pdf';saved=folder/'native-ashnar.pdf';fields=canonical_fields(PdfReader(original));expected={k:fields[k]['/V'] for k in ['PC Name','Str','Str Mod','Character Level']}
  _,e=run(original,{'alerts':[1,1],'dialogs':[{'result':'cancel'}],'steps':[{'op':'advance','ms':4100},{'op':'assert','values':expected},{'op':'eval','code':"__host.invokeMenu('ClassesButton')"},{'op':'save','path':str(saved)}]},'ashnar')
  saved_fields=canonical_fields(PdfReader(saved));key='User_Imported_Files.Stringified';assert fields[key]['/V']==saved_fields[key]['/V'];remembered=[k for k in fields if 'spells.remember.' in k];assert all(fields[k]['/V']==saved_fields[k]['/V'] for k in remembered);assert script_hashes(original)==script_hashes(saved)
  verify=inspect(saved,expected);assert verify['passed'];(folder/'ashnar-independent.json').write_text(json.dumps(verify,indent=2))
  _,reopened=run(saved,{'alerts':[1,1],'steps':[{'op':'advance','ms':4100},{'op':'assert','values':expected}]},'ashnar-reopen')
  report['workflows']['ashnar']={'passed':True,'probe':str(e),'reopen':str(reopened),'output':str(saved),'imported_payload_preserved':True,'remembered_spell_fields_preserved':len(remembered)};print('Ashnar original imports, initialization, dialog cancellation, save/reopen and retained spell state PASS',flush=True)
  report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'extended.json').write_text(json.dumps(report,indent=2));print(folder/'extended.json',flush=True)
if __name__=='__main__':main()
