#!/usr/bin/env python3
"""Original Bard1 instrument choices and inspiration through real Reader controls.

Only the observed Bard/Tools dialog's three named initial edits are filled.
Further class/skill/subclass choices are not qualified by this case.
"""
import argparse,hashlib,importlib.util,json,re,subprocess,sys,time
from pypdf import PdfReader
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import canonical_fields
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
CHOICES=['Flute','Lute','Drum']

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--phase',choices=['create','edit','read'],default='create');a=p.parse_args();ready=json.loads(a.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
 source=a.input.resolve();folder=ROOT/'output/testing'/('reader-bard-resources-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);script='tDoc.__bardPhase='+json.dumps(a.phase)+';\n'+(ROOT/'tools/native/bard-resource-observer.js').read_text();frozen=folder/'observer.js';frozen.write_text(script)
 remote=c.remote_path('runs/bard-resources-'+str(time.time_ns())+'.pdf');opened=False;pending=None;report={'passed':False,'scope':__doc__,'input':str(source),'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'observer':str(frozen.resolve()),'observer_sha256':hashlib.sha256(script.encode()).hexdigest(),'phase':a.phase,'decisions':[],'readiness':str(a.readiness.resolve())}
 try:
  with c.desktop_lock():
   assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()],'Pre-existing Reader document'
   subprocess.run(c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote);c.script('set',path=remote,values={'User Script':script});pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);report['request']=pending;deadline=time.monotonic()+150
   while time.monotonic()<deadline:
    elements=c.command('inspect')
    if any(e.get('name','').startswith('MPMB_RESULT') for e in elements):break
    dialogs=[e for e in elements if e.get('class')=='#32770'];asks=[e for e in dialogs if e.get('name')=='ASK USER DIALOG']
    if asks:
     assert a.phase=='create' and not report['decisions'],'Unexpected repeated Bard choice';assert len(asks)==1;owner=asks[0]['handle'];labels={e.get('name','') for e in elements if e.get('owner')==owner};assert {'Select proficiencies','Tools','Bard'}<=labels,labels
     controls=[e for e in elements if e.get('owner')==owner and e.get('class') in ['RICHEDIT50W','Edit'] and e.get('enabled') and e.get('read_only') is False and e['rect'][2]>0 and e['rect'][3]>0];live=[(e,c.command('dialog_control',owner=owner,handle=e['handle'])) for e in controls];assert len(live)==3,live
     entries=[]
     for index,value in enumerate(CHOICES,1):
      expected='Musical instrument ('+str(index)+'/3)';matches=[(e,state) for e,state in live if state['text']==expected];assert len(matches)==1,live;control,before=matches[0];focus=c.command('focus_control',owner=owner,handle=control['handle']);assert focus['focused'];paste=c.command('paste',value=value);assert paste['verified'] and paste['value']==value;after=c.command('dialog_control',owner=owner,handle=control['handle']);assert after['text']==value;entries.append({'control':control,'before':before,'value':value,'after':after,'focus':focus,'paste':paste})
     shot=c.command('screenshot');c.fetch(shot['path'],folder/'instruments.png');fresh=c.command('inspect');buttons=[e for e in fresh if e.get('owner')==owner and e.get('class')=='Button' and e.get('name')=='OK' and e.get('enabled')];assert len(buttons)==1;c.command('invoke',name=buttons[0]['name'],owner=owner);report['decisions'].append({'dialog':'ASK USER DIALOG','source':'Bard','kind':'Tools','entries':entries})
    elif any(e.get('name')=='CHANGES ALERT DIALOG' for e in dialogs):break
    elif dialogs:raise AssertionError('Unexpected dialog: '+str([(e.get('name'),e.get('handle')) for e in dialogs]))
    else:time.sleep(.1)
   else:raise TimeoutError('Original Bard request did not finish')
   report['completion']=c.script_result(pending,timeout=120);pending=None
   if a.phase=='create':
    report['ready_states']=[]
    def ready_state(label):
     report['ready_states'].append({'label':label,'fields':c.script('read',path=remote,fields=names)['fields']})
    # Every read/set/call checks initialization/calculation readiness separately.
    names=['Class and Levels','Character Level','Proficiency Bonus','Cha','Cha Mod','MoreProficiencies']+['Tool '+str(i) for i in range(1,7)]+['SpellSlots.CheckboxesSet.lvl'+str(i) for i in range(1,10)]
    resources=c.script('read',path=remote,fields=[name for name in canonical_fields(PdfReader(source)) if re.fullmatch(r'Limited Feature \d+',name)])['fields'];matches=[int(name.rsplit(' ',1)[1]) for name,value in resources.items() if 'bardic inspiration' in value.lower()];assert len(matches)==1;row=matches[0];names+=[prefix+str(row) for prefix in ['Limited Feature ','Limited Feature Max Usages ','Limited Feature Recovery ','Limited Feature Used ']];report['resource_row']=row
    ready_state('Charisma18');c.script('set',path=remote,values={'Cha':'10'});ready_state('Charisma10');c.script('set',path=remote,values={'Limited Feature Used '+str(row):'1'});c.script('call',path=remote,name='resetLimFeaUsed',args=['short rest']);ready_state('short rest');c.script('call',path=remote,name='resetLimFeaUsed',args=['long rest']);ready_state('long rest');c.script('set',path=remote,values={'Cha':'20'});ready_state('Charisma20')
   summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['summary']=summary;c.script('set',path=remote,values={'User Script':''});saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved;report['close']=c.script('close',path=remote);opened=False;local=c.fetch(remote,folder/'reader.pdf');report['captured']=style.saved_capture(local,summary,source);capture=report['captured'];assert not capture['errors'] and all(capture['assertions'].values()),capture
   if a.phase=='create':
    assert len(report['decisions'])==1;states={s['label']:s['fields'] for s in report['ready_states']};maximum='Limited Feature Max Usages '+str(report['resource_row']);used='Limited Feature Used '+str(report['resource_row']);assert [states[k][maximum] for k in ['Charisma18','Charisma10','Charisma20']]==['4','1','5'];assert states['short rest'][used]=='1' and states['long rest'][used]==''
   elif a.phase=='edit':assert capture['states'][-1]['resource']['maximum']=='3'
   assert hashlib.sha256(source.read_bytes()).hexdigest()==report['input_sha256'];report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:
  if opened:
   try:
    with c.desktop_lock():
     elements=c.command('inspect');asks=[e for e in elements if e.get('name')=='ASK USER DIALOG' and e.get('class')=='#32770']
     for root in asks:
      buttons=[e for e in elements if e.get('owner')==root['handle'] and e.get('class')=='Button' and e.get('name')=='Cancel' and e.get('enabled')]
      if len(buttons)==1:c.command('invoke',name='Cancel',owner=root['handle'])
     shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
     if pending:report['original_completion']=c.script_result(pending,timeout=90)
     retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
   except Exception as error:report['cleanup_error']=str(error)
  (folder/'observation.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'observation.json',flush=True)

if __name__=='__main__':main()
