#!/usr/bin/env python3
"""Open both actual native reader/class-dialog windows and retain frame captures."""
import json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 folder=ROOT/'output/testing'/('native-desktop-'+str(time.time_ns()));folder.mkdir(parents=True)
 report={'passed':False,'cases':[]}
 try:
  for rule in ['2014','2024']:
   pdf=next((ROOT/'Testing').glob('*_'+rule+'_*.pdf'));case=folder/rule
   with (folder/(rule+'.log')).open('w') as log:proc=subprocess.run([str(ROOT/'target/debug/mpmb-reader'),str(pdf),'--desktop-smoke',str(case)],cwd=ROOT,stdout=log,stderr=log,timeout=120)
   data=json.loads((case/'desktop-result.json').read_text());assert proc.returncode==0 and data['passed'],data
   assert (case/'reader.png').exists() and (case/'class-dialog.png').exists()
   report['cases'].append({'ruleset':rule,'passed':True,'report':str(case/'desktop-result.json')});print(rule,'native desktop PASS',flush=True)
  report['passed']=True
 finally:(folder/'desktop.json').write_text(json.dumps(report,indent=2));print(folder/'desktop.json',flush=True)
if __name__=='__main__':main()
