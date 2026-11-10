#!/usr/bin/env python3
"""Run original-sheet vertical slices and independent Linux checks. Evidence stays ignored."""
import argparse,hashlib,json,subprocess,sys,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect,script_hashes

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', choices=['2014','2024'], action='append', help='Run only this ruleset; repeat to select both')
    parser.add_argument('--binary', type=Path, default=ROOT/'target/debug/mpmb-reader', help='Qualify an isolated build without replacing a running reference binary')
    args=parser.parse_args()
    selected=args.fixture or ['2014','2024']
    folder=ROOT/'output/testing'/('native-acceptance-'+str(time.time_ns()));folder.mkdir(parents=True)
    binary=args.binary.resolve();binary_hash=hashlib.sha256(binary.read_bytes()).hexdigest();report={'passed':False,'selected_fixtures':selected,'binary':str(binary),'binary_sha256':binary_hash,'cases':[],'directory':str(folder)}
    def run(pdf,scenario,label):
        spec=folder/(label+'-scenario.json');evidence=folder/(label+'-report.json');log=folder/(label+'.log')
        spec.write_text(json.dumps(scenario))
        started=time.monotonic()
        with log.open('w') as out:
            proc=subprocess.run([str(binary),str(pdf),'--probe',str(spec),str(evidence)],cwd=ROOT,stdout=out,stderr=out,timeout=300)
        result=json.loads(evidence.read_text()) if evidence.exists() else {'error':'No probe report; inspect '+str(log)}
        assert proc.returncode==0,(label,result)
        assert result['passed'] is True,result.get('error')
        assert not result['diagnostics']['errors'],result['diagnostics']
        assert not result['diagnostics']['console']['messages'],result['diagnostics']['console']
        return {'probe':str(evidence),'seconds':round(time.monotonic()-started,3),'gaps':result['diagnostics']['gaps']}
    try:
        for rule in selected:
            item=next(x for x in json.loads((ROOT/'docs/fixtures.json').read_text()) if '_'+rule+'_' in x['file']);pdf=ROOT/'Testing'/item['file']
            assert hashlib.sha256(pdf.read_bytes()).hexdigest()==item['sha256']
            output=folder/('native-'+rule+'.pdf')
            expected={'PC Name':'Native Vertical Slice','Str':'18','Str Mod':'4','Class and Levels':'Fighter','Character Level':'1','Proficiency Bonus':'2'}
            scenario={'dialogs':[{'result':'ok'},{'event':'r0TX','values':{'r0TX':'Fighter 1'}},{'result':'ok'},{'result':'ok'}],'alerts':[1,1,1], 'steps':[
                {'op':'advance','ms':4100},{'op':'edit','field':'PC Name','value':expected['PC Name']},{'op':'edit','field':'Str','value':'18'},
                {'op':'assert','values':{'Str':'18','Str Mod':'4'}},{'op':'eval','code':"__host.invokeMenu('ClassesButton')"},{'op':'advance','ms':500},
                {'op':'assert','values':expected},{'op':'render','path':str(folder/(rule+'-native.ppm'))},{'op':'save','path':str(output)}]}
            detail=run(pdf,scenario,rule+'-create');detail['ruleset']=rule;detail['output']=str(output);report['cases'].append(detail)
            verify=inspect(output,expected);assert verify['passed'],verify
            assert script_hashes(pdf)==script_hashes(output),'Original script bytes changed'
            (folder/(rule+'-independent.json')).write_text(json.dumps(verify,indent=2))
            detail['independent']=True;detail['script_hashes_preserved']=True
            detail['reopen']=run(output,{'alerts':[1,1],'steps':[{'op':'advance','ms':4100},{'op':'assert','values':expected},{'op':'render','path':str(folder/(rule+'-reopened.ppm'))}]},rule+'-reopen')
            subprocess.run(['pdftoppm','-f','1','-singlefile','-scale-to','1100','-png',str(output),str(folder/(rule+'-poppler'))],check=True,stdout=subprocess.DEVNULL,stderr=(folder/(rule+'-poppler.log')).open('w'),timeout=60)
            assert hashlib.sha256(pdf.read_bytes()).hexdigest()==item['sha256']
            print(rule+' original scripts, class selection, calculations, save, native reopen and independent checks PASS',flush=True)
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==binary_hash,'Runtime binary changed during acceptance'
        report['passed']=True
    except Exception as e:
        report['error']=str(e);raise
    finally:
        (folder/'acceptance.json').write_text(json.dumps(report,indent=2));print(folder/'acceptance.json',flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
