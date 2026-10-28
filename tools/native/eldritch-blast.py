#!/usr/bin/env python3
"""Original legacy Agonizing Blast menu, attacks, progression and persistence.

Covers 2014/Ashnar only. The 2024 cantrip-specific invocation model, other
invocations, spell-page text and independent Reader parity remain unqualified.
"""
import hashlib, importlib.util, json, shutil, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect, script_hashes
module_spec=importlib.util.spec_from_file_location('audit',ROOT/'tools/native/subclass-audit.py')
audit=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(audit)
CHOICE='agonizing blast (prereq: eldritch blast cantrip)'
FIELDS=['Attack.1.Weapon','Attack.1.Weapon Selection','Attack.1.To Hit','Attack.1.Damage','Character Level','Proficiency Bonus','Cha','Cha Mod']
CHANGED={'title':'CHANGES ALERT DIALOG','result':'ok'}


def main():
    folder=ROOT/'output/testing'/('native-eldritch-blast-'+str(time.time_ns()));folder.mkdir()
    binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
    report={'passed':False,'scope':__doc__,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':[]};print(folder,flush=True)
    def run(source,label,dialogs,steps):
        scenario,evidence=folder/(label+'-scenario.json'),folder/(label+'-report.json');scenario.write_text(json.dumps({'dialogs':dialogs,'alerts':[1]*100,'steps':steps}))
        with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=300)
        data=json.loads(evidence.read_text());assert proc.returncode==0 and data['passed'],data.get('error');return data,str(evidence)
    def menu(selected):return {'title':'MPMB menu','button_path':['Warlock (the Fiend)','Eldritch Invocation (selected '+str(selected)+' of 3)','[improves Eldritch Blast]','Agonizing Blast (prereq: Eldritch Blast cantrip)']}
    def choose():return [{'op':'eval','code':"__host.activate('Class Features Menu')"},{'op':'advance','ms':1000}]
    def capture(phase,damage,hit,selected):
        expected=[CHOICE] if selected else []
        return [{'op':'assert','values':{'Attack.1.Damage':damage,'Attack.1.To Hit':'+'+str(hit)}},
                {'op':'eval','code':"var choice=GetFeatureChoice('classes','warlock','eldritch invocations',true);if(JSON.stringify(choice)!=="+json.dumps(json.dumps(expected,separators=(',',':')))+")throw Error('Wrong invocation selection');({phase:"+json.dumps(phase)+",choice:choice,fields:(function(){var o={};"+json.dumps(FIELDS)+".forEach(n=>o[n]=getField(n).valueAsString);return o})()})"}]
    try:
        for fixture,pattern in [('2014','*_2014_*.pdf'),('ashnar','Ashnar*.pdf')]:
            source=next((ROOT/'Testing').glob(pattern));original_hash=hashlib.sha256(source.read_bytes()).hexdigest();output=folder/(fixture+'.pdf')
            steps=[{'op':'advance','ms':4100},{'op':'eval','code':"__host.command('resourceDecisionDialog()')"},{'op':'advance','ms':1000}]
            steps += [{'op':'edit','field':n,'value':'18'} for n in ['Str','Dex','Con','Int','Wis','Cha']]
            steps += [{'op':'eval','code':"__host.command(\"ApplyClasses('Warlock (The Fiend) 5',false)\")"},{'op':'advance','ms':1000},{'op':'edit','field':'Attack.1.Weapon Selection','value':'Eldritch Blast'},{'op':'advance','ms':1000}]
            steps += capture('baseline','2×1d10',7,False)+choose()+capture('selected','2×1d10+4',7,True)
            steps += choose()+capture('removed','2×1d10',7,False)+choose()+capture('reselected','2×1d10+4',7,True)
            steps += [{'op':'edit','field':'Cha','value':'20'},{'op':'advance','ms':1000}]+capture('charisma','2×1d10+5',8,True)
            for level,damage,hit in [(11,'3×1d10+5',9),(20,'4×1d10+5',11),(5,'2×1d10+5',8)]:
                steps += [{'op':'eval','code':'__host.command('+json.dumps('ApplyClasses("Warlock (The Fiend) '+str(level)+'",false)')+')'},{'op':'advance','ms':1000}]+capture('level-'+str(level),damage,hit,True)
            steps += [{'op':'save','path':str(output)}]
            dialogs=audit.source_dialogs(fixture)+[CHANGED,menu(0),CHANGED,menu(1),CHANGED,menu(0),CHANGED]+[CHANGED]*10
            data,evidence=run(source,fixture,dialogs,steps)
            phases={s['result']['phase']:s['result'] for s in data['stages'] if isinstance(s.get('result'),dict) and 'phase' in s['result']}
            expected=phases['level-5']['fields'];assert inspect(output,expected)['passed'];assert script_hashes(output)==script_hashes(source)
            _,reopen=run(output,fixture+'-reopen',[menu(1),CHANGED,menu(0),CHANGED],
                         [{'op':'advance','ms':4100},{'op':'assert','values':expected}]+capture('reopened','2×1d10+5',8,True)+choose()+capture('reopened-remove','2×1d10',8,False)+choose()+capture('reopened-readd','2×1d10+5',8,True))
            assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
            report['cases'].append({'fixture':fixture,'passed':True,'source':str(source),'output':str(output),'probe':evidence,'reopen':reopen,'phases':phases,'expected':expected})
            (folder/'eldritch-blast.json').write_text(json.dumps(report,indent=2));print(fixture,'original invocation menu/attacks/progression/persistence PASS',flush=True)
        report['passed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:
        (folder/'eldritch-blast.json').write_text(json.dumps(report,indent=2));print(folder/'eldritch-blast.json',flush=True)


if __name__=='__main__':main()
