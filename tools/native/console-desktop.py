#!/usr/bin/env python3
"""Render genuine native console show/output/clear/close and original error UI.

The 2024 legacy-import case is an expected original workflow failure, not an
import pass. Original dialogs use explicit scripted replies; pointer/keyboard
console-control interaction and interactive code input are not qualified here.
"""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]


def main():
    folder=ROOT/'output/testing'/('native-console-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
    report={'passed':False,'scope':__doc__,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':[]}
    fixtures=json.loads((ROOT/'docs/fixtures.json').read_text());hashes={str(ROOT/'Testing'/r['file']):r['sha256'] for r in fixtures}
    try:
        for label,pattern,source in [('basic-2014','*_2014_*.pdf',None),('original-import-error-2024','*_2024_*.pdf',ROOT/'Testing/Ashnar_TestingCharacter_.pdf')]:
            target=next((ROOT/'Testing').glob(pattern));case_folder=folder/label;env={**os.environ,'MPMB_UI_SMOKE_CONSOLE':'1'}
            for name in ['MPMB_UI_SMOKE_PRINT','MPMB_UI_SMOKE_BOOKMARK','MPMB_UI_SMOKE_IMPORT_SOURCE']:env.pop(name,None)
            if source:env['MPMB_UI_SMOKE_IMPORT_SOURCE']=str(source.resolve())
            with (folder/(label+'.log')).open('w') as log:run=subprocess.run([str(binary),str(target),'--desktop-smoke',str(case_folder)],cwd=ROOT,stdout=log,stderr=log,timeout=300,env=env)
            assert run.returncode==0,run.returncode
            result=json.loads((case_folder/'desktop-result.json').read_text());case={'label':label,'result':str(case_folder/'desktop-result.json'),'passed':result['passed'],'expected_original_import_failure':source is not None};report['cases'].append(case)
            assert result['passed'],result
            for state in ['visible','cleared','closed']:
                assert (case_folder/('console-'+state+'.png')).is_file()
                assert (case_folder/('console-'+state+'.json')).is_file()
            if source:assert result['mpmb_workflow_passed'] is False and result['expected_original_import_failure']
            assert not any(gap in ['console.show UI','console.clear UI'] for gap in result['diagnostics']['gaps'])
            assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected for path,expected in hashes.items()),'Original PDF changed'
            (folder/'console.json').write_text(json.dumps(report,indent=2)+'\n');print(label,'console UI/state checks PASS',flush=True)
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:(folder/'console.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'console.json',flush=True)


if __name__=='__main__':main()
