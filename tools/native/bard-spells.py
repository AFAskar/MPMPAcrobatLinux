#!/usr/bin/env python3
"""Selected Bard5 spells, ability changes, generation and edited native reopens.

Original offered controls and callbacks populate CurrentSpells. Reader parity,
other lists/choices and slot expenditure remain separate requirements.
"""
import argparse,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect,script_hashes
CANTRIPS=['vicious mockery','mage hand','minor illusion']
SPELLS=['healing word','cure wounds','faerie fire','dissonant whispers','detect magic','invisibility','suggestion','shatter','hypnotic pattern']

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);a=p.parse_args();source=a.input.resolve();source_hash=hashlib.sha256(source.read_bytes()).hexdigest();scripts=script_hashes(source);folder=ROOT/'output/testing'/('native-bard-spells-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary);report={'passed':False,'scope':__doc__,'source':str(source),'source_sha256':source_hash,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'phases':[]}
 def probe(label,pdf,steps,dialogs):
  scenario=folder/(label+'.json');evidence=folder/(label+'-probe.json');scenario.write_text(json.dumps({'dialogs':dialogs,'alerts':[1]*30,'steps':steps}))
  with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(pdf),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=360)
  data=json.loads(evidence.read_text());assert proc.returncode==0 and data['passed'] and not data['diagnostics']['errors'],data.get('error') or data['diagnostics']['errors'];return data
 def capture(label,dc,attack,modifier):
  code="(function(){var wanted="+json.dumps(CANTRIPS+SPELLS)+",r={phase:"+json.dumps(label)+",cantrips:CurrentSpells.bard.selectCa.slice().sort(),spells:CurrentSpells.bard.selectSp.slice().sort(),fields:{},rows:[]},prefix=What('Template.extras.SSfront').split(',').filter(Boolean).slice(-1)[0];if(!prefix)throw Error('Missing spell page');r.prefix=prefix;r.pages=numPages;['spellshead.ability.0','spellshead.attack.0','spellshead.dc.0'].forEach(function(n){r.fields[prefix+n]=getField(prefix+n).valueAsString});__host.names.forEach(function(n){if(n.indexOf(prefix+'spells.remember.')===0){var key=String(What(n)).split('#')[0];if(wanted.indexOf(key)>=0){var desc=n.replace('spells.remember.','spells.description.');r.rows.push({key:key,remember:n,description:desc});r.fields[n]=getField(n).valueAsString;r.fields[desc]=getField(desc).valueAsString}}});if(JSON.stringify(r.cantrips)!=="+json.dumps(json.dumps(sorted(CANTRIPS),separators=(',',':')))+"||JSON.stringify(r.spells)!=="+json.dumps(json.dumps(sorted(SPELLS),separators=(',',':')))+")throw Error('Selected list changed');if(r.rows.length!==wanted.length||wanted.some(function(k){return r.rows.filter(function(n){return n.key===k}).length!==1}))throw Error('Generated rows missing or duplicate');if(r.fields[prefix+'spellshead.dc.0']!=="+json.dumps(dc)+"||r.fields[prefix+'spellshead.attack.0']!=="+json.dumps(attack)+")throw Error('Derived spell header differs');r.rows.forEach(function(row){var text=r.fields[row.description];if(row.key==='vicious mockery'&&!/2d6/.test(text))throw Error('Cantrip scale differs');if((row.key==='healing word'||row.key==='cure wounds')&&text.indexOf("+json.dumps('+'+str(modifier)+' (Cha)' if modifier is not None else '')+")<0)throw Error('Healing modifier differs')});return r})()"
  return {'op':'eval','code':code}
 def check(pdf,state):
  checked=inspect(pdf,state['fields']);assert checked['actual']==state['fields'] and checked['widgets'] and all(w['matches'] for w in checked['widgets']);assert script_hashes(pdf)==scripts
 def generate():return [{'op':'eval','code':"__host.command('GenerateSpellSheet()')"},{'op':'advance','ms':1000}]
 try:
  discovery=probe('discovery',source,[{'op':'advance','ms':4100}]+generate()+[{'op':'eval','code':"({cantrips:spDias.spellSelect.listCa[2],spells:spDias.spellSelect.listSp[2]})"}],[{'title':'SPELL SELECTION DIALOG','result':'cancel'}]);maps=discovery['stages'][-1]['result'];report['offered']={'cantrips':{k:maps['cantrips'][k] for k in CANTRIPS},'spells':{k:maps['spells'][k] for k in SPELLS}}
  selected={**{'Ca'+str(i).zfill(2):maps['cantrips'][key] for i,key in enumerate(CANTRIPS,1)},**{'Sp'+str(i).zfill(2):maps['spells'][key] for i,key in enumerate(SPELLS,1)}};selection={'title':'SPELL SELECTION DIALOG','result':'ok','select':selected,'values':{'SpR1':True,'SpR2':False,'SpR3':False,'SpR4':False}};generation={'title':'SPELL LIST GENERATION DIALOG','result':'ok'};keep={'title':'SPELL SELECTION DIALOG','result':'ok'};first=folder/'selected.pdf';edited=folder/'ability-edited.pdf';regenerated=folder/'regenerated.pdf'
  steps=[{'op':'advance','ms':4100},{'op':'edit','field':'PC Name','value':'Bard compatibility'}]+generate()+[capture('selected', 'DC 16','+8',5),{'op':'save','path':str(first)},{'op':'edit','field':'Cha','value':'18'},{'op':'advance','ms':1000},capture('ability-edited','DC 15','+7',None),{'op':'save','path':str(edited)}]+generate()+[capture('regenerated','DC 15','+7',4),{'op':'save','path':str(regenerated)}];data=probe('workflow',source,steps,[selection,generation,keep,generation]);states=[s['result'] for s in data['stages'] if isinstance(s.get('result'),dict) and 'phase' in s['result']]
  for pdf,state in zip([first,edited,regenerated],states):check(pdf,state);report['phases'].append({'pdf':str(pdf),'state':state})
  final=folder/'reopened-restored.pdf';data=probe('reopen',regenerated,[{'op':'advance','ms':4100},capture('loaded','DC 15','+7',4),{'op':'edit','field':'Cha','value':'20'},{'op':'advance','ms':1000},capture('restored-before-regeneration','DC 16','+8',None)]+generate()+[capture('restored','DC 16','+8',5),{'op':'save','path':str(final)}],[keep,generation]);state=data['stages'][-2]['result'];check(final,state);report['phases'].append({'pdf':str(final),'state':state});assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash;report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'spells.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'spells.json',flush=True)
if __name__=='__main__':main()
