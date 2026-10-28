#!/usr/bin/env python3
"""Rune Scribe prestige progression, shared slots, hit dice, removal and native reopen.

Wizard (Abjuration) 5 supplies the required prior character levels. Abilities
and Arcana proficiency are explicit inputs; the narrative rune/NPC prerequisite
is assumed. Rune choices, Mastery/ASI decisions and Reader parity are unqualified.
The 2024 fixture has no predefined Rune Scribe and is outside this profile.
"""
import argparse, hashlib, importlib.util, json, shutil, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import canonical_fields, inspect, script_hashes
module_spec = importlib.util.spec_from_file_location('subclass_audit', ROOT / 'tools/native/subclass-audit.py')
audit = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(audit)
SLOTS = {1: [4,3,3,0,0], 2: [4,3,3,1,0], 3: [4,3,3,2,0], 4: [4,3,3,3,1], 5: [4,3,3,3,2], 0: [4,3,2,0,0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--fixture', choices=['2014', 'ashnar'], action='append'); args = parser.parse_args()
    folder = ROOT / 'output/testing' / ('native-rune-scribe-' + str(time.time_ns())); folder.mkdir()
    binary = folder / 'mpmb-reader'; shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'cases': []}; print(folder, flush=True)
    def run(source, label, dialogs, steps):
        spec, evidence = folder / (label + '-scenario.json'), folder / (label + '-report.json')
        spec.write_text(json.dumps({'dialogs': dialogs, 'alerts': [1] * 300, 'steps': steps}))
        with (folder / (label + '.log')).open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(spec), str(evidence)], stdout=log, stderr=log, timeout=300)
        data = json.loads(evidence.read_text()); assert proc.returncode == 0 and data['passed'], data.get('error')
        return data, str(evidence)
    try:
        for fixture in args.fixture or ['2014', 'ashnar']:
            source = next((ROOT / 'Testing').glob('Ashnar*.pdf' if fixture == 'ashnar' else '*_2014_*.pdf'))
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest(); output = folder / (fixture + '-rune.pdf')
            steps = [{'op':'advance','ms':4100}, {'op':'eval','code':"__host.command('resourceDecisionDialog()')"}, {'op':'advance','ms':1000},
                     {'op':'eval','code':"if(ClassList['rune scribe'].prestigeClassPrereq!==5||ClassList['rune scribe'].die!==8||ClassList['rune scribe'].spellcastingFactor!==1)throw Error('Unexpected Rune Scribe definition');__host.command(\"ApplyClasses('',false)\")"}, {'op':'advance','ms':1000}]
            steps += [{'op':'edit','field':n,'value':'18'} for n in ['Str','Dex','Con','Int','Wis','Cha']]
            steps += [{'op':'eval','code':"__host.command(\"ApplyClasses('Wizard (School of Abjuration) 5',false)\")"}, {'op':'advance','ms':1000}]
            steps += [{'op':'edit','field':n,'value':'18'} for n in ['Str','Dex','Con','Int','Wis','Cha']]
            steps += [{'op':'eval','code':"if(!getField('Arc Prof').isBoxChecked(0))__host.activate('Arc Prof');if(!getField('Arc Prof').isBoxChecked(0)||classes.known.wizard.subclass!=='wizard-abjuration')throw Error('Qualifying wizard/Arcana input missing');"}]
            for index, level in enumerate([1,2,3,4,5,1,0,3]):
                text = 'Wizard (School of Abjuration) 5' + (' / Rune Scribe ' + str(level) if level else '')
                check = ("if(!classes.known['rune scribe']||classes.known['rune scribe'].level!==" + str(level) + ")throw Error('Wrong Rune Scribe level');" if level else "if(classes.known['rune scribe'])throw Error('Rune Scribe not removed');")
                check += "if(classes.known.wizard.level!==5||!getField('Arc Prof').isBoxChecked(0)||Number(What('Dex'))<13||Number(What('Int'))<13)throw Error('Prestige base class/abilities changed');"
                check += "var dice={};[1,2,3].forEach(function(i){var die=Number(What('HD'+i+' Die')),n=Number(What('HD'+i+' Level'));if(die&&n)dice[die]=(dice[die]||0)+n});if(dice[6]!==5||Number(dice[8]||0)!==" + str(level) + ")throw Error('Hit dice do not match both classes');"
                check += "var slots=[1,2,3,4,5].map(function(i){return Number(What('SpellSlots.CheckboxesSet.lvl'+i))});if(JSON.stringify(slots)!==" + json.dumps(json.dumps(SLOTS[level],separators=(',',':'))) + ")throw Error('Shared multiclass slots differ');({phase:" + str(index) + ",runeLevel:" + str(level) + ",dice:dice,slots:slots})"
                steps += [{'op':'eval','code':'__host.command(' + json.dumps('ApplyClasses(' + json.dumps(text) + ',false)') + ')'}, {'op':'advance','ms':1000},
                          {'op':'assert','values':{'Character Level':str(5+level),'Proficiency Bonus':str(2+(4+level)//4)}}, {'op':'eval','code':check}]
            expected = {'Character Level':'8','Proficiency Bonus':'3','HD1 Level':'3','HD2 Level':'5'} | {'SpellSlots.CheckboxesSet.lvl'+str(i):str(v) for i,v in enumerate(SLOTS[3],1)}
            steps += [{'op':'save','path':str(output)}]
            data, evidence = run(source, fixture, audit.source_dialogs(fixture) + [{'result':'ok'}]*300, steps)
            independent = inspect(output, expected); assert independent['passed'], independent
            saved_fields = canonical_fields(PdfReader(output)); assert saved_fields['HD1 Die']['/V']=='8' and saved_fields['HD2 Die']['/V']=='6'
            assert script_hashes(output) == script_hashes(source)
            _, reopen = run(output, fixture+'-reopen', [{'result':'ok'}]*40, [{'op':'advance','ms':4100},{'op':'assert','values':expected},{'op':'eval','code':"if(classes.known['rune scribe'].level!==3||classes.known.wizard.level!==5)throw Error('Multiclass state not retained')"}])
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
            report['cases'].append({'fixture':fixture,'passed':True,'probe':evidence,'reopen':reopen,'output':str(output),'expected':expected,'phases':[s['result'] for s in data['stages'] if isinstance(s.get('result'),dict) and 'runeLevel' in s['result']]})
            (folder/'rune-scribe.json').write_text(json.dumps(report,indent=2)); print(fixture,'Rune Scribe progression/slots/dice/removal/reopen PASS',flush=True)
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error); raise
    finally:
        (folder/'rune-scribe.json').write_text(json.dumps(report,indent=2)); print(folder/'rune-scribe.json',flush=True)


if __name__ == '__main__':
    main()
