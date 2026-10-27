#!/usr/bin/env python3
"""Independently compare original Fighter style commands and attack effects in Reader.

Reader executes original ClassFeatureOptions through the serialized application
menu. Native evidence exercises the original field popup; this suite does not
qualify Reader popup interaction or all fighting-style choices.
"""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import inspect,script_hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('native_report',type=Path);parser.add_argument('--readiness',type=Path,required=True);args=parser.parse_args()
    native=json.loads(args.native_report.read_text());qualification=json.loads(args.readiness.read_text());assert native['passed'] and qualification['passed'] and len(qualification['cases'])==24
    folder=args.native_report.resolve().parent/('reader-fighting-styles-'+str(time.time_ns()));folder.mkdir();report={'passed':False,'scope':__doc__,'readiness':str(args.readiness.resolve()),'cases':[]};print(folder,flush=True)
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Reference suite requires no pre-existing document'
            for case in native['cases']:
                fixture=case['fixture'];reference='ashnar.pdf' if fixture=='ashnar' else 'blank-'+fixture+'.pdf';path=c.remote_path('runs/style-reference-'+str(time.time_ns())+'-'+fixture+'.pdf')
                c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/'+reference))+' '+c.literal(path)+' -Force;(Get-Item '+c.literal(path)+').IsReadOnly=$false')
                c.script('set',path=path,values={n:'18' for n in ['Str','Dex','Con','Int','Wis','Cha']});c.script('call',path=path,name='ApplyClasses',args=['Fighter (Champion) 5',False]);c.script('set',path=path,values={'Attack.1.Weapon Selection':'Longbow'})
                phases={};differences={}
                def capture(phase):
                    expected=case['phases'][phase]['fields'];actual=c.script('read',path=path,fields=list(expected))['fields'];phases[phase]=actual
                    delta={n:{'native':expected[n],'reader':actual.get(n)} for n in expected if expected[n]!=actual.get(n)}
                    if delta:differences[phase]=delta
                    (folder/(fixture+'-phases.json')).write_text(json.dumps(phases,indent=2))
                c.script('call',path=path,name='ClassFeatureOptions',args=[['fighter','fighting style','archery'],'add']);capture('bow-archery')
                c.script('call',path=path,name='ClassFeatureOptions',args=[['fighter','fighting style','dueling'],'add']);capture('bow-dueling')
                c.script('set',path=path,values={'Attack.1.Weapon Selection':'Longsword'});capture('sword-dueling')
                saved=path[:-4]+'-saved.pdf';c.script('save',path=path,output=saved);c.script('close',path=saved);local=c.fetch(saved,folder/(fixture+'-reader.pdf'))
                assert inspect(local,case['expected'])['passed'];assert script_hashes(local)==script_hashes(Path(case['source']))
                report['cases'].append({'fixture':fixture,'passed':not differences,'phase_differences':differences,'phases':str(folder/(fixture+'-phases.json')),'reader_saved':str(local)})
                (folder/'reader-fighting-styles.json').write_text(json.dumps(report,indent=2));assert not differences,{'fixture':fixture,'differences':differences}
                print(fixture,'Reader original style commands/attacks/save PASS',flush=True)
            report['passed']=True
    except Exception as error:
        report['error']=str(error)
        try:shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
        except Exception as screenshot_error:report['screenshot_error']=str(screenshot_error)
        raise
    finally:(folder/'reader-fighting-styles.json').write_text(json.dumps(report,indent=2));print(folder/'reader-fighting-styles.json',flush=True)

if __name__=='__main__':main()
