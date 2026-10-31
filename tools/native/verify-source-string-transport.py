#!/usr/bin/env python3
"""Compare decoded toSource string/key transport with the saved Reader oracle.

Quote spelling and source formatting are not API-equality claims. Require exact
UTF-16 decoded keys/values, retained transport and independent saved carrier
checksum/sentinel/scripts; original document scripts are never modified.
"""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'target/debug/mpmb-reader');args=p.parse_args()
    reader=json.loads(args.reader.read_text());assert reader['passed'];source=Path(reader['input']);observer=Path(reader['observer']).read_text();assert hashlib.sha256(observer.encode()).hexdigest()==reader['observer_sha256'];assert hashlib.sha256(source.read_bytes()).hexdigest()==reader['input_sha256']
    folder=ROOT/'output/testing'/('source-string-comparison-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(args.binary,binary)
    report={'passed':False,'scope':__doc__,'reader':str(args.reader.resolve()),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    summary="(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    scenario={'dialogs':[{'title':'SOURCE SELECTION DIALOG','result':'ok'}],'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':"Value('User Script',"+json.dumps(observer)+")"},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'eval','code':summary},{'op':'save','path':str(folder/'native.pdf')}]}
    scenario_path=folder/'scenario.json';scenario_path.write_text(json.dumps(scenario))
    try:
        with (folder/'probe.log').open('w') as log:run=subprocess.run([str(binary),str(source),'--probe',str(scenario_path),str(folder/'probe.json')],stdout=log,stderr=log,timeout=300)
        probe=json.loads((folder/'probe.json').read_text());report['strict_probe_passed']=probe['passed'];assert run.returncode==0 and probe['passed'],probe.get('error')
        capture=style.saved_capture(folder/'native.pdf',probe['stages'][-2]['result'],source);report['captured']=capture
        keys=['stored_equals_source','decoded_key_units','decoded_value_units','key_retained','value_retained'];report['checks']={k:capture[k]==reader['captured'][k] for k in keys}
        assert all(capture[k] and reader['captured'][k] for k in ['stored_equals_source','key_retained','value_retained']);assert all(report['checks'].values())
        assert hashlib.sha256(source.read_bytes()).hexdigest()==reader['input_sha256'];report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:(folder/'comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'comparison.json',flush=True)


if __name__=='__main__':main()
