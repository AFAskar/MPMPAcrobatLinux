#!/usr/bin/env python3
"""Original companion, wild-shape and spell-generation workflows; immutable local evidence."""
import hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from pypdf import PdfReader
from verify import canonical_fields,inspect,script_hashes

def main():
 folder=ROOT/'output/testing'/('native-generated-'+str(time.time_ns()));folder.mkdir(parents=True);binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary);report={'passed':False,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':[]}
 def run(pdf,spec,label):
  scenario=folder/(label+'-scenario.json');evidence=folder/(label+'-report.json');scenario.write_text(json.dumps(spec))
  with (folder/(label+'.log')).open('w') as log:
   result=subprocess.run([str(binary),str(pdf),'--probe',str(scenario),str(evidence)],cwd=ROOT,stdout=log,stderr=log,timeout=360)
  data=json.loads(evidence.read_text());assert result.returncode==0 and data['passed'] and not data['diagnostics']['errors'],(label,data.get('error'),data.get('diagnostics',{}).get('errors'))
  return data,evidence
 try:
  for rule in ['2014','2024']:
   source=next((ROOT/'Testing').glob('*_'+rule+'_*.pdf'));original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
   for workflow in ['companion','wildshape','spells']:
    label=workflow+'-'+rule;output=folder/('native-'+label+'.pdf');steps=[{'op':'advance','ms':4100}];dialogs=[{'result':'ok','title':'SOURCE SELECTION DIALOG'}]
    if workflow!='companion':
     for name,value in {'Str':'10','Dex':'10','Con':'10','Int':'14','Wis':'16','Cha':'10'}.items():steps.append({'op':'edit','field':name,'value':value})
     cl='Druid (Circle of the Moon) 2' if rule=='2014' else 'Druid 2'
     steps += [{'op':'eval','code':'__host.command('+json.dumps('ApplyClasses('+json.dumps(cl)+',false)')+')'},{'op':'advance','ms':1000}];dialogs.append({'result':'ok','title':'CHANGES ALERT DIALOG'})
    if workflow=='companion':
     steps += [{'op':'eval','code':"var pageBefore=numPages;var generatedPrefix=DoTemplate('AScomp','Add',null,true);ApplyCompRace('wolf',generatedPrefix);if(numPages!==pageBefore+1)throw Error('Unexpected companion page count')"},{'op':'advance','ms':1000}]
     suffixes={'Comp.Race':'wolf','Comp.Use.Ability.Str.Score':'12' if rule=='2014' else '14'};page="getField(generatedPrefix+'Comp.Race').page";extras='AScomp'
    elif workflow=='wildshape':
     steps += [{'op':'eval','code':"var pageBefore=numPages;var generatedPrefix=DoTemplate('WSfront','Add',null,true);__host.edit(generatedPrefix+'Wildshape.Race.1','wolf');if(numPages!==pageBefore+1)throw Error('Unexpected wild-shape page count')"},{'op':'advance','ms':1000}]
     suffixes={'Wildshape.Race.1':'wolf','Wildshape.1.Ability.Str.Score':'12' if rule=='2014' else '14'};page="getField(generatedPrefix+'Wildshape.Race.1').page";extras='WSfront'
    else:
     dialogs += [{'title':'SPELL SELECTION DIALOG','event':'SpR1','values':{'SpR1':True,'SpR2':False,'SpR3':False,'SpR4':False}},{'title':'SPELL SELECTION DIALOG','result':'ok'},{'title':'SPELL LIST GENERATION DIALOG','result':'ok'}]
     steps += [{'op':'eval','code':"__host.command('GenerateSpellSheet()');var generatedPrefix=What('Template.extras.SSfront').split(',').filter(Boolean).slice(-1)[0];if(!generatedPrefix)throw Error('Missing generated spell page');if(!__host.names.some(n=>n.startsWith(generatedPrefix+'spells.remember.')&&String(What(n)).startsWith('cure wounds##')))throw Error('Missing Cure Wounds')"},{'op':'advance','ms':1000}]
     suffixes={'spellshead.dc.0':'DC 13','spellshead.attack.0':'+5'};page="getField(generatedPrefix+'spells.name.0').page";extras='SSfront'
    steps += [{'op':'eval','code':''.join('if(getField(generatedPrefix+'+json.dumps(k)+').valueAsString!=='+json.dumps(v)+')throw Error('+json.dumps('Unexpected '+k)+');' for k,v in suffixes.items())},{'op':'render','page_eval':page,'path':str(folder/(label+'.ppm'))},{'op':'save','path':str(output)}]
    data,evidence=run(source,{'dialogs':dialogs,'alerts':[1]*6,'steps':steps},label)
    fields=canonical_fields(PdfReader(output));prefix=[p for p in fields['Template.extras.'+extras]['/V'].split(',') if p][-1];expected={prefix+k:v for k,v in suffixes.items()}
    independent=inspect(output,expected);assert independent['passed'],independent;assert script_hashes(output)==script_hashes(source)
    (folder/(label+'-independent.json')).write_text(json.dumps(independent,indent=2))
    _,reopen=run(output,{'alerts':[1]*3,'steps':[{'op':'advance','ms':4100},{'op':'assert','values':expected}]},label+'-reopen')
    case={'ruleset':rule,'workflow':workflow,'passed':True,'output':str(output),'prefix':prefix,'expected':expected,'probe':str(evidence),'reopen':str(reopen),'pages':len(PdfReader(output).pages),'fields':len(fields),'repairs':data['diagnostics'].get('repairs',[])};report['cases'].append(case)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash;print(label,'PASS',flush=True)
    (folder/'generated.json').write_text(json.dumps(report,indent=2))
  report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'generated.json').write_text(json.dumps(report,indent=2));print(folder/'generated.json',flush=True)
if __name__=='__main__':main()
