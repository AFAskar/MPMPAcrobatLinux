#!/usr/bin/env python3
"""Serialize real Reader roundtrips for each independently validated generated output."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 source=Path(sys.argv[1]).resolve();data=json.loads(source.read_text());assert data['passed'];folder=source.parent/('acrobat-'+str(time.time_ns()));folder.mkdir();report={'passed':False,'cases':[]}
 try:
  for case in data['cases']:
   label=case['workflow']+'-'+case['ruleset'];log=folder/(label+'-acrobat.log')
   with log.open('w') as out:result=subprocess.run([sys.executable,str(ROOT/'tools/native/verify-acrobat.py'),'--expected',json.dumps(case['expected']),case['output']],cwd=ROOT,stdout=out,stderr=out)
   lines=log.read_text().strip().splitlines();path=Path(lines[-1]) if lines else None
   oracle=json.loads(path.read_text()) if path and path.exists() else {'passed':False,'error':log.read_text()}
   report['cases'].append({'workflow':case['workflow'],'ruleset':case['ruleset'],'passed':result.returncode==0 and oracle['passed'],'report':str(path)})
   (folder/'generated-acrobat.json').write_text(json.dumps(report,indent=2))
   print(label,'Acrobat', 'PASS' if report['cases'][-1]['passed'] else 'FAIL',flush=True)
   assert report['cases'][-1]['passed'],oracle
  report['passed']=True
 finally:(folder/'generated-acrobat.json').write_text(json.dumps(report,indent=2));print(folder/'generated-acrobat.json',flush=True)
if __name__=='__main__':main()
