#!/usr/bin/env python3
"""Fresh native reopen/edit qualification for every native/Reader Bard phase.

Covers selected original class/resource/slot/feature fields and instrument
retention; preserves all comparison representations and original scripts.
"""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields,inspect,script_hashes
from pypdf import PdfReader
spec=importlib.util.spec_from_file_location('field_state',ROOT/'tools/native/field-state-comparison.py');field_state=importlib.util.module_from_spec(spec);spec.loader.exec_module(field_state)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--native-comparison',type=Path,required=True);a=p.parse_args();r=json.loads(a.reader.read_text());n=json.loads(a.native_comparison.read_text());assert r['passed'] and n['passed'];folder=ROOT/'output/testing'/('bard-progression-reopens-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary);report={'passed':False,'scope':__doc__,'reader':str(a.reader),'native_comparison':str(a.native_comparison),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':[]}
 try:
  for phase,comparison in zip(r['phases'],n['phases']):
   expected=phase['fields'];names=list(expected);read="(function(){var o={};"+json.dumps(names)+".forEach(function(n){o[n]=getField(n).valueAsString});return o})()"
   for engine,source in [('reader',Path(phase['pdf'])),('native',Path(comparison['native_pdf']))]:
    before=hashlib.sha256(source.read_bytes()).hexdigest();label=phase['label']+'-'+engine;output=folder/(label+'.pdf');scenario=folder/(label+'.json');evidence=folder/(label+'-probe.json');scenario.write_text(json.dumps({'dialogs':[],'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':read},{'op':'edit','field':'Cha','value':'18'},{'op':'advance','ms':1000},{'op':'eval','code':read},{'op':'save','path':str(output)}]}))
    with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=300)
    data=json.loads(evidence.read_text());assert proc.returncode==0 and data['passed'] and not data['diagnostics']['errors'],data.get('error') or data['diagnostics']['errors'];loaded=data['stages'][1]['result'];edited=data['stages'][-2]['result'];assert loaded==expected,('Fresh loaded state differs',label);assert edited['Cha']=='18' and edited['Cha Mod']=='4';row=r['resource_row'];maximum='Limited Feature Max Usages '+str(row)
    if phase['label']=='removed':
     assert edited[maximum]=='' and edited['Limited Feature '+str(row)]=='';fields=canonical_fields(PdfReader(output));node=PdfReader(output).get_object(fields[maximum]['reference']);assert '/C' not in node.get('/AA',{})
     checked=inspect(output,{maximum:'','Limited Feature '+str(row):''});assert all(not w['appearance'] or not w['appearance_text'].strip() for w in checked['widgets'] if w['visible']),'Removed resource still visibly present'
    else:assert edited[maximum]=='4' and [edited['Tool '+str(i)] for i in [1,2,3]]==['Flute','Lute','Drum']
    raw=field_state.compare(output,edited);assert script_hashes(output)==script_hashes(source);assert hashlib.sha256(source.read_bytes()).hexdigest()==before;report['cases'].append({'label':label,'source':str(source),'source_sha256':before,'loaded_equal':True,'edited':edited,'api_raw_comparison':raw,'output':str(output)});print(label,'PASS',flush=True)
  report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'reopens.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'reopens.json',flush=True)
if __name__=='__main__':main()
