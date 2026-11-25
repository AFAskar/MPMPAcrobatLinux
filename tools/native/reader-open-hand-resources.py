#!/usr/bin/env python3
"""Real2024 Open Hand class-dialog text choice and nine resource/rest/cold states.

Native selects the original dropdowns; Reader commits the offered class-text and
level edits. This compares completed character/resource states, not UI path or
per-keystroke parity. Structural scores are not legal feat/ASI construction.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/native'),str(ROOT/'tools/acrobat')]
import control as c
import fighter_additional_diagnostics as diag
import reader_document_controls as closing
from reference_2024_qualification import require_2024_reference
from workflow_state_comparison import encoded_state,compare
from verify import canonical_fields,inspect,script_hashes
from pypdf import PdfReader

def module(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/'tools/native'/file)
 result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--native',type=Path,required=True)
 parser.add_argument('--readiness',type=Path,required=True)
 parser.add_argument('--input',type=Path)
 parser.add_argument('--removal-roundtrip',action='store_true',help='Cold removed5, readd6 and cold6 against native3')
 args=parser.parse_args();native=json.loads(args.native.read_text());assert native['passed'] and len(native['phases'])==(3 if args.removal_roundtrip else 9)
 assert native.get('removal_roundtrip',False)==args.removal_roundtrip
 wanted={p['label']:p['state'] for p in native['phases']};assert len(wanted)==(3 if args.removal_roundtrip else 9)
 source=args.input or Path(native['input']);assert hashlib.sha256(source.read_bytes()).hexdigest()==native['input_sha256']
 observer=(ROOT/'tools/native/open-hand-resource-observer.js').read_text();assert hashlib.sha256(observer.encode()).hexdigest()==native['observer_sha256']
 ready=json.loads(args.readiness.read_text());reference=require_2024_reference(ready,c.harness_fingerprint())
 style=module('open_hand_style','default-style-persistence.py');console=module('open_hand_console','reader-console.py');typing=module('open_hand_typing','reader-ascii-input.py')
 folder=ROOT/'output/testing'/('reader-open-hand-resources-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
 base=c.remote_path('runs/open-hand-resources-'+str(time.time_ns()));remote=base+'.pdf';opened=False;pending=None
 report={'passed':False,'scope':__doc__,'native':str(args.native.resolve()),'input':str(source),'input_sha256':native['input_sha256'],'readiness':str(args.readiness.resolve()),'reference':reference,'phases':[],'observations':[],'inputs':[],'console_checks':[],'removal_roundtrip':args.removal_roundtrip,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'observer_sha256':native['observer_sha256'],'verifier_sha256':hashlib.sha256((ROOT/'tools/native/verify-generated-fields.py').read_bytes()).hexdigest()}
 def persist():(folder/'progress.json').write_text(json.dumps(report,indent=2))
 def installed():
  c.script('set',path=remote,values={'User Script':observer});report['inputs'].append({'install':c.script('call',path=remote,name='RunUserScript',args=[False])});c.ensure_document(remote)
 def console_check():
  c.script('set',path=remote,values={'User Script':'// MPMB workflow console request'});deadline=time.monotonic()+30
  while True:
   rows=c.command('inspect')
   if any(r['class']=='#32770' and r['name']=='JavaScript Debugger' for r in rows):break
   assert time.monotonic()<deadline,rows
   time.sleep(.1)
  observed=console.observed_console('2024 Open Hand resource sentinel');observed['close']=console.close_console(observed);report['console_checks'].append(observed)
 def capture(label):
  nonlocal remote
  timer=diag.reader_request(c,remote);summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];c.script('set',path=remote,values={'User Script':''});output=base+'-'+label+'-diagnostic.pdf';c.script('save',path=remote,output=output);remote=output;pdf=c.fetch(remote,folder/(label+'-diagnostic.pdf'));state=style.saved_capture(pdf,summary,source)
  point={'label':label,'pdf':str(pdf),'state':state,'timer':timer};report['observations'].append(point);persist();assert not state['errors'] and encoded_state(state)==encoded_state(wanted[label]),('Captured state mismatch',label)
  reader=PdfReader(pdf);fields=canonical_fields(reader);co=reader.trailer['/Root']['/AcroForm'].get('/CO',[]);physical=[]
  for row in state['rows']:
   name='Limited Feature Max Usages '+row['row'];ref=fields[name]['reference'];indexes=[i for i,entry in enumerate(co) if getattr(entry,'idnum',None)==ref];assert indexes==([] if row['calcOrderIndex']==-1 else [row['calcOrderIndex']]),(label,name,indexes,row['calcOrderIndex']);physical.append({'field':name,'indexes':indexes})
  expected=dict(state['fields'],**state['resources']);api=folder/(label+'-expected.json');api.write_text(json.dumps(expected));verification=folder/(label+'-verification')
  with (folder/(label+'-verification.log')).open('w') as log:p=subprocess.run([sys.executable,str(ROOT/'tools/native/verify-generated-fields.py'),str(pdf),str(api),str(verification)],stdout=log,stderr=log,timeout=600)
  checked=json.loads((verification/'verification.json').read_text());assert p.returncode==0 and checked['passed'] and checked['source_sha256']==report['verifier_sha256'];assert script_hashes(pdf)==script_hashes(source)
  if timer['invocation_count']==1:console_check()
  point.update(canonical=checked,physical_co_slots=len(co),physical_rows=physical,console_qualified=True);report['phases'].append(point);persist()
 def edit_wis(value):
  report['inputs'].append({'Wis':value,'typing':typing.commit(c,remote,'Wis',str(value))});c.ensure_document(remote)
 def call(name,args):
  report['inputs'].append({'function':name,'args':args,'result':c.script('call',path=remote,name=name,args=args)});c.ensure_document(remote)
 def select_class():
  nonlocal pending
  c.script('set',path=remote,values={'PC Name':'Open Hand resource workflow'});pending=c.script_submit('call',path=remote,name='SelectClass',args=[]);report['class_request']=pending;persist();deadline=time.monotonic()+90
  while True:
   rows=c.command('inspect');dialogs=[r for r in rows if r['class']=='#32770' and r['name']=='CLASS SELECTION DIALOG']
   if dialogs:break
   assert time.monotonic()<deadline,rows
   time.sleep(.1)
  assert len(dialogs)==1;owner=dialogs[0]['handle'];edits=[r for r in rows if r['owner']==owner and r['class'] in ['RICHEDIT50W','Edit'] and r.get('read_only') is False and r['enabled']];live=[(r,c.command('dialog_control',owner=owner,handle=r['handle'])) for r in edits];names=[(r,v) for r,v in live if v['text']=='Monk (Warrior of Shadow)'];assert len(names)==1,live;name_control=names[0][0]
  report['class_dialog']={'before':rows,'live_edits':live,'edits':[]}
  def commit_control(control,text):
   focus=c.command('focus_control',owner=owner,handle=control['handle']);assert focus['focused'];paste=c.command('paste',value=text);assert paste['verified'] and paste['value']==text;observed=c.command('dialog_control',owner=owner,handle=control['handle']);assert observed['text']==text;report['class_dialog']['edits'].append({'control':control,'focus':focus,'paste':paste,'after':observed});persist()
  commit_control(name_control,'Monk (Warrior of the Open Hand)')
  rows=c.command('inspect');numeric=[]
  for row in rows:
   if row['owner']==owner and row['class'] in ['RICHEDIT50W','Edit'] and row.get('read_only') is False and row['enabled'] and abs(row['rect'][1]-name_control['rect'][1])<5:
    observed=c.command('dialog_control',owner=owner,handle=row['handle'])
    if observed['text']=='3':numeric.append(row)
  assert len(numeric)==1,numeric;commit_control(numeric[0],'6');report['class_dialog']['after']=c.command('inspect');buttons=[r for r in report['class_dialog']['after'] if r['owner']==owner and r['class']=='Button' and r['name']=='Apply' and r['enabled']];assert len(buttons)==1,report['class_dialog']['after'];report['class_dialog']['apply']=c.command('invoke',name=buttons[0]['name'],owner=owner);report['class_dialog']['completion']=c.script_result(pending,timeout=120);pending=None;c.ensure_document(remote)
 def clean_save(label):
  nonlocal remote
  c.script('set',path=remote,values={'User Script':'','PC Name':'Open Hand resource workflow'});output=base+'-'+label+'.pdf';c.script('save',path=remote,output=output);remote=output;pdf=c.fetch(remote,folder/(label+'.pdf'));checked=inspect(pdf,{'PC Name':'Open Hand resource workflow','Character Level':'6','Wis':'16'});assert checked['passed'] and script_hashes(pdf)==script_hashes(source);report[label]={'pdf':str(pdf),'independent':checked};return pdf
 try:
  with c.desktop_lock():
   assert not [r for r in c.command('inspect') if r['class']=='AcrobatSDIWindow' and '.pdf' in r['name'].lower()],'Pre-existing Reader document'
   subprocess.run(c.SCP+[str(source),c.SCP_TARGET + ':MPMB-Testing/runs/'+remote.replace('\\','/').rsplit('/',1)[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote);installed()
   if args.removal_roundtrip:
    report['scope']='Real Reader cold removed5/readded6/cold6; original class callback, retained timer, complete captured state and canonical/AP checks. No class-dropdown or full Monk claim.'
    capture('cold-removed5');call('ApplyClasses',['Monk (Warrior of the Open Hand) 6',False]);capture('readded6')
   else:
    select_class();capture('selected6')
    for resource_name,value in [('Focus Points','2'),('Uncanny Metabolism','1'),('Wholeness of Body','3')]:
     matching=[row for row in wanted['selected6']['rows'] if row['name'].startswith(resource_name)];assert len(matching)==1;field='Limited Feature Used '+matching[0]['row'];report['inputs'].append({'resource':resource_name,'spend':typing.commit(c,remote,field,value)})
    capture('spent6');call('resetLimFeaUsed',['short rest']);capture('short-rest6');edit_wis(8);capture('wis8');call('resetLimFeaUsed',['long rest']);capture('long-rest8');edit_wis(16);capture('wis16');call('ApplyClasses',['Monk (Warrior of the Open Hand) 5',False]);capture('removed5');call('ApplyClasses',['Monk (Warrior of the Open Hand) 6',False]);capture('readded6');
   clean_save('changed');report['changed_close']=closing.close_saved(c,remote);opened=False;remote,report['cold_snapshot']=closing.reopen_snapshot(c,remote);opened=True;c.ensure_document(remote);installed();capture('cold-readded6');report['pdf']=str(clean_save('final'));report['final_close']=closing.close_saved(c,remote);opened=False
   assert [p['timer']['invocation_count'] for p in report['phases']]==([1,2,1] if args.removal_roundtrip else list(range(1,9))+[1]) and len(report['console_checks'])==2
   report['strict_json_comparison']=compare(native,dict(report,passed=True));assert c.harness_fingerprint()==ready['harness_sha256'];report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:
  if opened:
   try:
    with c.desktop_lock():
     if pending:report['unresolved_original_request']=pending
     else:
      retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);remote=retained;report['cleanup_close']=closing.close_saved(c,remote);report['failed_pdf']=str(c.fetch(remote,folder/'failed-retained.pdf'));opened=False
   except Exception as error:report['cleanup_error']=str(error)
  report['opened']=opened;(folder/'resources.json').write_text(json.dumps(report,indent=2));print(folder,flush=True)


if __name__=='__main__':main()
