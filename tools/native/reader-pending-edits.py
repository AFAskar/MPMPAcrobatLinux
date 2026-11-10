#!/usr/bin/env python3
"""Consume actual2024 desktop saves in Reader and make further changed native saves.

Plain Name/Strength and retained class/resource state only. This is not complete
class, rich-editor, console-clean or pixel-equivalence qualification.
"""
import argparse,hashlib,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import canonical_fields,inspect,script_hashes
import reader_document_controls as closing

def module(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/'tools/native'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

typing=module('typing_control','reader-ascii-input.py');fields=module('field_control','field-state-comparison.py')

def values(path):return {name:row.get('/V','') for name,row in canonical_fields(PdfReader(path)).items()}

def visible_state(path,expected):
 # Class Features/Extra.Notes contain MPMB markup in /V; their formatted AP
 # intentionally omits those markers. Do not compare raw markup to display.
 plain={n:v for n,v in expected.items() if n not in ['Class Features','Extra.Notes']}
 result=inspect(path,plain);assert result['passed'],result
 rich={n:expected[n] for n in ['Class Features','Extra.Notes']}
 observed=inspect(path,rich);display=[]
 for name,value in rich.items():
  if not value:continue
  rows=[w for w in observed['widgets'] if w['name']==name and w.get('visible') and w.get('page') is not None]
  assert rows and all(w.get('appearance') and w.get('appearance_text','').strip() for w in rows),(name,rows)
  text='\n'.join(w['appearance_text'] for w in rows)
  if name=='Class Features':assert all(label in text for label in ['Fighting Style','Second Wind','Weapon Mastery']),text
  display.append({'field':name,'appearance_text':text,'scope':'Nonempty formatted AP and2024 Fighter1 feature labels; raw markup/pixels/fonts/line-wrap equality is not claimed'})
 return {'plain_fields':result,'formatted_rich_display':display}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);a=p.parse_args();native=json.loads(a.native.read_text());ready=json.loads(a.readiness.read_text());assert native['passed'] and len(native['cases'])==3 and ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
 binary=ROOT/'target/debug/mpmb-reader';assert hashlib.sha256(binary.read_bytes()).hexdigest()==native['binary_sha256'];folder=ROOT/'output/testing'/('reader-pending-edits-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);report={'passed':False,'scope':__doc__,'native':str(a.native.resolve()),'readiness':str(a.readiness.resolve()),'binary_sha256':native['binary_sha256'],'typing_helper_sha256':hashlib.sha256(Path(typing.__file__).read_bytes()).hexdigest(),'cases':[]};remote=None;opened=False
 try:
  with c.desktop_lock():
   assert not [w for w in c.command('inspect') if w.get('class')=='AcrobatSDIWindow' and '.pdf' in w.get('name','').lower()],'Pre-existing Reader document'
   for index,prior in enumerate(native['cases']):
    source=Path(prior['input']);assert hashlib.sha256(source.read_bytes()).hexdigest()==prior['input_sha256'];before=values(source);assert before['Class and Levels']=='Fighter' and before['Character Level']=='1';assert script_hashes(source)==script_hashes(next((ROOT/'Testing').glob('*_2024_*.pdf')));wanted=values(Path(prior['output']));assert wanted['Str']=='16' and wanted['Str Mod']=='3'
    names=['PC Name','Str','Str Mod','Dex','Dex Mod','Con','Con Mod','Class and Levels','Character Level','Proficiency Bonus','Class Features','Extra.Notes','HP Max','AC','HD1 Level'];assert all(n in before for n in names)
    resources=[n for n in before if __import__('re').match(r'^Limited Feature(?: Max Usages| Recovery| Used)? \d+$',n)];assert resources;names+=resources
    expected_before={n:str(before[n]) for n in names};expected_after={n:str(wanted[n]) for n in names};base=c.remote_path('runs/pending-edits-'+str(time.time_ns()));remote=base+'.pdf';case={'input':str(source),'input_sha256':prior['input_sha256'],'native_changed':prior['output'],'selected_fields':names};report['cases'].append(case)
    subprocess.run(c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote);case['reader_before']=c.script('read',path=remote,fields=names);assert case['reader_before']['fields']==expected_before,(index,'initial Reader state differs')
    case['input_action']=typing.commit(c,remote,'Str','16');case['reader_after']=c.script('read',path=remote,fields=names);assert case['reader_after']['fields']==expected_after,(index,'changed Reader state differs')
    saved=base+'-reader.pdf';c.script('save',path=remote,output=saved);remote=saved;case['close']=closing.close_saved(c,remote);opened=False;pdf=c.fetch(remote,folder/(str(index)+'-reader.pdf'));case['reader_pdf']=str(pdf);case['canonical_reader']=fields.compare(pdf,expected_after);case['independent_reader']=visible_state(pdf,expected_after);assert script_hashes(pdf)==script_hashes(source)
    after=values(pdf);case['full_canonical_differences_from_native_changed']=[{'name':n,'native_sha256':hashlib.sha256(str(wanted.get(n,'')).encode()).hexdigest(),'reader_sha256':hashlib.sha256(str(after.get(n,'')).encode()).hexdigest()} for n in sorted(set(wanted)|set(after)) if wanted.get(n,'')!=after.get(n,'')]
    script_fields=[n for n in before if 'imported' in n.lower() and 'stringified' in n.lower()];assert script_fields,'Require imported-script payload control';assert all(before[n]==after[n] for n in script_fields),'Full stored imported payload changed';case['complete_imported_payload_fields_preserved']=script_fields
    restored={n:str(before[n]) for n in names};output=folder/(str(index)+'-native-restored.pdf');scenario=folder/(str(index)+'-scenario.json');evidence=folder/(str(index)+'-native.json');scenario.write_text(json.dumps({'steps':[{'op':'advance','ms':4100},{'op':'assert','values':expected_after},{'op':'user-edit','field':'Str','value':str(before['Str'])},{'op':'advance','ms':1000},{'op':'assert','values':restored},{'op':'save','path':str(output)}]}))
    with (folder/(str(index)+'.log')).open('w') as log:run=subprocess.run([str(binary),str(pdf),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=300)
    data=json.loads(evidence.read_text());assert run.returncode==0 and data['passed'] and not data['diagnostics']['errors'] and not data['diagnostics']['console']['messages'],data.get('error');case['native_restore_probe']=str(evidence);case['native_restore_pdf']=str(output);case['canonical_native_restore']=fields.compare(output,restored);case['independent_native_restore']=visible_state(output,restored);assert script_hashes(output)==script_hashes(source);assert hashlib.sha256(source.read_bytes()).hexdigest()==prior['input_sha256'];case['passed']=True;(folder/'progress.json').write_text(json.dumps(report,indent=2))
   assert c.harness_fingerprint()==ready['harness_sha256'];report['passed']=True
 except Exception as e:report['error']=str(e);raise
 finally:
  if opened:
   try:
    with c.desktop_lock():
     shot=c.command('screenshot');c.fetch(shot['path'],folder/'original-failure.png');retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=closing.close_saved(c,retained);c.fetch(retained,folder/'failed-retained.pdf')
   except Exception as e:report['cleanup_error']=str(e)
  (folder/'interop.json').write_text(json.dumps(report,indent=2));print(folder/'interop.json',flush=True)

if __name__=='__main__':main()
