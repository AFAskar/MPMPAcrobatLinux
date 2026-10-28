#!/usr/bin/env python3
"""2024 selected Warlock spells, cantrip-specific invocation and regenerated pages.

Uses offered original spell/feature controls. Reader parity, other spell lists,
other invocations and slot expenditure/rest workflows remain unqualified.
"""
import hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect,script_hashes
m=importlib.util.spec_from_file_location('audit',ROOT/'tools/native/subclass-audit.py');audit=importlib.util.module_from_spec(m);m.loader.exec_module(audit)
CANTRIPS=['eldritch blast','mage hand','minor illusion']
SPELLS=['hex','armor of agathys','misty step','counterspell','fly','hunger of hadar']
CHOICE='agonizing blast: eldritch blast'
CHANGED={'title':'CHANGES ALERT DIALOG','result':'ok'}


def main():
    folder=ROOT/'output/testing'/('native-warlock-spells-'+str(time.time_ns()));folder.mkdir();binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
    source=next((ROOT/'Testing').glob('*_2024_*.pdf'));original_hash=hashlib.sha256(source.read_bytes()).hexdigest();output=folder/'2024.pdf'
    report={'passed':False,'scope':__doc__,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()};print(folder,flush=True)
    def run(label,steps,dialogs,pdf=source):
        spec,evidence=folder/(label+'-scenario.json'),folder/(label+'-report.json');spec.write_text(json.dumps({'steps':steps,'dialogs':dialogs,'alerts':[1]*100}))
        with (folder/(label+'.log')).open('w') as log:r=subprocess.run([str(binary),str(pdf),'--probe',str(spec),str(evidence)],stdout=log,stderr=log,timeout=300)
        data=json.loads(evidence.read_text());assert r.returncode==0 and data['passed'],data.get('error');return data,str(evidence)
    def setup():
        return [{'op':'advance','ms':4100},{'op':'eval','code':"__host.command('resourceDecisionDialog()')"},{'op':'advance','ms':1000}]+[{'op':'edit','field':n,'value':'18'} for n in ['Str','Dex','Con','Int','Wis','Cha']]+[{'op':'eval','code':"__host.command(\"ApplyClasses('Warlock (The Fiend) 5',false)\")"},{'op':'advance','ms':1000},{'op':'edit','field':'Attack.1.Weapon Selection','value':'Eldritch Blast'},{'op':'advance','ms':1000}]
    def generate():return [{'op':'eval','code':"__host.command('GenerateSpellSheet()')"},{'op':'advance','ms':1000}]
    def menu(selected):return {'title':'MPMB menu','button_path':['Warlock (Fiend Patron)','Eldritch Invocation (selected '+str(selected)+' of 5)','[upgrades Eldritch Blast]','Agonizing Blast: Eldritch Blast']}
    def choose():return [{'op':'eval','code':"__host.activate('Class Features Menu')"},{'op':'advance','ms':1000}]
    def capture(phase,selected):
        expected=[CHOICE] if selected else []
        code="if(JSON.stringify(CurrentSpells.warlock.selectCa.slice().sort())!=="+json.dumps(json.dumps(sorted(CANTRIPS),separators=(',',':')))+"||JSON.stringify(CurrentSpells.warlock.selectSp.slice().sort())!=="+json.dumps(json.dumps(sorted(SPELLS),separators=(',',':')))+")throw Error('Selected spell list changed');"
        code+="var choice=GetFeatureChoice('classes','warlock','eldritch invocations',true);if(JSON.stringify(choice)!=="+json.dumps(json.dumps(expected,separators=(',',':')))+")throw Error('Invocation selection differs');"
        code+="var fields={},prefix=What('Template.extras.SSfront').split(',').filter(Boolean).slice(-1)[0];if(!prefix)throw Error('Missing generated spell page');var rows=__host.names.filter(n=>n.startsWith(prefix+'spells.remember.')&&String(What(n)).startsWith('eldritch blast##'));if(rows.length!==1)throw Error('Expected exactly one generated Eldritch Blast row');var description=rows[0].replace('spells.remember.','spells.description.');"
        code+="['Attack.1.To Hit','Attack.1.Damage',description,rows[0]].forEach(n=>fields[n]=getField(n).valueAsString);if(fields['Attack.1.To Hit']!=='+7'||fields['Attack.1.Damage']!=="+json.dumps('2×1d10+4' if selected else '2×1d10')+")throw Error('Invocation attack effect differs');"
        code+=("if(!/1d10\\s*\\+\\s*4/.test(fields[description]))throw Error('Generated cantrip lacks Charisma damage');" if selected else "if(/1d10\\s*\\+\\s*4/.test(fields[description]))throw Error('Generated cantrip retained removed invocation damage');")
        code+="({phase:"+json.dumps(phase)+",choice:choice,prefix:prefix,fields:fields,cantrips:CurrentSpells.warlock.selectCa,spells:CurrentSpells.warlock.selectSp})"
        return {'op':'eval','code':code}
    try:
        # Discover exact invisible sort prefixes from the offered original dialog,
        # then cancel. No manufactured option labels or selection IDs.
        data,discovery=run('options',setup()+generate()+[{'op':'eval','code':"({cantrips:spDias.spellSelect.listCa[2],spells:spDias.spellSelect.listSp[2]})"}],audit.source_dialogs('2024')+[CHANGED,{'title':'SPELL SELECTION DIALOG','result':'cancel'}])
        maps=data['stages'][-1]['result'];report['option_discovery']=discovery
        selection={**{'Ca'+str(i).zfill(2):maps['cantrips'][n] for i,n in enumerate(CANTRIPS,1)},**{'Sp'+str(i).zfill(2):maps['spells'][n] for i,n in enumerate(SPELLS,1)}}
        select={'title':'SPELL SELECTION DIALOG','result':'ok','select':selection,'values':{'SpR1':True,'SpR2':False,'SpR3':False,'SpR4':False}}
        generation={'title':'SPELL LIST GENERATION DIALOG','result':'ok'}
        keep={'title':'SPELL SELECTION DIALOG','result':'ok'}
        steps=setup()+generate()+[capture('selected-spells',False)]+choose()+generate()+[capture('invocation',True)]+choose()+generate()+[capture('removed',False)]+choose()+generate()+[capture('readded',True),{'op':'save','path':str(output)}]
        dialogs=audit.source_dialogs('2024')+[CHANGED,select,generation,menu(0),CHANGED,keep,generation,menu(1),CHANGED,keep,generation,menu(0),CHANGED,keep,generation]
        data,evidence=run('workflow',steps,dialogs);phases={s['result']['phase']:s['result'] for s in data['stages'] if isinstance(s.get('result'),dict) and 'phase' in s['result']};expected=phases['readded']['fields']
        assert inspect(output,expected)['passed'];assert script_hashes(output)==script_hashes(source)
        _,reopen=run('reopen',[{'op':'advance','ms':4100},{'op':'assert','values':expected},capture('reopened',True)],[{'result':'ok'}]*30,output)
        assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
        report.update(passed=True,probe=evidence,reopen=reopen,output=str(output),phases=phases,expected=expected)
    except Exception as error:report['error']=str(error);raise
    finally:(folder/'warlock-spells.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'warlock-spells.json',flush=True)


if __name__=='__main__':main()
