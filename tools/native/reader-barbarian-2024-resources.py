#!/usr/bin/env python3
"""Actual2024 Reader Rage partial/full rests, spending and cold persistence.

Disclosed startup observer preserves original scripts/actions and avoids add-on
re-registration. Requires a positive live debugger sentinel at every checkpoint.
"""
import argparse,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import inspect,script_hashes
import fighter_additional_diagnostics as diagnostics
import reader_document_controls as document_controls

def module(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/'tools/native'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

profile=module('profile','fighter-styles.py');style=module('style','default-style-persistence.py');fields=module('fields','field-state-comparison.py');typing=module('typing_control','reader-ascii-input.py');console=module('console_control','reader-console.py')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--native-spent',action='store_true',help='Cold-load the actual native spent save and qualify three Reader recovery states');a=p.parse_args();native=json.loads(a.native.read_text());ready=json.loads(a.readiness.read_text())
 assert native['passed'] and ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
 assert native['diagnostic_mode']=='startup-script-timer' and native['diagnostic_helper_sha256']==hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()
 source=Path(native['input']);assert hashlib.sha256(source.read_bytes()).hexdigest()==native['input_sha256'];observer=(ROOT/'tools/native/barbarian-2024-observer.js').read_text();assert hashlib.sha256(observer.encode()).hexdigest()==native['observer_sha256'];wanted={x['label']:x['state'] for x in native['phases']};assert len(wanted)==8
 if a.native_spent:
  source=Path(native['spent_pdf']);assert script_hashes(source)==script_hashes(Path(native['input']))
 source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
 folder=ROOT/'output/testing'/('reader-barbarian-2024-resources-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);base=c.remote_path('runs/barbarian-2024-resources-'+str(time.time_ns()));remote=base+'.pdf';opened=False;pending=None;console_count=0
 report={'passed':False,'scope':__doc__,'native':str(a.native.resolve()),'readiness':str(a.readiness.resolve()),'input':str(source),'input_sha256':native['input_sha256'],'observer_sha256':native['observer_sha256'],'diagnostic_mode':'startup-script-timer','diagnostic_helper_sha256':native['diagnostic_helper_sha256'],'test_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'phases':[],'choices':[],'inputs':[],'timer_requests':[],'console_checks':[],'observations':[],'typing_helper_sha256':hashlib.sha256(Path(typing.__file__).read_bytes()).hexdigest(),'console_helper_sha256':hashlib.sha256(Path(console.__file__).read_bytes()).hexdigest()}
 report['input_sha256']=source_hash;report['origin_mode']='native-spent' if a.native_spent else 'instrumented-baseline'
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
  observed={'owner':owner,'edit':edits[0]['handle'],'live':c.command('dialog_control',owner=owner,handle=edits[0]['handle']),'rows':rows};report['console_checks'].append(observed);observed['close']=console.close_console(observed)
  if request:
   marker=c.script('read',path=remote,fields=['User Script'])['fields']['User Script'];console_count+=1;assert marker=='// MPMB workflow console complete:'+str(console_count),marker;observed['invocation_count']=console_count
  assert observed['live']['text'].rstrip('\r\n')=='MPMB 2024 Barbarian workflow console sentinel',observed
 def capture(label):
  nonlocal remote
  report['timer_requests'].append(diagnostics.reader_request(c,remote));summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];c.script('set',path=remote,values={'User Script':''});output=base+'-'+label+'-diagnostic.pdf';c.script('save',path=remote,output=output);remote=output;pdf=c.fetch(remote,folder/(label+'-diagnostic.pdf'));state=style.saved_capture(pdf,summary,source);assert not state['errors'] and state==wanted[label],(label,state,wanted[label])
  expected=dict(state['fields'],**state['resources'],**state['reactions']);canonical=fields.compare(pdf,expected);visible=inspect(pdf,{n:v for n,v in state['resources'].items() if v});assert visible['passed'] and script_hashes(pdf)==script_hashes(source)
  report['observations'].append({'label':label,'state':state,'pdf':str(pdf),'summary':summary,'canonical':canonical,'visible':visible,'console_qualified':False});(folder/'progress.json').write_text(json.dumps(report,indent=2)+'\n');check_console();report['observations'][-1]['console_qualified']=True;report['phases'].append({'label':label,'state':state,'pdf':str(pdf),'summary':summary,'canonical':canonical,'visible':visible});(folder/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
 def close_snapshot(label,reopen=True):
  nonlocal remote,opened
  c.script('set',path=remote,values={'User Script':'','PC Name':'2024 Berserker resource compatibility'});saved=base+'-'+label+'.pdf';c.script('save',path=remote,output=saved);remote=saved;report[label+'_close']=document_controls.close_saved(c,remote);opened=False;report[label+'_pdf']=str(c.fetch(remote,folder/('reader-'+label+'.pdf')))
  if reopen:remote,report[label+'_snapshot']=document_controls.reopen_snapshot(c,remote);opened=True;c.ensure_document(remote);install()
 try:
  with c.desktop_lock():
   assert not [w for w in c.command('inspect') if w.get('class')=='AcrobatSDIWindow' and '.pdf' in w.get('name','').lower()],'Pre-existing Reader document'
   subprocess.run(c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote);install()
   if not a.native_spent:
    for field,value in [('Str','18'),('Dex','14'),('Con','16'),('Int','10'),('Wis','12'),('Cha','8')]:report['inputs'].append(typing.commit(c,remote,field,value))
    report['class']=c.script('call',path=remote,name='ApplyClasses',args=['Barbarian (Berserker) 3',False]);report['inputs'].append(typing.commit(c,remote,'Attack.1.Weapon Selection','Greataxe'));capture('berserker3')
    report['inputs'].append(typing.commit(c,remote,'Limited Feature Used 1','3'));capture('spent3');report['short_reset']=c.script('call',path=remote,name='resetLimFeaUsed',args=['short rest']);capture('short-rest3');report['long_reset']=c.script('call',path=remote,name='resetLimFeaUsed',args=['long rest']);capture('long-rest3')
    report['inputs'].append(typing.commit(c,remote,'Limited Feature Used 1','2'));capture('spent-again3');close_snapshot('spent3')
   capture('cold-spent3');report['cold_short_reset']=c.script('call',path=remote,name='resetLimFeaUsed',args=['short rest']);capture('cold-short-rest3');report['cold_long_reset']=c.script('call',path=remote,name='resetLimFeaUsed',args=['long rest']);capture('cold-long-rest3');close_snapshot('rested3',False)
   expected_counts=[1,2,3] if a.native_spent else [1,2,3,4,5,1,2,3]
   assert [v['invocation_count'] for v in report['timer_requests']]==expected_counts;assert len(report['console_checks'])==len(expected_counts);assert c.harness_fingerprint()==ready['harness_sha256'];assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash;report.update(passed=True,pdf=report['rested3_pdf'])

 except Exception as e:report['error']=str(e);raise
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
