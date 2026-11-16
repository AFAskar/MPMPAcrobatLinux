#!/usr/bin/env python3
"""Real Reader manual Font slot/counter bookkeeping, rests and cold persistence.

Compare all six native states and actual checkbox appearances. A disclosed
startup observer supplies positive console/error/timer/Unicode controls; no
RunUserScript add-on re-registration or automatic conversion is introduced.
"""
import argparse,hashlib,importlib.util,json,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import inspect,script_hashes
import fighter_additional_diagnostics as diagnostics
import reader_document_controls as closing
from reference_2024_qualification import require_2024_reference

def module(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/'tools/native'/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);a=p.parse_args();native=json.loads(a.native.read_text());ready=json.loads(a.readiness.read_text());qualified=require_2024_reference(ready,c.harness_fingerprint());assert native['passed'];wanted={s['label']:s for s in native['phases']};assert list(wanted)==['baseline','spent-inspiration','manual-slot-recovery','short-rest','cold-spent-slot','long-rest'];source=Path(native['input']);assert hashlib.sha256(source.read_bytes()).hexdigest()==native['input_sha256'];assert len(native['boxes'])==4 and native['selected_slot'] in native['boxes'];names=list(native['phases'][0]['fields']);slot=native['selected_slot']
 typing=module('typing_control','reader-ascii-input.py');style=module('style','default-style-persistence.py');console=module('console_control','reader-console.py');widgets=module('slot_widgets','verify-bard-slot-widgets.py');raw=module('raw_values','field-state-comparison.py')
 folder=ROOT/'output/testing'/('reader-bard-font-slots-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);base=c.remote_path('runs/bard-font-slots-'+str(time.time_ns()));remote=base+'.pdf';opened=False;console_count=0;report={'passed':False,'scope':__doc__,'native':str(a.native.resolve()),'input':str(source),'input_sha256':native['input_sha256'],'reference':qualified,'phases':[],'inputs':[],'console_checks':[],'test_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 def installed():assert c.script('read',path=remote,fields=['User Script'])['fields']['User Script']=='// MPMB workflow observer installed'
 def capture(label):
  nonlocal remote,console_count
  timer=diagnostics.reader_request(c,remote);summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];values=c.script('read',path=remote,fields=names)['fields'];assert values==wanted[label]['fields'],(label,values,wanted[label]['fields']);c.script('set',path=remote,values={'User Script':''});saved=base+'-'+label+'-diagnostic.pdf';c.script('save',path=remote,output=saved);remote=saved;pdf=c.fetch(remote,folder/(label+'.pdf'));observer=style.saved_capture(pdf,summary,source);assert not observer['errors'] and observer['identity']=={'level':5,'subclass':'bard-lore'};assert observer['calculation']=={'app':True,'doc':True,'delay':False};checked=raw.compare(pdf,values);visible=inspect(pdf,{'Limited Feature Used 1':values['Limited Feature Used 1'],'Limited Feature Max Usages 1':'5'});assert visible['passed'];usage=[w for w in visible['widgets'] if w['name']=='Limited Feature Used 1' and w['visible'] and w['page'] is not None];assert usage and all((w['appearance_text'] or '').strip()==values['Limited Feature Used 1'] for w in usage);box_appearances=widgets.widgets(pdf,{n:values[n] for n in native['boxes']});assert script_hashes(pdf)==script_hashes(source)
  c.script('set',path=remote,values={'User Script':'// MPMB workflow console request'});deadline=time.monotonic()+30
  while True:
   rows=c.command('inspect');roots=[r for r in rows if r.get('class')=='#32770' and r.get('name')=='JavaScript Debugger']
   if roots:break
   assert time.monotonic()<deadline,rows;time.sleep(.1)
  assert len(roots)==1;owner=roots[0]['handle'];edits=[r for r in rows if r.get('owner')==owner and r.get('class')=='RICHEDIT50W'];assert len(edits)==1;seen={'owner':owner,'edit':edits[0]['handle'],'live':c.command('dialog_control',owner=owner,handle=edits[0]['handle'])};seen['close']=console.close_console(seen);console_count+=1;assert seen['live']['text'].rstrip('\r\n')=='MPMB 2024 Bard resource workflow console sentinel',seen;assert c.script('read',path=remote,fields=['User Script'])['fields']['User Script']=='// MPMB workflow console complete:'+str(console_count);report['console_checks'].append(seen);report['phases'].append({'label':label,'fields':values,'pdf':str(pdf),'timer':timer,'observer':observer,'canonical':checked,'visible':visible,'slot_widgets':box_appearances});(folder/'progress.json').write_text(json.dumps(report,indent=2))
 try:
  with c.desktop_lock():
   assert not [w for w in c.command('inspect') if w.get('class')=='AcrobatSDIWindow' and '.pdf' in w.get('name','').lower()],'Pre-existing document'
   subprocess.run(c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace(chr(92),'/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote);installed();capture('baseline');report['inputs'].append(typing.commit(c,remote,'Limited Feature Used 1','3'));capture('spent-inspiration');focus=c.script('focus',path=remote,field=slot);observed=c.command('inspect_focused');assert observed.get('in_reader') and observed.get('foreground_class')=='AcrobatSDIWindow';key=c.command('keys',keys=' ');assert c.script('read',path=remote,fields=[slot])['fields'][slot]=='True';report['slot_activation']={'field':slot,'focus':focus,'observed':observed,'key':key};report['inputs'].append(typing.commit(c,remote,'Limited Feature Used 1','2'));capture('manual-slot-recovery');report['short_rest']=c.script('call',path=remote,name='resetLimFeaUsed',args=['short rest']);capture('short-rest');c.script('set',path=remote,values={'User Script':'','PC Name':'2024 Font manual resource persistence'});saved=base+'-spent.pdf';c.script('save',path=remote,output=saved);remote=saved;report['spent_close']=closing.close_saved(c,remote);opened=False;report['spent_pdf']=str(c.fetch(remote,folder/'reader-spent.pdf'));remote,report['cold_snapshot']=closing.reopen_snapshot(c,remote);opened=True;c.ensure_document(remote);installed();console_count=0;capture('cold-spent-slot');report['long_rest']=c.script('call',path=remote,name='resetLimFeaUsed',args=['long rest']);capture('long-rest');c.script('set',path=remote,values={'User Script':'','PC Name':'2024 Font manual resource persistence'});saved=base+'-final.pdf';c.script('save',path=remote,output=saved);remote=saved;report['final_close']=closing.close_saved(c,remote);opened=False;report['pdf']=str(c.fetch(remote,folder/'reader-final.pdf'));assert [s['timer']['invocation_count'] for s in report['phases']]==[1,2,3,4,1,2];assert c.harness_fingerprint()==ready['harness_sha256'] and hashlib.sha256(source.read_bytes()).hexdigest()==native['input_sha256'];report['passed']=True
 except Exception as e:report.update(error=str(e),traceback=traceback.format_exc())
 finally:
  if opened:report['retained_document']=remote
  (folder/'slots.json').write_text(json.dumps(report,indent=2));print(folder/'slots.json',flush=True)
if __name__=='__main__':main()
