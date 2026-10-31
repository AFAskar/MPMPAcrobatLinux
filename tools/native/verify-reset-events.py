#!/usr/bin/env python3
"""Compare isolated reset/commit exception observations with actual Reader.

Synthetic action errors intentionally leave the underlying native strict probe
failed. Only exact observed API traces/values and those six errors can qualify
this diagnostic. This is not an original MPMB import/reset workflow pass.
"""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
spec=importlib.util.spec_from_file_location('reader_reset',ROOT/'tools/native/reader-reset-events.py');reset=importlib.util.module_from_spec(spec);spec.loader.exec_module(reset)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'target/debug/mpmb-reader');args=p.parse_args()
    reference=json.loads(args.reader.read_text());assert reference['passed'] and len(reference['captured']['failures'])==6
    source=next((ROOT/'Testing').glob('*_2024_*.pdf'));before=hashlib.sha256(source.read_bytes()).hexdigest()
    folder=ROOT/'output/testing'/('native-reset-events-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    binary=folder/'mpmb-reader';shutil.copy2(args.binary,binary);output=folder/'native.pdf';probe=folder/'probe.json'
    report={'passed':False,'scope':__doc__,'reader':str(args.reader.resolve()),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    summary="(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    scenario={'dialogs':[{'title':'SOURCE SELECTION DIALOG','result':'ok'}],'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':reset.STRING_ARGUMENT_OBSERVER if reference.get('observer_profile')=='string-arguments' else reset.OBSERVER},{'op':'eval','code':summary},{'op':'save','path':str(output)}]}
    scenario_path=folder/'scenario.json';scenario_path.write_text(json.dumps(scenario))
    try:
        with (folder/'probe.log').open('w') as log:result=subprocess.run([str(binary),str(source),'--probe',str(scenario_path),str(probe)],stdout=log,stderr=log,timeout=300)
        native=json.loads(probe.read_text());report['strict_probe_passed']=native['passed'];report['strict_probe_exit_code']=result.returncode
        assert all(stage['passed'] for stage in native['stages']),native.get('error')
        errors=native['diagnostics']['errors'];report['expected_diagnostic_errors']=errors
        assert len(errors)==6 and all(error.get('field')=='Player Name' and error.get('event') in ['K','V','F'] and error.get('error')=='Error: MPMB field exception sentinel' for error in errors)
        assert not native['passed'] and result.returncode!=0, 'Strict probe must retain intentional original action errors'
        captured=reset.style.saved_capture(output,native['stages'][-2]['result'],source);report['captured']=captured
        report['exact_observations_equal']=captured==reference['captured']
        assert report['exact_observations_equal'],'Reset/exception traces or canonical values differ'
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:
        (folder/'reset-events.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'reset-events.json',flush=True)


if __name__=='__main__':main()
