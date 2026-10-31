#!/usr/bin/env python3
"""Edit/rest/save imported 2014 Ashnar in native, Reader, then native again.

Only actual Ki usage is entered. Original resetLimFeaUsed calculates short/long
rest effects. Check imported payloads, remembered spells, selected serialized
state, canonical fields/AP/scripts and input hashes; no full rendering claim.
Optional armor checks force changed-save/fresh-reopen/restore of the original
formula field in native before and after actual Reader formula edits.
"""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from pypdf import PdfReader
from verify import canonical_fields,inspect,script_hashes
spec=importlib.util.spec_from_file_location('state',ROOT/'tools/native/compare-state.py');state=importlib.util.module_from_spec(spec);spec.loader.exec_module(state)


def retained_state(before,after):
    left,right=[canonical_fields(PdfReader(path)) for path in [before,after]]
    names=['User_Imported_Files.Stringified','CurrentFeatureChoices.Stringified','CurrentSpells.Stringified']
    expressions={n:[left[n]['/V'],right[n]['/V']] for n in names}
    run=subprocess.run(['node','-e',state.COMPARE],input=json.dumps(expressions),text=True,capture_output=True,check=True,timeout=30)
    result=json.loads(run.stdout)
    remembered=[n for n in left if '.spells.remember.' in n.lower()]
    assert remembered
    result['remembered_rows']={'equal':all(n in right and left[n]['/V']==right[n]['/V'] for n in remembered),'count':len(remembered)}
    assert all(row['equal'] for row in result.values()),result
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--reader',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--check-armor-format',action='store_true');args=p.parse_args()
    reference=json.loads(args.reader.read_text());execution=json.loads((args.native/'execution.json').read_text());ready=json.loads(args.readiness.read_text())
    assert reference['passed'] and reference['profile']=='legacy' and execution['profile']=='legacy'
    assert '_2014_' in reference['target_fixture'] and ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
    baseline=reference['captured']['fields'];assert baseline['Limited Feature 1']=='Ki Points' and baseline['Limited Feature Max Usages 1']=='12' and baseline['Limited Feature Recovery 1']=='short rest'
    folder=ROOT/'output/testing'/('legacy-import-resource-roundtrip-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(args.native/'mpmb-reader',binary)
    report={'passed':False,'scope':__doc__,'native':str(args.native.resolve()),'reader':str(args.reader.resolve()),'readiness':str(args.readiness.resolve()),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'check_armor_format':args.check_armor_format,'cases':[]};opened=False;remote=None
    def publish():(folder/'roundtrip.json').write_text(json.dumps(report,indent=2)+'\n')
    def probe(source,label,steps):
        scenario=folder/(label+'-scenario.json');evidence=folder/(label+'-probe.json');scenario.write_text(json.dumps({'steps':steps,'dialogs':[{'result':'ok'}]*10,'alerts':[1]*20}))
        with (folder/(label+'.log')).open('w') as log:run=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=300)
        result=json.loads(evidence.read_text());assert run.returncode==0 and result['passed'],result.get('error')
        return result
    def armor_display(path,value,display):
        result=inspect(path,{'AC Armor Bonus':value});widgets=[w for w in result['widgets'] if w['visible']]
        assert result['actual']['AC Armor Bonus']==value and widgets
        assert all(w['matches'] and w['appearance'] and w['appearance_text']==display for w in widgets),widgets
        return {'canonical':value,'decoded_display':[w['appearance_text'] for w in widgets]}
    def rebuild_armor(source,label,resource_expected):
        changed=folder/(label+'-armor-changed.pdf');restored=folder/(label+'-armor-restored.pdf')
        probe(source,label+'-armor-change',[{'op':'advance','ms':4100},{'op':'edit','field':'AC Armor Bonus','value':'11+Wis'},{'op':'advance','ms':1000},{'op':'assert','values':resource_expected|{'AC':'25'}},{'op':'save','path':str(changed)}])
        changed_display=armor_display(changed,'11+Wis','16')
        # Freshly reopen the changed AP: restoring cannot reuse the old15 AP.
        probe(changed,label+'-armor-restore',[{'op':'advance','ms':4100},{'op':'assert','values':{'AC Armor Bonus':'11+Wis','AC':'25'}},{'op':'edit','field':'AC Armor Bonus','value':'10+Wis'},{'op':'advance','ms':1000},{'op':'assert','values':resource_expected},{'op':'save','path':str(restored)}])
        restored_display=armor_display(restored,'10+Wis','15')
        assert script_hashes(restored)==script_hashes(source)
        return restored,{'changed':changed_display,'fresh_reopen_restored':restored_display}
    def capture(phase):return {'op':'eval','code':'({phase:'+json.dumps(phase)+',fields:(function(){var out={};'+json.dumps(list(baseline))+'.forEach(function(n){out[n]=getField(n).valueAsString});return out})()})'}
    try:
        for label,input_pdf in [('native-import',args.native/'native.pdf'),('reader-import',args.reader.parent/'reader-imported.pdf')]:
            case={'label':label,'input':str(input_pdf.resolve()),'input_sha256':hashlib.sha256(input_pdf.read_bytes()).hexdigest()};report['cases'].append(case);publish()
            used='Limited Feature Used 1';steps=[{'op':'advance','ms':4100},{'op':'assert','values':baseline},capture('baseline')]
            for value,phase,rest in [('2','used-two','short rest'),('3','used-three','long rest'),('4','saved-four',None)]:
                steps += [{'op':'edit','field':used,'value':value},{'op':'advance','ms':1000},capture(phase)]
                if rest:steps += [{'op':'eval','code':'__host.command('+json.dumps('resetLimFeaUsed('+json.dumps(rest)+')')+')'},{'op':'advance','ms':1000},capture(rest)]
            edited=folder/(label+'-native.pdf');steps.append({'op':'save','path':str(edited)});result=probe(input_pdf,label,steps)
            phases={s['result']['phase']:s['result']['fields'] for s in result['stages'] if isinstance(s.get('result'),dict) and 'phase' in s['result']};case['native_phases']=phases
            assert phases['used-two'][used]=='2' and phases['used-three'][used]=='3' and phases['saved-four'][used]=='4'
            assert phases['short rest'][used]==phases['long rest'][used]==''
            expected=phases['saved-four'];assert inspect(edited,expected)['passed'] and script_hashes(edited)==script_hashes(input_pdf);case['native_retained_state']=retained_state(input_pdf,edited)
            probe(edited,label+'-native-reopen',[{'op':'advance','ms':4100},{'op':'assert','values':expected}])
            if args.check_armor_format:
                case['native_initial_armor']=armor_display(edited,'10+Wis','15')
                edited,case['native_armor_rebuild']=rebuild_armor(edited,label+'-before-reader',expected)
            publish()
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
                remote=c.remote_path('runs/legacy-resource-'+str(time.time_ns())+'.pdf');subprocess.run(c.SCP+[str(edited),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True)
                opened=True;c.ensure_document(remote);case['reader_reopened']=c.script('read',path=remote,fields=list(expected))['fields'];assert case['reader_reopened']==expected
                case['reader_phases']={}
                for value,phase,rest in [('2','used-two','short rest'),('3','used-three','long rest'),('4','saved-four',None)]:
                    c.script('focus',path=remote,field=used);typed=c.command('paste',value=value);assert typed['verified']
                    actual=c.script('read',path=remote,fields=list(expected))['fields'];case['reader_phases'][phase]=actual;assert actual==phases[phase]
                    if rest:
                        c.script('call',path=remote,name='resetLimFeaUsed',args=[rest]);actual=c.script('read',path=remote,fields=list(expected))['fields'];case['reader_phases'][rest]=actual;assert actual==phases[rest]
                    publish()
                if args.check_armor_format:
                    field='AC Armor Bonus';c.script('focus',path=remote,field=field);assert c.command('paste',value='11+Wis')['verified']
                    case['reader_changed_armor']=c.script('read',path=remote,fields=[field,'AC'])['fields'];assert case['reader_changed_armor']=={field:'11+Wis','AC':'25'}
                    changed_remote=remote[:-4]+'-armor-changed.pdf';c.script('save',path=remote,output=changed_remote);remote=changed_remote
                    changed_local=c.fetch(remote,folder/(label+'-reader-armor-changed.pdf'));case['reader_changed_armor_display']=armor_display(changed_local,'11+Wis','16')
                    c.script('focus',path=remote,field=field);assert c.command('paste',value='10+Wis')['verified']
                    case['reader_restored_armor']=c.script('read',path=remote,fields=[field,'AC'])['fields'];assert case['reader_restored_armor']=={field:'10+Wis','AC':'24'}
                saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved;case['close']=c.script('close',path=remote);opened=False;local=c.fetch(remote,folder/(label+'-reader.pdf'))
            assert inspect(local,expected)['passed'] and script_hashes(local)==script_hashes(input_pdf);case['reader_retained_state']=retained_state(input_pdf,local)
            final=folder/(label+'-native-after-reader.pdf');probe(local,label+'-native-after-reader',[{'op':'advance','ms':4100},{'op':'assert','values':expected},{'op':'edit','field':used,'value':'5'},{'op':'advance','ms':1000},{'op':'assert','values':{used:'5'}},{'op':'save','path':str(final)}])
            assert inspect(final,expected|{used:'5'})['passed'] and script_hashes(final)==script_hashes(input_pdf)
            if args.check_armor_format:
                case['reader_restored_armor_display']=armor_display(local,'10+Wis','15')
                case['native_after_reader_armor']=armor_display(final,'10+Wis','15')
                final,case['after_reader_armor_rebuild']=rebuild_armor(final,label+'-after-reader',expected|{used:'5'})
            case['final_output']=str(final);case['final_retained_state']=retained_state(input_pdf,final);assert hashlib.sha256(input_pdf.read_bytes()).hexdigest()==case['input_sha256'];case['passed']=True;publish()
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png');retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
            except Exception as error:report['cleanup_error']=str(error)
        publish();print(folder/'roundtrip.json',flush=True)


if __name__=='__main__':main()
