#!/usr/bin/env python3
"""Observe an actual unsupported MPMB workflow in all three authorized PDFs."""
import json, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 folder=ROOT/'output/testing'/('mpmb-scope-audit-'+str(time.time_ns()));folder.mkdir(parents=True)
 result={'target':'All MPMB behavior in the three supplied PDFs; general Acrobat JavaScript is not the target.','full_mpmb_compatibility':False,'cases':[]}
 try:
  for label,pattern in [('2014','*_2014_*.pdf'),('2024','*_2024_*.pdf'),('ashnar','Ashnar*.pdf')]:
   source=next((ROOT/'Testing').glob(pattern));scenario=folder/(label+'-scenario.json');report=folder/(label+'-report.json')
   code="if(typeof tDoc.getPrintParams==='function'&&typeof tDoc.print==='function')throw Error('Print dependency now implemented; controlled printer validation required');__host.command(\"Value('Print Remember','false!#TheListSeparator#!0');PrintTheSheet()\")"
   scenario.write_text(json.dumps({'dialogs':[{'result':'ok'}]*10,'alerts':[1]*10,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':"({getPrintParams:typeof tDoc.getPrintParams,print:typeof tDoc.print})"},{'op':'eval','code':code}]}))
   with (folder/(label+'.log')).open('w') as out:proc=subprocess.run([str(ROOT/'target/debug/mpmb-reader'),str(source),'--probe',str(scenario),str(report)],stdout=out,stderr=out,timeout=120)
   data=json.loads(report.read_text());interfaces=data['stages'][1]['result'];observed=proc.returncode!=0 and not data['passed'] and 'PrintTheSheet' in data.get('error','') and interfaces['getPrintParams']=='undefined'
   case={'fixture':label,'workflow':'Original PrintTheSheet','compatible':False,'failure_observed':observed,'interfaces':interfaces,'probe':str(report)};result['cases'].append(case)
   assert observed,{'unexpected_probe_result':str(report)}
   print(label,'original MPMB print: UNSUPPORTED',flush=True)
 finally:(folder/'scope.json').write_text(json.dumps(result,indent=2));print(folder/'scope.json',flush=True)
if __name__=='__main__':main()
