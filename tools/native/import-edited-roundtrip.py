#!/usr/bin/env python3
"""Fresh Reader reopen/weapon edits of Reader and native imported characters.

Compare actual observed native phases, then freshly edit Reader outputs in
native. This is bounded imported Warlock state, not every import or AP equality.
"""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import inspect,script_hashes
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--native-reopen',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);args=p.parse_args()
    reference=json.loads(args.reader.read_text());native=json.loads(args.native_reopen.read_text());ready=json.loads(args.readiness.read_text())
    assert reference['passed'] and native['passed'] and ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
    states={case['label']:case['states'] for case in native['cases']};source=next((ROOT/'Testing').glob('*_2024_*.pdf'))
    folder=ROOT/'output/testing'/('import-edited-roundtrip-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    binary=folder/'mpmb-reader';shutil.copy2(args.native_reopen.parent/'mpmb-reader',binary)
    report={'passed':False,'scope':__doc__,'readiness':str(args.readiness.resolve()),'reader':str(args.reader.resolve()),'native_reopen':str(args.native_reopen.resolve()),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':[]};opened=False;pending=None;remote=None
    fields=list(states['reader'][0]['fields'])
    capture="var iFileName='Imported character persistence observer.js';(function(d){var w=CurrentSpells.warlock,k=classes.known.warlock,r={level:k.level,subclass:k.subclass,cantrips:w.selectCa,spells:w.selectSp,choice:GetFeatureChoice('classes','warlock','eldritch invocations',true),ability:w.ability,excludedSources:CurrentSources.globalExcl,fields:{},sentinel:'\\u00a0\\u2028\\ud83d\\ude00'};"+json.dumps(fields)+".forEach(function(n){try{r.fields[n]=d.getField(n).valueAsString}catch(e){r.fields[n]={getter_error:String(e)}}});Value('PC Name',JSON.stringify(r).replace(/[\\u007f-\\uffff]/g,function(c){return '\\\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"
    inputs=[('reader-import',args.reader.parent/'reader-imported.pdf',states['reader']),('native-edited-import',args.native_reopen.parent/'native-edited.pdf',[states['native'][2],states['native'][1],states['native'][2]])]
    try:
        for label,input_pdf,expected in inputs:
            case={'label':label,'input':str(input_pdf.resolve()),'input_sha256':hashlib.sha256(input_pdf.read_bytes()).hexdigest()};report['cases'].append(case)
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
                remote=c.remote_path('runs/import-roundtrip-'+str(time.time_ns())+'.pdf');case['remote']=remote
                subprocess.run(c.SCP+[str(input_pdf),c.SCP_TARGET + ':MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True)
                opened=True;c.ensure_document(remote);actual=c.script('read',path=remote,fields=fields)['fields'];case['reopened_fields']=actual;assert actual==expected[0]['fields']
                case['edits']=[]
                for weapon,wanted in zip(['Quarterstaff','Eldritch Blast'],expected[1:]):
                    c.script('focus',path=remote,field='Attack.1.Weapon Selection');typed=c.command('paste',value=weapon);assert typed['verified']
                    actual=c.script('read',path=remote,fields=fields)['fields'];case['edits'].append({'weapon':weapon,'paste':typed,'fields':actual});assert actual==wanted['fields']
                c.script('set',path=remote,values={'User Script':capture});pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);case['request']=pending;c.script_result(pending,timeout=90);pending=None
                summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];case['summary']=summary
                c.script('set',path=remote,values={'User Script':''});saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved
                case['close']=c.script('close',path=remote);opened=False;local=c.fetch(remote,folder/(label+'-reader.pdf'));observed=style.saved_capture(local,summary,source);case['captured']=observed
                assert observed['fields']==expected[2]['fields'] and observed['level']==5 and observed['subclass']=='warlock-fiend' and observed['ability']==6
                for key in ['cantrips','spells','choice']:assert sorted(observed[key])==sorted(expected[2][key])
                assert sorted(set(observed['excludedSources']))==sorted(set(reference['captured']['excludedSources']))
                assert inspect(local,observed['fields'])['passed'] and script_hashes(local)==script_hashes(source)
            # Fresh native runtime after genuine Reader edits/save.
            steps=[{'op':'advance','ms':4100},{'op':'assert','values':observed['fields']}]
            for weapon,wanted in zip(['Quarterstaff','Eldritch Blast'],expected[1:]):steps += [{'op':'edit','field':'Attack.1.Weapon Selection','value':weapon},{'op':'advance','ms':1000},{'op':'assert','values':wanted['fields']}]
            final=folder/(label+'-native-after-reader.pdf');steps.append({'op':'save','path':str(final)})
            scenario=folder/(label+'-scenario.json');probe=folder/(label+'-probe.json');scenario.write_text(json.dumps({'steps':steps,'dialogs':[{'result':'ok'}]*15,'alerts':[1]*20}))
            with (folder/(label+'-native.log')).open('w') as log:result=subprocess.run([str(binary),str(local),'--probe',str(scenario),str(probe)],stdout=log,stderr=log,timeout=300)
            data=json.loads(probe.read_text());case['native_after_reader_probe']=str(probe);assert result.returncode==0 and data['passed'],data.get('error')
            assert inspect(final,observed['fields'])['passed'] and script_hashes(final)==script_hashes(source)
            assert hashlib.sha256(input_pdf.read_bytes()).hexdigest()==case['input_sha256'];case['passed']=True
            (folder/'roundtrip.json').write_text(json.dumps(report,indent=2)+'\n')
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
                    if pending:report['original_completion']=c.script_result(pending,timeout=90)
                    retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
            except Exception as error:report['cleanup_error']=str(error)
        (folder/'roundtrip.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'roundtrip.json',flush=True)


if __name__=='__main__':main()
