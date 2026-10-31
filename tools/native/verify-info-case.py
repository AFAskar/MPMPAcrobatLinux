#!/usr/bin/env python3
"""Compare 39 sampled metadata getters with actual Reader observations.

Date comparison uses type/epoch, not locale-dependent display text. Enumeration
differences and full API equality are reported separately and remain gaps.
"""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
spec=importlib.util.spec_from_file_location('reader_info',ROOT/'tools/native/reader-info-case.py');info=importlib.util.module_from_spec(spec);spec.loader.exec_module(info)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'target/debug/mpmb-reader');args=p.parse_args()
    reference=json.loads(args.reader.read_text());assert reference['passed']
    source=next((ROOT/'Testing').glob('*_2024_*.pdf'));before=hashlib.sha256(source.read_bytes()).hexdigest()
    folder=ROOT/'output/testing'/('native-info-case-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    binary=folder/'mpmb-reader';shutil.copy2(args.binary,binary)
    report={'passed':False,'scope':__doc__,'reader':str(args.reader.resolve()),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    output=folder/'native.pdf';probe=folder/'probe.json'
    summary="(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    scenario={'dialogs':[{'title':'SOURCE SELECTION DIALOG','result':'ok'}],'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':info.OBSERVER},{'op':'eval','code':summary},{'op':'save','path':str(output)}]}
    scenario_path=folder/'scenario.json';scenario_path.write_text(json.dumps(scenario))
    try:
        with (folder/'probe.log').open('w') as log:result=subprocess.run([str(binary),str(source),'--probe',str(scenario_path),str(probe)],stdout=log,stderr=log,timeout=300)
        native=json.loads(probe.read_text());assert result.returncode==0 and native['passed'],native.get('error')
        captured=info.style.saved_capture(output,native['stages'][-2]['result'],source);expected=reference['captured'];report['captured']=captured
        assert set(captured['values'])==set(expected['values']) and len(expected['values'])==39
        checks={}
        for key,value in expected['values'].items():
            observed=captured['values'][key]
            if value.get('epoch_millis') is not None:
                checks[key]=observed.get('type')==value['type'] and observed.get('epoch_millis')==value['epoch_millis']
            else:checks[key]=observed==value
        report['checks']=checks
        report['enumeration_keyset_equal']=set(captured['keys'])==set(expected['keys'])
        report['reader_only_keys']=sorted(set(expected['keys'])-set(captured['keys']))
        report['native_only_keys']=sorted(set(captured['keys'])-set(expected['keys']))
        report['date_display_strings_equal']={key:captured['values'][key]['text']==value['text'] for key,value in expected['values'].items() if value.get('epoch_millis') is not None}
        report['normalization']='Sampled dates compare type and epoch milliseconds; other sampled values compare exactly. Enumeration compares sets and is not a required pass condition. Locale display strings are reported, not normalized into equality.'
        report['exact_api_equality']=report['enumeration_keyset_equal'] and all(report['date_display_strings_equal'].values()) and all(checks.values())
        assert all(checks.values()),'Sampled metadata values differ: '+','.join(key for key,passed in checks.items() if not passed)
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:
        (folder/'info-case.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'info-case.json',flush=True)


if __name__=='__main__':main()
