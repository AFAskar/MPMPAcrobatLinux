#!/usr/bin/env python3
"""Run original native 2024 DirectImport with the same Reader observation.

Preserves the raw strict probe's exit status, including original field errors.
Use verify-direct-import.py separately for bounded Reader data/error parity.
"""
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('reader_import',ROOT/'tools/native/reader-direct-import.py');reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'target/debug/mpmb-reader');args=p.parse_args()
    source=args.source.resolve();assert source.is_file();target=next((ROOT/'Testing').glob('*_2024_*.pdf'))
    folder=ROOT/'output/testing'/('native-direct-import-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    binary=folder/'mpmb-reader';shutil.copy2(args.binary,binary)
    hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in [source,target]}
    summary="(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    scenario={'steps':[{'op':'advance','ms':4100},{'op':'eval','code':'__host.command('+json.dumps(reader.SCRIPT)+')'},{'op':'eval','code':summary},{'op':'save','path':str(folder/'native.pdf')}],
              'dialogs':[{'title':'SOURCE SELECTION DIALOG','result':'ok'},{'title':'IMPORT FROM PDF DIALOG','result':'ok','values':{'fLoc':str(source),'fRel':False,'icYe':False,'icNo':True}}],'alerts':[1]*100}
    scenario_path=folder/'scenario.json';scenario_path.write_text(json.dumps(scenario))
    with (folder/'probe.log').open('w') as log:result=subprocess.run([str(binary),str(target),'--probe',str(scenario_path),str(folder/'report.json')],stdout=log,stderr=log,timeout=300,env={**os.environ,'MPMB_DIALOG_TRACE_DIR':str(folder/'traces')})
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==value for path,value in hashes.items()),'An input PDF changed'
    evidence={'scope':__doc__,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'input_hashes':hashes,'strict_exit_code':result.returncode,'probe':str(folder/'report.json')}
    (folder/'execution.json').write_text(json.dumps(evidence,indent=2)+'\n');print(folder/'execution.json',flush=True)
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
