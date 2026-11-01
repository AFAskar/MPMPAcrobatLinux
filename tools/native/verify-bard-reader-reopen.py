#!/usr/bin/env python3
"""Fresh native reopen and further ability edit of a Reader-saved Bard1.

Exact selected character/resource/widget values, retained instruments and
original scripts are checked; no appearance fidelity or complete Bard claim.
"""
import argparse,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect,script_hashes

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader-edit',type=Path,required=True);a=p.parse_args();r=json.loads(a.reader_edit.read_text());assert r['passed'] and r['phase']=='edit';state=r['captured']['states'][-1];expected=state['fields'];row=state['resource']['row'];source=a.reader_edit.parent/'reader.pdf';before=hashlib.sha256(source.read_bytes()).hexdigest();folder=ROOT/'output/testing'/('bard-reader-native-reopen-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary);report={'passed':False,'scope':__doc__,'reader':str(a.reader_edit),'source_sha256':before,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()};names=list(expected);read="(function(){var o={};"+json.dumps(names)+".forEach(function(n){o[n]=getField(n).valueAsString});return o})()";output=folder/'native.pdf'
 plan={'dialogs':[],'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'assert','values':expected},{'op':'eval','code':read},{'op':'edit','field':'Cha','value':'12'},{'op':'advance','ms':1000},{'op':'assert','values':{'Cha Mod':'1','Limited Feature Max Usages '+str(row):'1','Tool 1':'Flute','Tool 2':'Lute','Tool 3':'Drum'}},{'op':'eval','code':read},{'op':'save','path':str(output)}]};scenario=folder/'scenario.json';scenario.write_text(json.dumps(plan))
 try:
  with (folder/'probe.log').open('w') as log:proc=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(folder/'probe.json')],stdout=log,stderr=log,timeout=300)
  data=json.loads((folder/'probe.json').read_text());assert proc.returncode==0 and data['passed'] and not data['diagnostics']['errors'],data.get('error') or data['diagnostics']['errors'];assert data['stages'][2]['result']==expected;after=data['stages'][-2]['result'];independent=inspect(output,after);assert independent['actual']==after and independent['widgets'] and all(w['matches'] for w in independent['widgets']);assert script_hashes(output)==script_hashes(source);assert hashlib.sha256(source.read_bytes()).hexdigest()==before;report.update(passed=True,loaded=expected,edited=after,independent=independent)
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'reopen.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'reopen.json',flush=True)
if __name__=='__main__':main()
