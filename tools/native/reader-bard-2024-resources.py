#!/usr/bin/env python3
"""Original2024 Bard Inspiration maxima, Font/rest transitions and cold saves.

Disclosed startup input; exact native-state comparisons and positive live Reader
console/timer controls at every checkpoint. Not a complete Bard qualification.
"""
import argparse,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import inspect,script_hashes
import fighter_additional_diagnostics as diagnostics
import reader_document_controls as document_controls
from reference_2024_qualification import require_2024_reference

def module(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/'tools/native'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

profile=module('profile','fighter-styles.py');style=module('style','default-style-persistence.py');fields=module('fields','field-state-comparison.py');typing=module('typing_control','reader-ascii-input.py');console=module('console_control','reader-console.py')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);a=p.parse_args();native=json.loads(a.native.read_text());ready=json.loads(a.readiness.read_text())
 assert native['passed'];reference=require_2024_reference(ready,c.harness_fingerprint())
 manifest=json.loads(Path(native['instrumentation']).read_text());assert manifest['passed'] and manifest['mode']=='startup-script-timer'
 assert manifest['diagnostic_helper_sha256']==hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()
 source=Path(native['input']);assert hashlib.sha256(source.read_bytes()).hexdigest()==native['input_sha256']==manifest['input_sha256']
 observer=(ROOT/'tools/native/bard-2024-resource-observer.js').read_text();assert hashlib.sha256(observer.encode()).hexdigest()==manifest['observer_sha256']
 wanted={x['label']:x['state'] for x in native['phases']};assert len(wanted)==len(native['phases'])==13
 source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
 folder=ROOT/'output/testing'/('reader-bard-2024-resources-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);base=c.remote_path('runs/bard-2024-resources-'+str(time.time_ns()));remote=base+'.pdf';opened=False;pending=None;console_count=0
 report={'passed':False,'scope':__doc__,'native':str(a.native.resolve()),'readiness':str(a.readiness.resolve()),'input':str(source),'input_sha256':native['input_sha256'],'observer_sha256':manifest['observer_sha256'],'diagnostic_mode':'startup-script-timer','diagnostic_helper_sha256':manifest['diagnostic_helper_sha256'],'test_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'phases':[],'choices':[],'inputs':[],'timer_requests':[],'console_checks':[],'observations':[],'typing_helper_sha256':hashlib.sha256(Path(typing.__file__).read_bytes()).hexdigest(),'console_helper_sha256':hashlib.sha256(Path(console.__file__).read_bytes()).hexdigest()}
 report['input_sha256']=source_hash;report['origin_mode']='instrumented-baseline';report['reference_qualification']=reference
 def install():
  nonlocal console_count
  console_count=0
  deadline=time.monotonic()+45
  while True:
   marker=c.script('read',path=remote,fields=['User Script'])['fields']['User Script']
   if marker=='// MPMB workflow observer installed':return
   assert time.monotonic()<deadline,('Startup observer did not acknowledge installation',marker)
   time.sleep(0.1)
 def check_console(request=True):
  nonlocal console_count
  if request:c.script('set',path=remote,values={'User Script':'// MPMB workflow console request'})
  deadline=time.monotonic()+20
  while True:
   rows=c.command('inspect');roots=[r for r in rows if r.get('class')=='#32770' and r.get('name')=='JavaScript Debugger']
   if roots:break
   assert time.monotonic()<deadline,('Requested debugger did not open',rows)
   time.sleep(0.1)
  assert len(roots)==1,rows;owner=roots[0]['handle'];edits=[r for r in rows if r.get('owner')==owner and r.get('class')=='RICHEDIT50W'];assert len(edits)==1,rows
  observed=console.read_console_text(owner,edits[0]['handle']);observed['rows']=rows;report['console_checks'].append(observed);observed['close']=console.close_console(observed)
  if request:
   marker=c.script('read',path=remote,fields=['User Script'])['fields']['User Script'];console_count+=1;assert marker=='// MPMB workflow console complete:'+str(console_count),marker;observed['invocation_count']=console_count
  assert observed['live']['text'].rstrip('\r\n')=='MPMB 2024 Bard resource workflow console sentinel',observed
 def capture(label):
  nonlocal remote
  report['timer_requests'].append(diagnostics.reader_request(c,remote));summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];c.script('set',path=remote,values={'User Script':''});output=base+'-'+label+'-diagnostic.pdf';c.script('save',path=remote,output=output);remote=output;pdf=c.fetch(remote,folder/(label+'-diagnostic.pdf'));state=style.saved_capture(pdf,summary,source);assert not state['errors'] and state==wanted[label],(label,state,wanted[label])
  expected=dict(state['fields'],**state['resources'],**state['reactions']);canonical=fields.compare(pdf,expected);visible=inspect(pdf,state['resources']);assert visible['passed'] and script_hashes(pdf)==script_hashes(source)
  usage=[w for w in visible['widgets'] if w['name']=='Limited Feature Used 1' and w['visible'] and w['page'] is not None];assert usage and all((w['appearance_text'] or '').strip()==state['resources']['Limited Feature Used 1'] for w in usage),usage
  report['observations'].append({'label':label,'state':state,'pdf':str(pdf),'summary':summary,'canonical':canonical,'visible':visible,'console_qualified':False});(folder/'progress.json').write_text(json.dumps(report,indent=2)+'\n');check_console();report['observations'][-1]['console_qualified']=True;report['phases'].append({'label':label,'state':state,'pdf':str(pdf),'summary':summary,'canonical':canonical,'visible':visible});(folder/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
 def close_snapshot(label,reopen=True):
  nonlocal remote,opened
  c.script('set',path=remote,values={'User Script':'','PC Name':'2024 Bard resource compatibility'});saved=base+'-'+label+'.pdf';c.script('save',path=remote,output=saved);remote=saved;report[label+'_close']=document_controls.close_saved(c,remote);opened=False;report[label+'_pdf']=str(c.fetch(remote,folder/('reader-'+label+'.pdf')))
  if reopen:remote,report[label+'_snapshot']=document_controls.reopen_snapshot(c,remote);opened=True;c.ensure_document(remote);install()
 try:
  with c.desktop_lock():
   assert not [w for w in c.command('inspect') if w.get('class')=='AcrobatSDIWindow' and '.pdf' in w.get('name','').lower()],'Pre-existing Reader document'
   subprocess.run(c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote);install()
   capture('baseline9')
   report['inputs'].append(typing.commit(c,remote,'Cha','14'));capture('cha14')
   report['inputs'].append(typing.commit(c,remote,'Cha','20'));capture('cha20')
   report['inputs'].append(typing.commit(c,remote,'Limited Feature Used 1','4'));capture('spent9')
   report['short9']=c.script('call',path=remote,name='resetLimFeaUsed',args=['short rest']);capture('short9')
   report['inputs'].append(typing.commit(c,remote,'Limited Feature Used 1','3'));capture('spent-again9');close_snapshot('spent9')
   capture('cold-spent9');report['long9']=c.script('call',path=remote,name='resetLimFeaUsed',args=['long rest']);capture('cold-long9')
   report['level4']=c.script('call',path=remote,name='ApplyClasses',args=['Bard (College of Lore) 4',False]);capture('lore4')
   report['inputs'].append(typing.commit(c,remote,'Limited Feature Used 1','3'))
   report['short4']=c.script('call',path=remote,name='resetLimFeaUsed',args=['short rest']);capture('short4')
   report['long4']=c.script('call',path=remote,name='resetLimFeaUsed',args=['long rest']);capture('long4')
   report['level5']=c.script('call',path=remote,name='ApplyClasses',args=['Bard (College of Lore) 5',False]);capture('font5')
   report['inputs'].append(typing.commit(c,remote,'Limited Feature Used 1','2'))
   report['short5']=c.script('call',path=remote,name='resetLimFeaUsed',args=['short rest']);capture('short5');close_snapshot('rested5',False)
   expected_counts=[1,2,3,4,5,6,1,2,3,4,5,6,7]
   assert [v['invocation_count'] for v in report['timer_requests']]==expected_counts;assert len(report['console_checks'])==len(expected_counts);assert c.harness_fingerprint()==ready['harness_sha256'];assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash;report.update(passed=True,pdf=report['rested5_pdf'])

 except Exception as e:
  report['error']=str(e)
  if hasattr(e,'read_attempts'):report['console_read_attempts']=e.read_attempts
  if hasattr(e,'observation_attempts'):report['focus_observation_attempts']=e.observation_attempts
  raise
 finally:
  if opened:
   try:
    with c.desktop_lock():
     shot=c.command('screenshot');c.fetch(shot['path'],folder/'original-failure.png')
     if any(r.get('class')=='#32770' and r.get('name')=='JavaScript Debugger' for r in c.command('inspect')):
      try:check_console(request=False)
      except Exception as console_error:report['cleanup_console_error']=str(console_error)
     for _ in range(6):
      if not any(w.get('class')=='#32768' for w in c.command('inspect')):break
      c.command('keys',keys='{ESC}')
     if pending:
      try:report['cleanup_original_result']=c.script_result(pending,timeout=120)
      except Exception as e:report['cleanup_original_error']=str(e)
     retained=base+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=document_controls.close_saved(c,retained);c.fetch(retained,folder/'failed-retained.pdf')
   except Exception as e:report['cleanup_error']=str(e)
  (folder/'resources.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'resources.json',flush=True)

if __name__=='__main__':main()
