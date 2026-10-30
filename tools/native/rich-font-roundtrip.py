#!/usr/bin/env python3
"""Qualify font-face retention through fresh native and real Reader save/reopen.

This checks font resources, canonical text and original actions/scripts only.
It does not qualify decorations, glyph positioning or complete appearances.
"""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('formatting', ROOT/'tools/native/rich-format-workflow.py')
w = importlib.util.module_from_spec(spec);spec.loader.exec_module(w)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--readiness',type=Path)
    parser.add_argument('--native-only',action='store_true')
    args = parser.parse_args()
    if not args.native_only:
        assert args.readiness
        ready=json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24
    measured=json.loads(args.native.read_text());assert measured['execution_completed']
    source=Path(measured['pdf']);assert source.resolve().is_relative_to(ROOT/'output/testing')
    binary=args.native.parent/'mpmb-reader';assert hashlib.sha256(binary.read_bytes()).hexdigest()==measured['binary_sha256']
    expected=w.appearances(source);assert expected==measured['appearances']
    expected_faces=[row['fonts'] for row in expected]
    assert len(expected_faces)==1 and len(expected_faces[0])==4, 'This qualification requires the four-face notes case'
    fixture=next((ROOT/'Testing').glob({'2014':'*_2014_*.pdf','2024':'*_2024_*.pdf','ashnar':'Ashnar*.pdf'}[measured['fixture']]))
    expected_actions=w.actions(fixture);expected_scripts=w.script_hashes(fixture)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    folder=ROOT/'output/testing'/('rich-font-roundtrip-'+str(time.time_ns()));folder.mkdir()
    report={'passed':False,'scope':__doc__,'native_only':args.native_only,'native_measurement':str(args.native.resolve()),'readiness':str(args.readiness.resolve()) if args.readiness else None,'binary_sha256':measured['binary_sha256'],'cases':[]}
    print(folder,flush=True)
    def verify(path,label):
        fields=w.canonical_fields(w.PdfReader(path))
        assert fields[w.FIELD]['/V']==w.TEXT
        assert w.actions(path)==expected_actions
        assert w.script_hashes(path)==expected_scripts
        faces=[row['fonts'] for row in w.appearances(path)]
        report['cases'].append({'label':label,'path':str(path),'faces':faces,'passed':faces==expected_faces})
        assert faces==expected_faces, 'Saved font-face set changed'
    def reopen(path,label):
        output=folder/(label+'.pdf')
        state=w.style.p.probe(binary,path,folder,label,[{'op':'eval','code':"JSON.parse(__host.snapshot())['Extra.Notes'].richValue"},{'op':'save','path':str(output)}])['stages'][-2]['result']
        report[label+'_rich_value']=state
        assert state==measured['formatted_native'], 'Rich span state changed on native reopen'
        verify(output,label)
    try:
        verify(source,'initial-native')
        reopen(source,'native-reopen')
        if args.native_only:
            assert hashlib.sha256(source.read_bytes()).hexdigest()==before
            report['passed']=True
            return 0
        with w.c.desktop_lock():
            assert not [e for e in w.c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            relative='runs/rich-font-roundtrip-'+str(time.time_ns())+'.pdf'
            subprocess.run(w.c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/'+relative],capture_output=True,check=True)
            remote=w.c.remote_path(relative);report['reader_path']=remote
            saved=remote[:-4]+'-saved.pdf'
            report['reader_save']=w.c.script('save',path=remote,output=saved)
            report['reader_close']=w.c.script('close',path=saved)
            local=w.c.fetch(saved,folder/'reader.pdf')
        verify(local,'reader-save')
        reopen(local,'reader-native-reopen')
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        report['passed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:
        (folder/'fonts.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'fonts.json',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
