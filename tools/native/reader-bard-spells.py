#!/usr/bin/env python3
"""Real offered Bard5 spell inputs, ability changes and explicit regeneration.

Uses original dialog controls and independent ASCII diagnostic snapshots. It
records pre-regeneration healing text instead of assuming it updates itself.
"""
import argparse,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from spells import wait_dialog
from verify import inspect,script_hashes
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
spec=importlib.util.spec_from_file_location('spell_input',ROOT/'tools/native/reader-spell-input.py');spell_input=importlib.util.module_from_spec(spec);spec.loader.exec_module(spell_input)
CANTRIPS=['vicious mockery','mage hand','minor illusion']
SPELLS=['healing word','cure wounds','faerie fire','dissonant whispers','detect magic','invisibility','suggestion','shatter','hypnotic pattern']

def observer(phase,options=False):
 code="var iFileName='Bard spell observation.js';Value('User Script','');(function(d){var r={phase:"+json.dumps(phase)+",selectedCantrips:CurrentSpells.bard.selectCa||[],selectedSpells:CurrentSpells.bard.selectSp||[],fields:{},rows:[],sentinel:'\\u00a0\\u2028\\ud83d\\ude00'};"
 if options:code+="r.cantrips={};r.spells={};"+json.dumps(CANTRIPS)+".forEach(function(k){r.cantrips[k]=spDias.spellSelect.listCa[2][k]});"+json.dumps(SPELLS)+".forEach(function(k){r.spells[k]=spDias.spellSelect.listSp[2][k]});"
 code+="var prefix=What('Template.extras.SSfront').split(',').filter(function(p){return !!p}).slice(-1)[0];r.prefix=prefix||'';r.pages=numPages;if(prefix){['spellshead.ability.0','spellshead.attack.0','spellshead.dc.0'].forEach(function(n){r.fields[prefix+n]=d.getField(prefix+n).valueAsString});for(var i=0;i<100;i++){var name=prefix+'spells.remember.'+i,f=d.getField(name);if(!f)continue;var key=f.valueAsString.split('#')[0];if("+json.dumps(CANTRIPS+SPELLS)+".indexOf(key)>=0){var desc=name.replace('spells.remember.','spells.description.');r.rows.push({key:key,remember:name,description:desc});r.fields[name]=f.valueAsString;r.fields[desc]=d.getField(desc).valueAsString}}}Value('PC Name',JSON.stringify(r).replace(/[\\u007f-\\uffff]/g,function(c){return '\\\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"
 return code

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);a=p.parse_args();ready=json.loads(a.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint();source=a.input.resolve();before=hashlib.sha256(source.read_bytes()).hexdigest();scripts=script_hashes(source);folder=ROOT/'output/testing'/('reader-bard-spells-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);remote=c.remote_path('runs/bard-spells-'+str(time.time_ns())+'.pdf');opened=False;pending=None;report={'passed':False,'scope':__doc__,'input':str(source),'source_sha256':before,'readiness':str(a.readiness),'phases':[]}
 def capture(label,options=False):
  nonlocal remote,pending
  code=observer(label,options);(folder/(label+'-observer.js')).write_text(code);c.script('set',path=remote,values={'User Script':code});pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);c.script_result(pending,timeout=120);pending=None;summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];c.script('set',path=remote,values={'User Script':''});diagnostic=remote[:-4]+'-'+label+'-diagnostic.pdf';c.script('save',path=remote,output=diagnostic);remote=diagnostic;c.script('set',path=remote,values={'PC Name':'Bard compatibility'});saved=remote[:-4]+'-character.pdf';c.script('save',path=remote,output=saved);remote=saved;report['phases'].append({'label':label,'diagnostic':diagnostic,'reader_path':saved,'summary':summary});return report['phases'][-1]
 def generate(select=False,offered=None):
  nonlocal pending
  pending=c.script_submit('call',path=remote,name='GenerateSpellSheet',args=[]);root,elements=wait_dialog('SPELL SELECTION DIALOG',time.monotonic()+90)
  if select:
   report['spell_inputs']=spell_input.type_selection(c,root['handle'],elements,offered,cantrips=CANTRIPS,spells=SPELLS)
   options=[e for e in elements if e.get('owner')==root['handle'] and e.get('class')=='Button' and e.get('name','').startswith('3rd-level and lower spells known')];assert len(options)==1;c.command('invoke',name=options[0]['name'],owner=root['handle'])
  assert any(e.get('owner')==root['handle'] and e.get('name')=='Continue to Next Dialog >>' for e in elements);c.command('invoke',name='Continue to Next Dialog >>',owner=root['handle']);root,elements=wait_dialog('SPELL LIST GENERATION DIALOG',time.monotonic()+90);assert any(e.get('owner')==root['handle'] and e.get('name')=='Generate the Spell Sheet' for e in elements);c.command('invoke',name='Generate the Spell Sheet',owner=root['handle']);c.script_result(pending,timeout=150);pending=None;c.ensure_document(remote)
 try:
  with c.desktop_lock():
   assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()];subprocess.run(c.SCP+[str(source),c.SCP_TARGET + ':MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote);c.script('set',path=remote,values={'PC Name':'Bard compatibility'})
   pending=c.script_submit('call',path=remote,name='GenerateSpellSheet',args=[]);root,elements=wait_dialog('SPELL SELECTION DIALOG',time.monotonic()+90);assert any(e.get('owner')==root['handle'] and e.get('name')=='Cancel and Stop' for e in elements);c.command('invoke',name='Cancel and Stop',owner=root['handle']);report['discovery_cancel']=c.script_result(pending,timeout=120);pending=None;discovery=capture('offered',True)
   # Close/fetch only the diagnostic discovery, proving exact Unicode labels.
   c.script('close',path=remote);opened=False;local=c.fetch(discovery['diagnostic'],folder/'offered-diagnostic.pdf');offered=style.saved_capture(local,discovery['summary'],source);report['offered']=offered;assert all(k in offered[group] and offered[group][k] for group,keys in [('cantrips',CANTRIPS),('spells',SPELLS)] for k in keys);opened=True;c.ensure_document(remote)
   generate(True,offered);capture('selected');c.script('set',path=remote,values={'Cha':'18'});capture('ability-edited');generate();capture('regenerated');c.script('set',path=remote,values={'Cha':'20'});generate();capture('restored');report['close']=c.script('close',path=remote);opened=False
   for phase in report['phases']:
    diag=folder/(phase['label']+'-diagnostic.pdf')
    if not diag.exists():c.fetch(phase['diagnostic'],diag)
    capture_data=style.saved_capture(diag,phase['summary'],source);phase['captured']=capture_data;local=c.fetch(phase['reader_path'],folder/(phase['label']+'.pdf'));phase['pdf']=str(local);assert script_hashes(local)==scripts
    if phase['label']=='offered':continue
    assert sorted(capture_data['selectedCantrips'])==sorted(CANTRIPS) and sorted(capture_data['selectedSpells'])==sorted(SPELLS);assert len(capture_data['rows'])==12;prefix=capture_data['prefix'];modifier=5 if phase['label'] in ['selected','restored'] else 4;assert capture_data['fields'][prefix+'spellshead.attack.0']=='+'+str(3+modifier);assert capture_data['fields'][prefix+'spellshead.dc.0']=='DC '+str(11+modifier);checked=inspect(local,capture_data['fields']);assert checked['actual']==capture_data['fields'] and all(w['matches'] for w in checked['widgets'])
   assert hashlib.sha256(source.read_bytes()).hexdigest()==before;report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:
  if opened:
   try:
    with c.desktop_lock():
     elements=c.command('inspect');dialogs=[e for e in elements if e.get('name') in ['SPELL SELECTION DIALOG','SPELL LIST GENERATION DIALOG']]
     for root in dialogs:
      names={e.get('name') for e in elements if e.get('owner')==root['handle']}
      for button in ['Cancel and Stop','Cancel']:
       if button in names:c.command('invoke',name=button,owner=root['handle']);break
     shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
     if pending:report['original_completion']=c.script_result(pending,timeout=90)
     saved=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=saved);report['cleanup_close']=c.script('close',path=saved);c.fetch(saved,folder/'failed-retained.pdf')
   except Exception as error:report['cleanup_error']=str(error)
  (folder/'spells.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'spells.json',flush=True)
if __name__=='__main__':main()
