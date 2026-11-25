#!/usr/bin/env python3
"""Original Reader invocation gestures, regeneration, removal and readdition.

Uses exact accessible labels and guarded popup pointer input, never preselected
return values. Checks bounded 2024 Fiend Warlock state against native phases;
other invocations/classes and complete rendering remain unqualified.
"""
import argparse,importlib.util,json,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from spells import wait_dialog
from verify import inspect,script_hashes
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
OBSERVER=r"""var iFileName='Warlock invocation state observer.js';(function(d){var w=CurrentSpells.warlock,k=classes.known.warlock,r={identity:{level:k.level,subclass:k.subclass},choice:GetFeatureChoice('classes','warlock','eldritch invocations',true),cantrips:w.selectCa,spells:w.selectSp,excludedSources:CurrentSources.globalExcl,fields:{},generated:[],sentinel:'\u00a0\u2028\ud83d\ude00'};['Class and Levels','Character Level','Proficiency Bonus','Attack.1.To Hit','Attack.1.Damage'].forEach(function(n){r.fields[n]=d.getField(n).valueAsString});var a=What('Template.extras.SSfront').split(','),p='';for(var i=0;i<a.length;i++)if(a[i])p=a[i];for(var n=0;n<100;n++){var rn=p+'spells.remember.'+n,f=d.getField(rn);if(f&&/^eldritch blast##/.test(f.valueAsString)){var dn=p+'spells.description.'+n;r.generated.push({remember:rn,description:dn});r.fields[rn]=f.valueAsString;r.fields[dn]=d.getField(dn).valueAsString;}}Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""


def popup(label,folder):
    deadline=time.monotonic()+15
    while True:
        state=c.command('inspect_focused')
        (folder/'last-popup.json').write_text(json.dumps({'wanted':label,'observed':state},indent=2)+'\n')
        if state['in_reader'] and state['type']=='ControlType.Menu' and state['class']=='#32768' and any(item.get('name','').split('\t')[0].strip()==label for item in state.get('children',[])):return state
        assert time.monotonic()<deadline, 'Expected offered popup item: '+label


def select_invocation(remote,count,folder,report):
    pending=c.script_submit('call',path=remote,name='ClassFeatureOptions',args=[]);report['pending_request']=pending
    steps=[]
    try:
        for label in ['Warlock (Fiend Patron)',f'Eldritch Invocation (selected {count} of 5)','[upgrades Eldritch Blast]','Agonizing Blast: Eldritch Blast']:
            menu=popup(label,folder);children=menu['children']
            matches=[(i,item) for i,item in enumerate(children) if item['type']=='ControlType.MenuItem' and item['name'].split('\t')[0].strip()==label]
            assert len(matches)==1, 'Missing or ambiguous offered popup label: '+label
            index,item=matches[0]
            action=c.command('activate_menu',owner=menu['native_window_handle'],position=index,name=item['name'])
            steps.append({'menu':menu,'chosen':item,'action':action})
            (folder/'menu-steps.json').write_text(json.dumps(steps,indent=2)+'\n')
        return pending,steps
    except Exception:
        # Cancel only actual observed popup windows; never replay a selection.
        for _ in range(5):
            if not any(e.get('class')=='#32768' for e in c.command('inspect')):break
            c.command('keys',keys='{ESC}')
        try:c.script_result(pending,timeout=20)
        except Exception:pass
        raise


def regenerate(remote,folder,report):
    pending=c.script_submit('call',path=remote,name='GenerateSpellSheet',args=[]);report['pending_request']=pending
    try:
        root,elements=wait_dialog('SPELL SELECTION DIALOG',time.monotonic()+90)
        assert any(e.get('owner')==root['handle'] and e.get('name')=='Continue to Next Dialog >>' for e in elements)
        c.command('invoke',name='Continue to Next Dialog >>',owner=root['handle'])
        root,elements=wait_dialog('SPELL LIST GENERATION DIALOG',time.monotonic()+90)
        assert any(e.get('owner')==root['handle'] and e.get('name')=='Generate the Spell Sheet' for e in elements)
        c.command('invoke',name='Generate the Spell Sheet',owner=root['handle'])
        result=c.script_result(pending,timeout=120);report.pop('pending_request',None);return result
    except Exception:
        elements=c.command('inspect');buttons=[e for e in elements if e.get('class')=='Button' and e.get('name','').startswith('Cancel')]
        if len(buttons)==1:c.command('invoke',name=buttons[0]['name'],owner=buttons[0]['owner'])
        try:c.script_result(pending,timeout=20)
        except Exception:pass
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);args=p.parse_args()
    reader=json.loads(args.reader.read_text());native=json.loads(args.native.read_text());ready=json.loads(args.readiness.read_text());assert reader['passed'] and native['passed'] and ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
    assert native['source_profile']=='original startup defaults'
    folder=ROOT/'output/testing'/('reader-warlock-invocations-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    report={'passed':False,'scope':__doc__,'readiness':str(args.readiness.resolve()),'native':str(args.native.resolve()),'phases':{}};opened=False;remote=c.remote_path('runs/warlock-invocations-'+str(time.time_ns())+'.pdf');report['reader_path']=remote
    source=next((ROOT/'Testing').glob('*_2024_*.pdf'))
    def capture(phase):
        nonlocal remote
        c.script('set',path=remote,values={'User Script':OBSERVER});pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);report['pending_request']=pending;c.script_result(pending,timeout=90);report.pop('pending_request',None)
        summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];c.script('set',path=remote,values={'User Script':''})
        saved=remote[:-4]+'-'+phase+'.pdf';c.script('save',path=remote,output=saved);remote=saved
        # Snapshot the actual saved file without altering it. Fetch after final
        # Reader shutdown for independent checks and ASCII transport validation.
        report['phases'][phase]={'remote':saved,'summary':summary}
        (folder/'invocations.json').write_text(json.dumps(report,indent=2)+'\n')
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP+[reader['selected_pdf'],c.SCP_TARGET + ':MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True)
            opened=True;c.ensure_document(remote);capture('selected-spells')
            for phase,count in [('invocation',0),('removed',1),('readded',0)]:
                phase_folder=folder/phase;phase_folder.mkdir()
                pending,steps=select_invocation(remote,count,phase_folder,report)
                report[phase+'-menu']=steps;report[phase+'-completion']=c.script_result(pending,timeout=120);report.pop('pending_request',None)
                report[phase+'-generation']=regenerate(remote,phase_folder,report);capture(phase)
            report['close']=c.script('close',path=remote);opened=False
            for phase,data in report['phases'].items():
                local=c.fetch(data['remote'],folder/(phase+'.pdf'));observed=style.saved_capture(local,data['summary'],source);data['captured']=observed;data['pdf']=str(local)
                expected=native['phases'][phase];assert len(observed['generated'])==1
                desc=observed['fields'][observed['generated'][0]['description']]
                native_desc=[v for n,v in expected['fields'].items() if 'spells.description.' in n];assert len(native_desc)==1
                normalize=lambda value:value.replace('\r\n','\n').replace('\r','\n')
                checks={'identity':observed['identity']=={'level':5,'subclass':'warlock-fiend'},'choice':observed['choice']==expected['choice'],'cantrips':sorted(observed['cantrips'])==sorted(expected['cantrips']),'spells':sorted(observed['spells'])==sorted(expected['spells']),'source_sets':sorted(set(observed['excludedSources']))==sorted(set(expected['excludedSources'])),'attacks':all(observed['fields'][n]==expected['fields'][n] for n in ['Attack.1.To Hit','Attack.1.Damage']),'description_line_endings_normalized':normalize(desc)==normalize(native_desc[0])}
                data['checks']=checks;assert all(checks.values()), {phase:checks}
                assert inspect(local,observed['fields'])['passed'] and script_hashes(local)==script_hashes(source)
            report['passed']=True
    except Exception as error:
        report['error']=str(error)
        if opened:
            try:shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
            except Exception as diagnostic:report['diagnostic_error']=str(diagnostic)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    for _ in range(5):
                        if not any(e.get('class')=='#32768' for e in c.command('inspect')):break
                        c.command('keys',keys='{ESC}')
                    if report.get('pending_request'):
                        try:report['cleanup_original_completion']=c.script_result(report['pending_request'],timeout=30)
                        except Exception as error:report['cleanup_original_error']=str(error)
                    saved=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=saved);report['cleanup_close']=c.script('close',path=saved);c.fetch(saved,folder/'failed-retained.pdf')
            except Exception as error:report['cleanup_error']=str(error)
        (folder/'invocations.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'invocations.json',flush=True)


if __name__=='__main__':main()
