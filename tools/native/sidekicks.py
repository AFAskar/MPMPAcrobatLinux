#!/usr/bin/env python3
"""Explicit sidekick conversion, base-creature HD, progression and persistence.

Bandit base inputs are manual as required by MPMB. This qualifies class identity,
HD arithmetic and manual-mode persistence; HP, all feature/tool/skill choices,
spell selection and independent Reader equivalence remain separate coverage.
"""
import argparse,hashlib,json,os,runpy,shutil,subprocess,sys,time
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect,script_hashes
import subclass_audit_qualification as qualification
source_dialogs=runpy.run_path(str(ROOT/'tools/native/subclass-audit.py'))['source_dialogs']
PROFILES=[('sidekick-expert-tcoe','Expert (sidekick)',None,None),('sidekick-warrior-tcoe','Warrior (sidekick)',None,None)]+[('sidekick-spellcaster-tcoe','Spellcaster (sidekick)','sidekick-spellcaster-tcoe-'+s,s.title()) for s in ['mage','healer','prodigy']]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fixture',choices=['2014','2024','ashnar'],action='append');parser.add_argument('--binary',type=Path,default=ROOT/'target/debug/mpmb-reader',help='Copy and qualify an isolated runtime build');args=parser.parse_args()
    folder=ROOT/'output/testing'/('native-sidekicks-'+str(time.time_ns()));folder.mkdir();binary=folder/'mpmb-reader';shutil.copy2(args.binary.resolve(),binary)
    report={'passed':False,'scope':__doc__,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':[],'probe_qualifications':[],'full_mpmb_compatibility':False};print(folder,flush=True)
    def run(source,label,dialogs,alerts,steps):
        scenario,evidence=folder/(label+'-scenario.json'),folder/(label+'-report.json');scenario.write_text(json.dumps({'dialogs':dialogs,'alerts':alerts,'steps':steps}));env=os.environ.copy();env['MPMB_DIALOG_TRACE_DIR']=str(folder/(label+'-dialogs'))
        with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(evidence)],env=env,stdout=log,stderr=log,timeout=300)
        data=json.loads(evidence.read_text());checked=qualification.qualify_probe(proc.returncode,data,label);report['probe_qualifications'].append({'label':label,'evidence':str(evidence),**checked});assert checked['passed'],checked['error'];return data,evidence
    try:
        for fixture in args.fixture or ['2014','2024','ashnar']:
            source=next((ROOT/'Testing').glob('Ashnar*.pdf' if fixture=='ashnar' else '*_'+fixture+'_*.pdf'));original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            for key,label,subkey,subname in PROFILES:
                name=fixture+'-'+(subname or label.split()[0]).lower();output=folder/(name+'.pdf')
                dialogs=source_dialogs(fixture)+[{'title':'CLASS SELECTION DIALOG','event':'r0CD','select':{'r0CD':label}}]
                if subname:dialogs += [{'title':'CLASS SELECTION DIALOG','event':'r0SD','select':{'r0SD':subname}}]
                dialogs += [{'title':'CLASS SELECTION DIALOG','event':'r0LV','values':{'r0LV':'3'}},{'title':'CLASS SELECTION DIALOG','result':'ok'},{'title':'ASK USER DIALOG','header':'Set Base Creature Hit Dice','result':'ok','values':{'r000':'2','r001':'d8'}}]+[{'result':'ok'}]*100
                alerts=([{'title':"Before you get started with MPMB's Character Record Sheet",'button':1}] if fixture!='ashnar' else [])+[{'title':'Creating a Sidekick Works Differently','button':4}]+[1]*100
                steps=[{'op':'advance','ms':4100},{'op':'eval','code':"__host.command('resourceDecisionDialog()')"},{'op':'advance','ms':1000},{'op':'eval','code':"__host.command(\"ApplyClasses('',false)\")"},{'op':'advance','ms':1000}]
                if fixture=='ashnar':dialogs.insert(len(source_dialogs(fixture)),{'title':'CHANGES ALERT DIALOG','result':'ok'})
                steps += [{'op':'edit','field':n,'value':v} for n,v in {'Str':'11','Dex':'12','Con':'12','Int':'10','Wis':'10','Cha':'10'}.items()]
                steps += [{'op':'eval','code':"__host.command('SelectClass()')"},{'op':'advance','ms':1000}]
                verify="if(!classes.known["+json.dumps(key)+"]||classes.known["+json.dumps(key)+"].subclass!=="+json.dumps(subkey or '')+")throw Error('Wrong sidekick role');if(!CurrentVars.manual.race||!CurrentVars.manual.background)throw Error('Sidekick race/background automation must be manual');if(CurrentVars.sidekickHD.toString()!=='2,8')throw Error('Wrong base creature HD');"
                steps += [{'op':'eval','code':verify+"var chosenSidekick=What('Class and Levels');"},{'op':'assert','values':{'Character Level':'3','Proficiency Bonus':'2','HD1 Level':'4','HD1 Die':'8'}},{'op':'edit','field':'Race','value':'Human'},{'op':'edit','field':'Background','value':'Bandit (CR 1/8)'},{'op':'edit','field':'Extra.Notes','value':'Base creature: Bandit, speaks Common, 2d8 HD. Base proficiencies and attacks require manual entry.'}]
                for level in [1,5,11,17,20,3]:
                    code='__host.command("ApplyClasses("+JSON.stringify(chosenSidekick.replace(/\\s*\\d+\\s*$/,\'\')+\' '+str(level)+'\')+",false)")'
                    steps += [{'op':'eval','code':code},{'op':'advance','ms':1000},{'op':'eval','code':verify},{'op':'assert','values':{'Character Level':str(level),'Proficiency Bonus':str(2+(level-1)//4),'HD1 Level':str(level+1),'HD1 Die':'8'}}]
                steps += [{'op':'save','path':str(output)}]
                data,evidence=run(source,name,dialogs,alerts,steps)
                expected={'Character Level':'3','Proficiency Bonus':'2','HD1 Level':'4','HD1 Die':'8','Race':'Human','Background':'Bandit (CR 1/8)'}
                assert inspect(output,{k:v for k,v in expected.items() if k!='HD1 Die'})['passed']
                die=inspect(output,{'HD1 Die':'8'});assert die['actual']['HD1 Die']=='8'
                assert all(w['matches'] and (not w['visible'] or (w['appearance'] and w['appearance_text']=='d8+1')) for w in die['widgets']), 'Hit-die display must include the base creature Constitution modifier'
                assert script_hashes(output)==script_hashes(source)
                _,reopened=run(output,name+'-reopen',[{'result':'ok'}]*30,[1]*30,[{'op':'advance','ms':4100},{'op':'eval','code':verify},{'op':'assert','values':expected}])
                assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
                report['cases'].append({'fixture':fixture,'class':key,'subclass':subkey,'passed':True,'probe':str(evidence),'reopen':str(reopened),'output':str(output),'expected':expected,'displayed':{'HD1 Die':'d8+1'},'base_creature':'Bandit (CR 1/8), manual base proficiencies/attacks still unqualified'})
                (folder/'sidekicks.json').write_text(json.dumps(report,indent=2));print(name,'explicit conversion/HD/progression/reopen PASS',flush=True)
        assert len(report['cases'])==len(args.fixture or ['2014','2024','ashnar'])*len(PROFILES),'Incomplete profile set'
        assert len(report['probe_qualifications'])==2*len(report['cases']) and all(p['passed'] for p in report['probe_qualifications']),'Creation and reopen must both have clean diagnostics'
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:(folder/'sidekicks.json').write_text(json.dumps(report,indent=2));print(folder/'sidekicks.json',flush=True)

if __name__=='__main__':main()
