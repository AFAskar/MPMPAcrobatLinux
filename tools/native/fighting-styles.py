#!/usr/bin/env python3
"""Exercise original class-feature menus and derived attack changes/persistence.

This covers Archery/Dueling and three attack states per fixture, not all class options.
Reader equivalence is a separate required qualification.
"""
import hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect, script_hashes


def main():
    folder=ROOT/'output/testing'/('native-fighting-styles-'+str(time.time_ns()));folder.mkdir()
    binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
    report={'passed':False,'scope':__doc__,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':[]};print(folder,flush=True)
    def run(source,label,dialogs,steps):
        scenario,evidence=folder/(label+'-scenario.json'),folder/(label+'-report.json');scenario.write_text(json.dumps({'dialogs':dialogs,'alerts':[1]*30,'steps':steps}))
        with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=300)
        data=json.loads(evidence.read_text());assert proc.returncode==0 and data['passed'],data.get('error');return data,evidence
    def menu(style):return {'title':'MPMB menu','button_path':['Champion','Fighting Style',style]}
    changed={'title':'CHANGES ALERT DIALOG','result':'ok'}
    fields=['Attack.1.Weapon','Attack.1.Weapon Selection','Attack.1.To Hit','Attack.1.Damage','Character Level','Proficiency Bonus']
    def capture(phase):return {'op':'eval','code':"({phase:"+json.dumps(phase)+",choice:GetFeatureChoice('classes','fighter','fighting style'),fields:(function(){var o={};"+json.dumps(fields)+".forEach(n=>o[n]=getField(n).valueAsString);return o})()})"}
    def choose():return [{'op':'eval','code':"__host.activate('Class Features Menu')"},{'op':'advance','ms':1000}]
    try:
        for fixture,pattern in [('2014','*_2014_*.pdf'),('2024','*_2024_*.pdf'),('ashnar','Ashnar*.pdf')]:
            source=next((ROOT/'Testing').glob(pattern));original_hash=hashlib.sha256(source.read_bytes()).hexdigest();output=folder/(fixture+'-styles.pdf')
            dialogs=([{'title':'SOURCE SELECTION DIALOG','result':'ok'}] if fixture!='ashnar' else [])+[changed,menu('Archery'),changed,menu('Dueling'),changed]
            steps=[{'op':'advance','ms':4100}]+[{'op':'edit','field':n,'value':'18'} for n in ['Str','Dex','Con','Int','Wis','Cha']]
            steps += [{'op':'eval','code':'__host.command(\'ApplyClasses("Fighter (Champion) 5",false)\')'},{'op':'advance','ms':1000},{'op':'edit','field':'Attack.1.Weapon Selection','value':'Longbow'}]
            steps += choose()+[capture('bow-archery'),{'op':'eval','code':"if(Number(What('Attack.1.To Hit'))!==9||What('Attack.1.Damage')!=='1d8+4')throw Error('Archery must give +2 to ranged attacks');"}]
            steps += choose()+[capture('bow-dueling'),{'op':'eval','code':"if(Number(What('Attack.1.To Hit'))!==7||What('Attack.1.Damage')!=='1d8+4')throw Error('Dueling must remove Archery without boosting ranged damage');"},{'op':'edit','field':'Attack.1.Weapon Selection','value':'Longsword'},{'op':'advance','ms':1000},capture('sword-dueling'),{'op':'eval','code':"if(Number(What('Attack.1.To Hit'))!==7||What('Attack.1.Damage')!=='1d8+6')throw Error('Dueling must give +2 to one-handed longsword damage');"},{'op':'save','path':str(output)}]
            data,evidence=run(source,fixture,dialogs,steps)
            phases={s['result']['phase']:s['result'] for s in data['stages'] if isinstance(s.get('result'),dict) and 'phase' in s['result']}
            assert [phases[p]['choice'] for p in ['bow-archery','bow-dueling','sword-dueling']]==['archery','dueling','dueling']
            expected=phases['sword-dueling']['fields'];assert inspect(output,expected)['passed']
            assert script_hashes(output)==script_hashes(source)
            reopened,reopen_evidence=run(output,fixture+'-reopen',[menu('Archery'),changed,menu('Dueling'),changed],[{'op':'advance','ms':4100},{'op':'assert','values':expected},capture('reopened')]+choose()+[{'op':'assert','values':{'Attack.1.Damage':'1d8+4'}}]+choose()+[{'op':'assert','values':{'Attack.1.Damage':'1d8+6'}}])
            retained=next(s['result'] for s in reopened['stages'] if isinstance(s.get('result'),dict) and s['result'].get('phase')=='reopened');assert retained['choice']=='dueling'
            assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
            report['cases'].append({'fixture':fixture,'passed':True,'source':str(source),'output':str(output),'probe':str(evidence),'reopen':str(reopen_evidence),'phases':phases,'expected':expected})
            (folder/'fighting-styles.json').write_text(json.dumps(report,indent=2));print(fixture,'original feature menus/attack changes/save/reopen PASS',flush=True)
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:(folder/'fighting-styles.json').write_text(json.dumps(report,indent=2));print(folder/'fighting-styles.json',flush=True)

if __name__=='__main__':main()
