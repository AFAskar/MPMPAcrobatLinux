#!/usr/bin/env python3
"""Original calculated resources: edited native/Reader persistence and rests.

Exact captured resource/character fields, calculation code, physical CO index,
widgets and original scripts are required. Appearance text is reported separately.
No expected derived values are injected into reference PDFs.
"""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields,field_text,inspect,script_hashes
CODE="event.value=Number(What('Wis Mod'))+2;"
LABEL='Compatibility Calculated Resource'

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',choices=['2014','2024','ashnar'],required=True);p.add_argument('--resume',type=Path,help='Resume a retained pilot after its first Reader phase completed; validate hashes and reuse the exact result without replay');p.add_argument('--readiness',type=Path,required=True);a=p.parse_args()
 source=next((ROOT/'Testing').glob({'2014':'*_2014_*.pdf','2024':'*_2024_*.pdf','ashnar':'Ashnar*.pdf'}[a.fixture]));source_hash=hashlib.sha256(source.read_bytes()).hexdigest();scripts=script_hashes(source)
 folder=ROOT/'output/testing'/('calculated-resource-persistence-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(a.resume.parent/'mpmb-reader' if a.resume else ROOT/'target/debug/mpmb-reader',binary)
 report={'passed':False,'scope':__doc__,'fixture':a.fixture,'source':str(source),'source_sha256':source_hash,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'native':[],'reader':[]}
 def observer(phase):return 'tDoc.__resourcePhase='+json.dumps(phase)+';\n'+(ROOT/'tools/native/calculated-resource-observer.js').read_text()
 def check(pdf,capture,maximum,used):
  assert not capture['errors'],capture['errors'];state=capture['after'];row=state['row'];r=PdfReader(pdf);fields=canonical_fields(r);co=r.trailer['/Root']['/AcroForm'].get('/CO',[])
  assert script_hashes(pdf)==scripts;assert len(r.pages)==len(PdfReader(source).pages)
  independent=inspect(pdf,state['fields']);assert independent['actual']==state['fields'];assert independent['widgets'] and all(w['matches'] for w in independent['widgets'])
  if maximum is None:
   assert row==0;old=capture['before']['row'];node=r.get_object(fields['Limited Feature Max Usages '+str(old)]['reference']);assert '/C' not in node.get('/AA',{});assert field_text(node.get('/TM',''))=='';assert fields['Limited Feature Max Usages '+str(old)]['/V']=='';assert node.indirect_reference.idnum not in [ref.idnum for ref in co]
  else:
   assert row>0 and state['index']>=0 and state['calculation']==CODE
   key='Limited Feature Max Usages '+str(row);assert state['fields'][key]==str(maximum);assert state['fields']['Limited Feature Used '+str(row)]==str(used)
   node=r.get_object(fields[key]['reference']);assert co[state['index']].idnum==node.indirect_reference.idnum;assert sum(ref.idnum==node.indirect_reference.idnum for ref in co)==1
   assert field_text(node['/AA']['/C']['/JS'])==CODE
  if capture['phase']=='edit-high':
   assert len(capture['rests'])==3
   assert [s['fields']['Limited Feature Used '+str(s['row'])] for s in capture['rests']]==['1','1','']
  return {'canonical_widgets_equal':True,'calculation_persisted':True,'raw_appearance_inspection_passed':independent['passed']}
 def native(label,input_pdf,phase,maximum,used):
  output=folder/(label+'.pdf');plan=folder/(label+'.json');evidence=folder/(label+'-probe.json');scenario={'dialogs':[{'result':'ok'}]*10,'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':"Value('User Script',"+json.dumps(observer(phase))+")"},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'eval','code':"JSON.parse(getField('PC Name').valueAsString)"},{'op':'save','path':str(output)}]};plan.write_text(json.dumps(scenario))
  with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(input_pdf),'--probe',str(plan),str(evidence)],stdout=log,stderr=log,timeout=300)
  data=json.loads(evidence.read_text());assert proc.returncode==0 and data['passed'] and not data['diagnostics']['errors'],data.get('error') or data['diagnostics']['errors'];capture=data['stages'][-2]['result'];saved=canonical_fields(PdfReader(output))['PC Name']['/V'];assert saved.isascii() and json.loads(saved)==capture;assert [ord(ch) for ch in capture['sentinel']]==[160,8232,128512]
  checked=check(output,capture,maximum,used);report['native'].append({'phase':phase,'pdf':str(output),'capture':capture,'checks':checked});return output
 def reader(label,input_pdf,phase,maximum,used):
  script=folder/(label+'.js');script.write_text(observer(phase));logpath=folder/(label+'.log')
  if a.resume and phase=='edit-high':
   oldlog=a.resume.parent/(label+'.log');ref=Path([s.strip() for s in oldlog.read_text().splitlines() if s.strip().endswith('/observation.json')][-1]);r=json.loads(ref.read_text());assert r['passed'] and 'close' in r;assert Path(r['input']).resolve()==input_pdf.resolve();assert hashlib.sha256(input_pdf.read_bytes()).hexdigest()==r['input_sha256'];assert Path(r['observer']).read_text()==observer(phase);logpath.write_text('Reused completed/closed original result without replay\n'+str(ref)+'\n')
  else:
   with logpath.open('w') as log:proc=subprocess.run([sys.executable,str(ROOT/'tools/native/reader-script-observation.py'),'--input',str(input_pdf),'--observer',str(script),'--readiness',str(a.readiness)],stdout=log,stderr=log,timeout=420)
   ref=Path([s.strip() for s in logpath.read_text().splitlines() if s.strip().endswith('/observation.json')][-1]);r=json.loads(ref.read_text());assert proc.returncode==0 and r['passed'],r.get('error')
  output=ref.parent/'reader.pdf';checked=check(output,r['captured'],maximum,used)
  comparelog=folder/(label+'-comparison.log')
  with comparelog.open('w') as log:proc=subprocess.run([sys.executable,str(ROOT/'tools/native/verify-script-observation.py'),'--reader',str(ref),'--binary',str(binary)],stdout=log,stderr=log,timeout=330)
  comparison=Path([s.strip() for s in comparelog.read_text().splitlines() if s.strip().endswith('/comparison.json')][-1]);assert proc.returncode==0 and json.loads(comparison.read_text())['passed'];native_fields={k:v['/V'] for k,v in canonical_fields(PdfReader(comparison.parent/'native.pdf')).items()};reader_fields={k:v['/V'] for k,v in canonical_fields(PdfReader(output)).items()};differences={k:{'native':native_fields.get(k),'reader':reader_fields.get(k)} for k in set(native_fields)|set(reader_fields) if native_fields.get(k)!=reader_fields.get(k)};canonical_report=folder/(label+'-full-canonical.json');canonical_report.write_text(json.dumps({'exact':not differences,'native_field_count':len(native_fields),'reader_field_count':len(reader_fields),'differences':differences},indent=2)+'\n');report['reader'].append({'phase':phase,'observation':str(ref),'exact_native_comparison':str(comparison),'checks':checked,'full_canonical_report':str(canonical_report),'full_canonical_exact':not differences});return output
 try:
  if a.resume:
   old=json.loads(a.resume.read_text());assert old['source_sha256']==source_hash and old['binary_sha256']==report['binary_sha256'];assert len(old['native'])==2 and [n['phase'] for n in old['native']]==['create','edit'];report['resumed_from']=str(a.resume)
   for entry,maximum in zip(old['native'],[6,3]):check(Path(entry['pdf']),entry['capture'],maximum,1)
   report['native'].extend(old['native']);edited=Path(old['native'][-1]['pdf'])
  else:created=native('native-created',source,'create',6,1);edited=native('native-edited',created,'edit',3,1)
  saved=reader('reader-high-rests',edited,'edit-high',7,'');reopened=native('reader-native-reopened',saved,'read',7,'')
  removed=native('native-removed',reopened,'remove',None,None);readded=reader('reader-readded',removed,'readd',5,0);native('native-final-reopen',readded,'read',5,0)
  assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash;report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'persistence.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'persistence.json',flush=True)

if __name__=='__main__':main()
