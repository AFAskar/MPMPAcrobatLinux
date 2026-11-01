#!/usr/bin/env python3
"""Compare native Bard actions with real Reader actions after each ready boundary.

Includes genuine instrument inputs and original field actions; it does not
qualify all Bard subclass/spell/feat choices or appearance fidelity.
"""
import argparse,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields,inspect,script_hashes

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--dialogs',type=Path,default=ROOT/'tools/native/profiles/bard-instruments-2024.json');a=p.parse_args();r=json.loads(a.reader.read_text());assert r['passed'] and r['phase']=='create';source=Path(r['input']);assert hashlib.sha256(source.read_bytes()).hexdigest()==r['input_sha256'];script=Path(r['observer']).read_text();assert hashlib.sha256(script.encode()).hexdigest()==r['observer_sha256'];folder=ROOT/'output/testing'/('bard-ready-comparison-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
 report={'passed':False,'scope':__doc__,'reader':str(a.reader),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'native_dialog_profile':str(a.dialogs),'native_dialog_profile_sha256':hashlib.sha256(a.dialogs.read_bytes()).hexdigest()}
 names=list(r['ready_states'][0]['fields']);read="(function(){var o={};"+json.dumps(names)+".forEach(function(n){o[n]=getField(n).valueAsString});return o})()";row=r['resource_row'];steps=[{'op':'advance','ms':4100},{'op':'eval','code':"Value('User Script',"+json.dumps(script)+")"},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'eval','code':"JSON.parse(getField('PC Name').valueAsString)"},{'op':'advance','ms':1000},{'op':'eval','code':read},{'op':'edit','field':'Cha','value':'10'},{'op':'advance','ms':1000},{'op':'eval','code':read},{'op':'edit','field':'Limited Feature Used '+str(row),'value':'1'},{'op':'eval','code':"__host.command(\"resetLimFeaUsed('short rest')\")"},{'op':'advance','ms':1000},{'op':'eval','code':read},{'op':'eval','code':"__host.command(\"resetLimFeaUsed('long rest')\")"},{'op':'advance','ms':1000},{'op':'eval','code':read},{'op':'edit','field':'Cha','value':'20'},{'op':'advance','ms':1000},{'op':'eval','code':read},{'op':'save','path':str(folder/'native.pdf')}]
 def probe(label,pdf,steps,dialogs):
  plan=folder/(label+'.json');evidence=folder/(label+'-probe.json');plan.write_text(json.dumps({'dialogs':dialogs,'alerts':[1]*20,'steps':steps}))
  with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(pdf),'--probe',str(plan),str(evidence)],stdout=log,stderr=log,timeout=300)
  result=json.loads(evidence.read_text());assert proc.returncode==0 and result['passed'] and not result['diagnostics']['errors'],result.get('error') or result['diagnostics']['errors'];return result
 try:
  data=probe('create',source,steps,json.loads(a.dialogs.read_text()));script_capture=data['stages'][3]['result'];script_capture.pop('sentinel');assert script_capture==r['captured'],'Immediate class-submit state differs';actual=[data['stages'][i]['result'] for i in [5,8,12,15,18]];expected=[s['fields'] for s in r['ready_states']];assert actual==expected,'Native ready user-action states differ';report['ready_states_equal']=True;report['states']=actual
  for label,pdf in [('native',folder/'native.pdf'),('reader',a.reader.parent/'reader.pdf')]:
   checked=inspect(pdf,expected[-1]);assert checked['actual']==expected[-1] and checked['widgets'] and all(w['matches'] for w in checked['widgets']);assert script_hashes(pdf)==script_hashes(source);report[label+'_canonical_widgets_scripts']=True
  output=folder/'native-reopened-edited.pdf';reopened=probe('reopened-edit',folder/'native.pdf',[{'op':'advance','ms':4100},{'op':'eval','code':read},{'op':'edit','field':'Cha','value':'16'},{'op':'advance','ms':1000},{'op':'eval','code':read},{'op':'save','path':str(output)}],[]);assert reopened['stages'][1]['result']==expected[-1];edited=reopened['stages'][4]['result'];assert edited['Cha Mod']=='3' and edited['Limited Feature Max Usages '+str(row)]=='3';assert [edited['Tool '+str(i)] for i in [1,2,3]]==['Flute','Lute','Drum'];checked=inspect(output,edited);assert checked['actual']==edited and all(w['matches'] for w in checked['widgets']);assert script_hashes(output)==script_hashes(source);report['edited_reopen']=edited
  report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'comparison.json',flush=True)

if __name__=='__main__':main()
