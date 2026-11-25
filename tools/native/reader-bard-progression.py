#!/usr/bin/env python3
"""Original Bard/Lore progression, rests, down-level and removal in Reader.

Starts from a qualified Bard1 save with real instruments. ASI, expertise/skill
and spell-selection choices are not covered by this progression/resource case.
"""
import argparse,hashlib,importlib.util,json,re,subprocess,sys,time
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import canonical_fields,script_hashes,inspect
spec=importlib.util.spec_from_file_location('field_state',ROOT/'tools/native/field-state-comparison.py');field_state=importlib.util.module_from_spec(spec);spec.loader.exec_module(field_state)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);a=p.parse_args();qualification=json.loads(a.readiness.read_text());assert qualification['passed'] and len(qualification['cases'])==24 and qualification['harness_sha256']==c.harness_fingerprint();source=a.input.resolve();source_hash=hashlib.sha256(source.read_bytes()).hexdigest();scripts=script_hashes(source);inventory=canonical_fields(PdfReader(source));folder=ROOT/'output/testing'/('reader-bard-progression-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
 wanted=['Class and Levels','Character Level','Proficiency Bonus','Class Features','Cha','Cha Mod','Dex','Dex Mod','Int','Int Mod','Acr Bonus','Arc Bonus','Jack of All Trades']+['Tool '+str(i) for i in range(1,7)]+['SpellSlots.CheckboxesSet.lvl'+str(i) for i in range(1,10)]
 names=[n for n in wanted if n in inventory]+sorted(n for n in inventory if re.fullmatch(r'Limited Feature(?: Max Usages| Recovery| Used)? \d+',n));remote=c.remote_path('runs/bard-progression-'+str(time.time_ns())+'.pdf');opened=False;pending=None;report={'passed':False,'scope':__doc__,'input':str(source),'input_sha256':source_hash,'readiness':str(a.readiness),'names':names,'phases':[]}
 def checkpoint():
  (folder/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
 def capture(label):
  nonlocal remote
  values=c.script('read',path=remote,fields=names)['fields'];saved=remote[:-4]+'-'+label+'.pdf';c.script('save',path=remote,output=saved);remote=saved;report['phases'].append({'label':label,'fields':values,'reader_path':saved});checkpoint();return values
 def apply(class_input):
  nonlocal pending
  pending=c.script_submit('call',path=remote,name='ApplyClasses',args=[class_input,False]);deadline=time.monotonic()+120
  while time.monotonic()<deadline:
   elements=c.command('inspect')
   if any(e.get('name','').startswith('MPMB_RESULT') for e in elements) or any(e.get('name')=='CHANGES ALERT DIALOG' for e in elements):break
   unexpected=[e for e in elements if e.get('class')=='#32770'];assert not unexpected,'Unqualified progression choice: '+str([(e.get('name'),e.get('handle')) for e in unexpected]);time.sleep(.1)
  else:raise TimeoutError('Progression request did not finish')
  result=c.script_result(pending,timeout=120);pending=None;c.ensure_document(remote);return result
 try:
  with c.desktop_lock():
   assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()],'Pre-existing Reader document';subprocess.run(c.SCP+[str(source),c.SCP_TARGET + ':MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote)
   c.script('set',path=remote,values={'Str':'10','Dex':'14','Con':'12','Int':'12','Wis':'13'});initial=capture('level1')
   report['level5_completion']=apply('Bard (College of Lore) 5');high=capture('lore5');matches=[int(n.rsplit(' ',1)[1]) for n,v in high.items() if re.fullmatch(r'Limited Feature \d+',n) and 'bardic inspiration' in v.lower()];assert len(matches)==1;row=matches[0];report['resource_row']=row;maximum='Limited Feature Max Usages '+str(row);used='Limited Feature Used '+str(row);recovery='Limited Feature Recovery '+str(row)
   assert high['Character Level']=='5' and high['Proficiency Bonus']=='3' and high[maximum]=='5' and 'd8' in high['Limited Feature '+str(row)];assert [high['SpellSlots.CheckboxesSet.lvl'+str(i)] for i in [1,2,3]]==['4','3','2'];assert high['Jack of All Trades']=='True'
   c.script('set',path=remote,values={used:'1'});c.script('call',path=remote,name='resetLimFeaUsed',args=['short rest']);rest=capture('short-rest5');assert rest[used]==''
   report['downlevel_completion']=apply('Bard 1');low=capture('level1-again');assert low['Character Level']=='1' and low['Proficiency Bonus']=='2' and low[maximum]=='5' and low[recovery]=='long rest' and 'd6' in low['Limited Feature '+str(row)];assert [low['SpellSlots.CheckboxesSet.lvl'+str(i)] for i in [1,2,3]]==['2','0','0'];assert [low['Tool '+str(i)] for i in [1,2,3]]==['Flute','Lute','Drum']
   report['removal_completion']=apply('');removed=capture('removed');assert not any('bardic inspiration' in str(v).lower() for n,v in removed.items() if re.fullmatch(r'Limited Feature \d+',n));assert all(removed['Tool '+str(i)]=='' for i in [1,2,3]);assert [removed['SpellSlots.CheckboxesSet.lvl'+str(i)] for i in [1,2,3]]==['0','0','0']
   report['close']=c.script('close',path=remote);opened=False
   for phase in report['phases']:
    local=c.fetch(phase['reader_path'],folder/(phase['label']+'.pdf'));phase['pdf']=str(local);phase['api_raw_comparison']=field_state.compare(local,phase['fields']);assert script_hashes(local)==scripts;phase['canonical_widgets_scripts']=True
   assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash;report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:
  if opened:
   try:
    with c.desktop_lock():
     shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
     if pending:report['original_completion']=c.script_result(pending,timeout=90)
     saved=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=saved);report['cleanup_close']=c.script('close',path=saved);c.fetch(saved,folder/'failed-retained.pdf')
   except Exception as error:report['cleanup_error']=str(error)
  (folder/'progression.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'progression.json',flush=True)
if __name__=='__main__':main()
