#!/usr/bin/env python3
"""Bounded Wizard/Warlock shared and Pact Magic progression/removal persistence.

Runs original source and class commands. Invocations, Pact Boons, spell choices,
slot expenditure/rest distinctions and independent Reader parity are unqualified.
"""
import argparse, hashlib, importlib.util, json, shutil, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect, script_hashes
module_spec = importlib.util.spec_from_file_location('subclass_audit', ROOT / 'tools/native/subclass-audit.py')
audit = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(audit)
# Wizard 5 contributes 4/3/2. Pact slots contribute separately at their level.
SLOTS = {0:[4,3,2,0,0],1:[5,3,2,0,0],2:[6,3,2,0,0],3:[4,5,2,0,0],5:[4,3,4,0,0],7:[4,3,2,2,0],9:[4,3,2,0,2],11:[4,3,2,0,3],15:[4,3,2,0,3]}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--fixture', choices=['2014','2024','ashnar'], action='append'); args = parser.parse_args()
    folder = ROOT / 'output/testing' / ('native-pact-multiclass-' + str(time.time_ns())); folder.mkdir()
    binary = folder / 'mpmb-reader'; shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed':False,'scope':__doc__,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':[]}; print(folder, flush=True)
    def run(source, label, dialogs, steps):
        spec, evidence = folder / (label+'-scenario.json'), folder / (label+'-report.json')
        spec.write_text(json.dumps({'dialogs':dialogs,'alerts':[1]*400,'steps':steps}))
        with (folder / (label+'.log')).open('w') as log:
            proc = subprocess.run([str(binary),str(source),'--probe',str(spec),str(evidence)],stdout=log,stderr=log,timeout=420)
        data = json.loads(evidence.read_text()); assert proc.returncode==0 and data['passed'], data.get('error')
        return data, str(evidence)
    try:
        for fixture in args.fixture or ['2014','2024','ashnar']:
            source = next((ROOT/'Testing').glob('Ashnar*.pdf' if fixture=='ashnar' else '*_'+fixture+'_*.pdf')); output=folder/(fixture+'.pdf')
            original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            wizard='Wizard ('+('Abjurer' if fixture=='2024' else 'School of Abjuration')+') 5'
            steps=[{'op':'advance','ms':4100},{'op':'eval','code':"__host.command('resourceDecisionDialog()')"},{'op':'advance','ms':1000},
                   {'op':'eval','code':"__host.command(\"ApplyClasses('',false)\")"},{'op':'advance','ms':1000}]
            steps += [{'op':'edit','field':n,'value':'18'} for n in ['Str','Dex','Con','Int','Wis','Cha']]
            for level in [0,1,2,3,5,7,9,11,15,1,0,3]:
                text=wizard+(' / Warlock (The Fiend) '+str(level) if level else '')
                wizard_key='wizard-abjurer' if fixture=='2024' else 'wizard-abjuration'
                warlock_key='warlock-fiend' if fixture=='2024' else 'warlock-the fiend'
                check="if(!classes.known.wizard||classes.known.wizard.level!==5||classes.known.wizard.subclass!=="+json.dumps(wizard_key)+")throw Error('Wizard identity changed');"
                check += ("if(!classes.known.warlock||classes.known.warlock.level!=="+str(level)+"||classes.known.warlock.subclass!=="+json.dumps(warlock_key)+")throw Error('Warlock identity changed');" if level else "if(classes.known.warlock||CurrentSpells.warlock)throw Error('Removed Warlock caster retained');")
                check += "var slots=[1,2,3,4,5].map(function(i){return Number(What('SpellSlots.CheckboxesSet.lvl'+i))});if(JSON.stringify(slots)!=="+json.dumps(json.dumps(SLOTS[level],separators=(',',':')))+")throw Error('Pact/shared slots differ: '+JSON.stringify(slots));"
                check += "if([6,7,8,9].some(function(i){return Number(What('SpellSlots.CheckboxesSet.lvl'+i))!==0}))throw Error('Mystic Arcanum incorrectly added to slots');"
                check += "var dice={};[1,2,3].forEach(function(i){var die=Number(What('HD'+i+' Die')),n=Number(What('HD'+i+' Level'));if(die&&n)dice[die]=(dice[die]||0)+n});if(dice[6]!==5||Number(dice[8]||0)!=="+str(level)+")throw Error('Multiclass hit dice differ');"
                check += "({warlockLevel:"+str(level)+",slots:slots,dice:dice})"
                steps += [{'op':'eval','code':'__host.command('+json.dumps('ApplyClasses('+json.dumps(text)+',false)')+')'},{'op':'advance','ms':1000},
                          {'op':'assert','values':{'Character Level':str(5+level),'Proficiency Bonus':str(2+(4+level)//4)}},{'op':'eval','code':check}]
            expected={'Character Level':'8','Proficiency Bonus':'3','HD1 Level':'3','HD2 Level':'5'} | {'SpellSlots.CheckboxesSet.lvl'+str(i):str(v) for i,v in enumerate(SLOTS[3],1)}
            steps += [{'op':'save','path':str(output)}]
            data,evidence=run(source,fixture,audit.source_dialogs(fixture)+[{'result':'ok'}]*400,steps)
            independent=inspect(output,expected);assert independent['passed'],independent
            assert script_hashes(output)==script_hashes(source)
            _,reopen=run(output,fixture+'-reopen',[{'result':'ok'}]*60,[{'op':'advance','ms':4100},{'op':'assert','values':expected},{'op':'eval','code':"if(classes.known.warlock.level!==3||classes.known.wizard.level!==5||CurrentSpells.warlock.level!==3)throw Error('Caster progression not retained')"}])
            assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
            report['cases'].append({'fixture':fixture,'passed':True,'probe':evidence,'reopen':reopen,'output':str(output),'expected':expected,'phases':[s['result'] for s in data['stages'] if isinstance(s.get('result'),dict) and 'warlockLevel' in s['result']]})
            (folder/'pact-multiclass.json').write_text(json.dumps(report,indent=2));print(fixture,'Pact/shared slots, progression/removal/native reopen PASS',flush=True)
        report['passed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:
        (folder/'pact-multiclass.json').write_text(json.dumps(report,indent=2));print(folder/'pact-multiclass.json',flush=True)


if __name__=='__main__':
    main()
