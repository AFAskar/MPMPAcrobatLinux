#!/usr/bin/env python3
"""Actual Reader Superior Technique choices, resource use, removal and reopen.

Only the matched Champion profile; no full class/table compatibility claim.
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

profile=module('profile','fighter-styles.py');style=module('style','default-style-persistence.py');fields=module('fields','field-state-comparison.py');menus=module('menus','warlock-reader-invocations.py');typing=module('typing_control','reader-ascii-input.py')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);a=p.parse_args();native=json.loads(a.native.read_text());ready=json.loads(a.readiness.read_text())
 assert native['passed'] and ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
 assert native['diagnostic_mode']==diagnostics.MODE and native['diagnostic_helper_sha256']==hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()
 source=Path(native['input']);assert hashlib.sha256(source.read_bytes()).hexdigest()==native['input_sha256'];observer=(ROOT/'tools/native/fighter-superior-observer.js').read_text();assert hashlib.sha256(observer.encode()).hexdigest()==native['observer_sha256'];wanted={x['label']:x['state'] for x in native['phases']};assert len(wanted)==13
 folder=ROOT/'output/testing'/('reader-fighter-superior-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);base=c.remote_path('runs/fighter-superior-'+str(time.time_ns()));remote=base+'.pdf';opened=False;pending=None
 report={'passed':False,'scope':__doc__,'native':str(a.native.resolve()),'readiness':str(a.readiness.resolve()),'input':str(source),'input_sha256':native['input_sha256'],'observer_sha256':native['observer_sha256'],'diagnostic_mode':diagnostics.MODE,'diagnostic_helper_sha256':native['diagnostic_helper_sha256'],'test_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'phases':[],'choices':[],'inputs':[],'timer_requests':[]}
 def complete():
  nonlocal pending
  result=c.script_result(pending,timeout=120);pending=None;c.ensure_document(remote);return result
 def install():
  nonlocal pending
  c.script('set',path=remote,values={'User Script':diagnostics.install(profile.SETUP,observer)});pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);complete()
 def choose(path):
  nonlocal pending
  pending=c.script_submit('call',path=remote,name='ClassFeatureOptions',args=[]);actions=[]
  for label in path:
   popup=menus.popup(label,folder);matches=[(i,x) for i,x in enumerate(popup['children']) if x['name'].split('\t')[0].strip().lstrip('✓✔').strip()==label];assert len(matches)==1,(label,popup)
   index,item=matches[0];actions.append({'popup':popup,'selected':item,'action':c.command('activate_menu',owner=popup['native_window_handle'],position=index,name=item['name'])})
  report['choices'].append({'path':path,'actions':actions,'completion':complete()})
 def capture(label):
  nonlocal remote
  report['timer_requests'].append(diagnostics.reader_request(c,remote));summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];c.script('set',path=remote,values={'User Script':''});output=base+'-'+label+'-diagnostic.pdf';c.script('save',path=remote,output=output);remote=output;pdf=c.fetch(remote,folder/(label+'-diagnostic.pdf'));state=style.saved_capture(pdf,summary,source);assert not state['errors'] and state==wanted[label],(label,state,wanted[label])
  expected=dict(state['fields'],**state['resources'],**state['reactions']);expected.update({'Class Features':state['featureText'],'Extra.Notes':state['notesText']});canonical=fields.compare(pdf,expected);visible=inspect(pdf,{n:v for n,v in state['resources'].items() if v});assert visible['passed'] and script_hashes(pdf)==script_hashes(source)
  report['phases'].append({'label':label,'state':state,'pdf':str(pdf),'summary':summary,'canonical':canonical,'visible':visible});(folder/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
 def close_snapshot(label,reopen=True):
  nonlocal remote,opened
  c.script('set',path=remote,values={'User Script':'','PC Name':'Champion Superior Technique compatibility'});saved=base+'-'+label+'.pdf';c.script('save',path=remote,output=saved);remote=saved;report[label+'_close']=document_controls.close_saved(c,remote);opened=False;report[label+'_pdf']=str(c.fetch(remote,folder/('reader-'+label+'.pdf')))
  if reopen:remote,report[label+'_snapshot']=document_controls.reopen_snapshot(c,remote);opened=True;c.ensure_document(remote);install()
 try:
  with c.desktop_lock():
   assert not [w for w in c.command('inspect') if w.get('class')=='AcrobatSDIWindow' and '.pdf' in w.get('name','').lower()],'Pre-existing Reader document'
   subprocess.run(c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote);install();capture('loaded-dueling-17')
   choose(['Champion','Additional Fighting Style','Superior Technique']);capture('superior-17');choose(['Bonus Battle Master Maneuver (selected 0 of 1)','Disarming Attack']);capture('disarming-17')
   report['inputs'].append(typing.commit(c,remote,'Limited Feature Used 4','1'));capture('spent-17');close_snapshot('spent17');capture('cold-spent-17');report['short_reset']=c.script('call',path=remote,name='resetLimFeaUsed',args=['short rest']);capture('short-reset-17')
   choose(['Bonus Battle Master Maneuver (selected 1 of 1)','Disarming Attack']);capture('maneuver-removed-17');choose(['Bonus Battle Master Maneuver (selected 0 of 1)','Riposte']);capture('riposte-17');report['drop_level']=c.script('call',path=remote,name='ApplyClasses',args=['Fighter (Champion) 9',False]);capture('removed-9');close_snapshot('removed9');capture('cold-removed-9')
   report['restore_level']=c.script('call',path=remote,name='ApplyClasses',args=['Fighter (Champion) 17',False]);capture('restored-empty-17');choose(['Champion','Additional Fighting Style','Superior Technique']);capture('restored-superior-17');choose(['Bonus Battle Master Maneuver (selected 0 of 1)','Disarming Attack']);capture('reselected-disarming-17');close_snapshot('final17',False)
   assert [v['invocation_count'] for v in report['timer_requests']]==list(range(1,5))+list(range(1,6))+list(range(1,5));assert c.harness_fingerprint()==ready['harness_sha256'];assert hashlib.sha256(source.read_bytes()).hexdigest()==native['input_sha256'];report.update(passed=True,pdf=report['final17_pdf'])
 except Exception as e:report['error']=str(e);raise
 finally:
  if opened:
   try:
    with c.desktop_lock():
     for _ in range(6):
      if not any(w.get('class')=='#32768' for w in c.command('inspect')):break
      c.command('keys',keys='{ESC}')
     if pending:
      try:report['cleanup_original_result']=c.script_result(pending,timeout=120)
      except Exception as e:report['cleanup_original_error']=str(e)
     retained=base+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=document_controls.close_saved(c,retained);c.fetch(retained,folder/'failed-retained.pdf')
   except Exception as e:report['cleanup_error']=str(e)
  (folder/'superior.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'superior.json',flush=True)

if __name__=='__main__':main()
