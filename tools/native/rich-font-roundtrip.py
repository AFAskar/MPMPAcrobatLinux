#!/usr/bin/env python3
"""Qualify font-face retention through fresh native and real Reader save/reopen.

This checks font resources, canonical text and original actions/scripts only.
Optional first-baseline checks measure retention across the same roundtrip.
Decorations, glyph advances and complete appearances remain unqualified.
"""
import argparse
import hashlib
import importlib.util
import json
import os
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
    parser.add_argument('--first-baseline',action='store_true')
    parser.add_argument('--without-system-fonts-on-reopen',action='store_true',help='Disable executable lookup during fresh native probes to test embedded-face portability')
    parser.add_argument('--edit-on-reopen',action='store_true',help='Edit and restore the original notes through field events before resaving')
    args = parser.parse_args()
    if not args.native_only:
        assert args.readiness
        ready=json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24
    measured=json.loads(args.native.read_text());assert measured['execution_completed']
    source=Path(measured['pdf']);assert source.resolve().is_relative_to(ROOT/'output/testing')
    binary=args.native.parent/'mpmb-reader';assert hashlib.sha256(binary.read_bytes()).hexdigest()==measured['binary_sha256']
    expected=w.appearances(source);assert expected==measured['appearances']
    expected_faces=[row['fonts'] for row in expected]
    def baselines(rows):
        result=[]
        for row in rows:
            for op in row['text_positions']:
                if op['operator'] in ['Tm','Td','TD']:
                    result.append(float(op['operands'][-1]));break
            else:raise AssertionError('No first text placement')
        return result
    expected_baselines=baselines(expected)
    assert len(expected_faces)==1 and len(expected_faces[0])==4, 'This qualification requires the four-face notes case'
    fixture=next((ROOT/'Testing').glob({'2014':'*_2014_*.pdf','2024':'*_2024_*.pdf','ashnar':'Ashnar*.pdf'}[measured['fixture']]))
    expected_actions=w.actions(fixture);expected_scripts=w.script_hashes(fixture)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    folder=ROOT/'output/testing'/('rich-font-roundtrip-'+str(time.time_ns()));folder.mkdir()
    report={'passed':False,'scope':__doc__,'native_only':args.native_only,'first_baseline_retention':args.first_baseline,'without_system_fonts_on_reopen':args.without_system_fonts_on_reopen,'edit_on_reopen':args.edit_on_reopen,'native_measurement':str(args.native.resolve()),'readiness':str(args.readiness.resolve()) if args.readiness else None,'binary_sha256':measured['binary_sha256'],'cases':[]}
    print(folder,flush=True)
    def verify(path,label):
        fields=w.canonical_fields(w.PdfReader(path))
        assert fields[w.FIELD]['/V']==w.TEXT
        assert w.actions(path)==expected_actions
        assert w.script_hashes(path)==expected_scripts
        rows=w.appearances(path);faces=[row['fonts'] for row in rows]
        baseline_equal=not args.first_baseline or all(abs(a-b)<.002 for a,b in zip(baselines(rows),expected_baselines)) and len(rows)==len(expected_baselines)
        report['cases'].append({'label':label,'path':str(path),'faces':faces,'first_baselines':baselines(rows),'passed':faces==expected_faces and baseline_equal})
        assert faces==expected_faces, 'Saved font-face set changed'
        assert baseline_equal, 'First baseline changed across save/reopen'
    def reopen(path,label):
        output=folder/(label+'.pdf')
        old_path=os.environ.get('PATH')
        if args.without_system_fonts_on_reopen:
            empty=folder/'no-executables';empty.mkdir(exist_ok=True)
            os.environ['PATH']=str(empty)
        try:
            edits=[{'op':'edit','field':w.FIELD,'value':w.TEXT+' [edit]'}, {'op':'edit','field':w.FIELD,'value':w.TEXT}] if args.edit_on_reopen else []
            state=w.style.p.probe(binary,path,folder,label,edits+[{'op':'eval','code':"JSON.parse(__host.snapshot())['Extra.Notes'].richValue"},{'op':'save','path':str(output)}])['stages'][-2]['result']
        finally:
            if old_path is None:os.environ.pop('PATH',None)
            else:os.environ['PATH']=old_path
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
            subprocess.run(w.c.SCP+[str(source),w.c.SCP_TARGET + ':MPMB-Testing/'+relative],capture_output=True,check=True)
            remote=w.c.remote_path(relative);report['reader_path']=remote
            saved=remote[:-4]+'-saved.pdf'
            report['reader_save']=w.c.script('save',path=remote,output=saved)
            summary=w.c.script('field_summary',path=saved,fields=['PC Name'])['fields']['PC Name']
            report['reader_diagnostic_summary']=summary
            report['reader_close']=w.c.script('close',path=saved)
            local=w.c.fetch(saved,folder/'reader.pdf')
        diagnostic=w.style.saved_capture(local,summary,fixture)
        expected_diagnostic=dict(measured['captured']);expected_diagnostic.pop('sentinel')
        report['reader_diagnostic_equal']=diagnostic==expected_diagnostic
        assert report['reader_diagnostic_equal'], 'Reader changed captured field/widget APIs'
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
