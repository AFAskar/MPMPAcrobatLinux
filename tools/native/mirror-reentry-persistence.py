#!/usr/bin/env python3
"""Synthetic persistent K action with original MPMB adventure-log synchronization.

Original mirror calculation/validation and embedded scripts stay unchanged.
Exercises changed edits across native saves/reopens, actual Reader reopen/edit/
save, then fresh native edits/reopen. This is not all-class table qualification.
"""
import argparse,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect,script_hashes,canonical_fields,field_text
KEYSTONE=r"event.value=event.value.replace(/ B$/, '\u00a0B');"
READ="({primary:getField('Player Name').valueAsString,mirror:getField('AdvLog.Player Name').valueAsString})"

def action(path,name,key):
 r=PdfReader(path);node=r.get_object(canonical_fields(r)[name]['reference']);a=node.get('/AA',{}).get('/'+key);return field_text(a.get_object()['/JS']) if a else ''

def expected(phase):return {'Player Name':'Phase '+str(phase)+'\u00a0B','AdvLog.Player Name':'Phase '+str(phase)+' B'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--fixture',choices=['2014','2024','ashnar'],default='2024');args=p.parse_args()
 folder=ROOT/'output/testing'/('mirror-reentry-persistence-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
 fixtures=json.loads((ROOT/'docs/fixtures.json').read_text());source=ROOT/'Testing'/fixtures[{'2014':0,'2024':1,'ashnar':2}[args.fixture]]['file'];original_hash=hashlib.sha256(source.read_bytes()).hexdigest();binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
 mirror_v=action(source,'AdvLog.Player Name','V');mirror_c=action(source,'AdvLog.Player Name','C');assert 'ValidateAdvLogInfo' in mirror_v and mirror_c
 report={'passed':False,'fixture':args.fixture,'scope':__doc__,'source_sha256':original_hash,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'native':[]}
 def native(label,input_pdf,before,phase=None,setup=False):
  output=folder/(label+'.pdf');steps=[{'op':'advance','ms':4100}]
  if before:steps.append({'op':'assert','values':expected(before)})
  if setup:steps.append({'op':'eval','code':"__host.command("+json.dumps("getField('Player Name').setAction('Keystroke',"+json.dumps(KEYSTONE)+")")+")"})
  if phase:steps.append({'op':'edit','field':'Player Name','value':'Phase '+str(phase)+' B'})
  final=phase or before;steps.extend([{'op':'assert','values':expected(final)},{'op':'eval','code':READ},{'op':'save','path':str(output)}]);scenario={'dialogs':[{'result':'ok'}]*10,'alerts':[1]*20,'steps':steps};plan=folder/(label+'.json');plan.write_text(json.dumps(scenario));evidence=folder/(label+'-probe.json')
  with (folder/(label+'.log')).open('w') as log:run=subprocess.run([str(binary),str(input_pdf),'--probe',str(plan),str(evidence)],stdout=log,stderr=log,timeout=300)
  data=json.loads(evidence.read_text());assert run.returncode==0 and data['passed'] and not data['diagnostics']['errors'],data.get('error') or data['diagnostics']['errors'];checked=inspect(output,expected(final));assert checked['passed'];assert script_hashes(output)==script_hashes(source);assert action(output,'Player Name','K')==KEYSTONE;assert action(output,'AdvLog.Player Name','V')==mirror_v and action(output,'AdvLog.Player Name','C')==mirror_c
  report['native'].append({'label':label,'input':str(input_pdf),'output':str(output),'state':data['stages'][-2]['result'],'independent':checked});return output
 try:
  first=native('native-phase1',source,None,1,True);second=native('native-phase2',first,1,2)
  observer=r"""var iFileName='Persistent mirror edit.js';Value('User Script','');(function(d){var r={before:READ,after:null,errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};try{Value('Player Name','Phase 3 B');r.after=READ}catch(e){r.errors.push({name:e.name,message:String(e)})}Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);""".replace('READ',READ)
  obs=folder/'observer.js';obs.write_text(observer)
  with (folder/'reader.log').open('w') as log:result=subprocess.run([sys.executable,str(ROOT/'tools/native/reader-script-observation.py'),'--input',str(second),'--observer',str(obs),'--readiness',str(args.readiness)],stdout=log,stderr=log,timeout=420)
  paths=[line.strip() for line in (folder/'reader.log').read_text().splitlines() if line.strip().endswith('/observation.json')];assert paths;ref=Path(paths[-1]);reader=json.loads(ref.read_text());report['reader']=str(ref);assert result.returncode==0 and reader['passed'],reader.get('error');state=reader['captured'];assert not state['errors'];assert state['before']=={'primary':expected(2)['Player Name'],'mirror':expected(2)['AdvLog.Player Name']};assert state['after']=={'primary':expected(3)['Player Name'],'mirror':expected(3)['AdvLog.Player Name']}
  saved=ref.parent/'reader.pdf';checked=inspect(saved,expected(3));assert checked['passed'];assert action(saved,'Player Name','K')==KEYSTONE;assert action(saved,'AdvLog.Player Name','V')==mirror_v and action(saved,'AdvLog.Player Name','C')==mirror_c;report['reader_independent']=checked
  fourth=native('native-phase4',saved,3,4);native('native-reopen-phase4',fourth,4)
  assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash;report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'persistence.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'persistence.json',flush=True)


if __name__=='__main__':main()
