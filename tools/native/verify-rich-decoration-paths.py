#!/usr/bin/env python3
"""Read-only presence/retention checks for the controlled original notes case.

A successful presence check is not exact Reader geometry or full formatting.
The independent original-workflow comparison remains the compatibility gate.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('workflow',ROOT/'tools/native/rich-format-workflow.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)


def paths(rows):
    result=[]
    for row in rows:
        baseline=next(float(op['operands'][-1]) for op in row['text_positions'] if op['operator'] in ['Tm','Td','TD'])
        width=1.;start=end=None;segments=[]
        for op in row['drawing']:
            operands=[float(value) for value in op['operands']]
            assert all(math.isfinite(value) for value in operands)
            if op['operator']=='w':width=operands[0]
            elif op['operator']=='m':start=operands
            elif op['operator']=='l':end=operands
            elif op['operator'] in ['S','s']:
                if start is not None and end is not None and abs(start[1]-end[1])<.001 and end[0]>start[0]:
                    assert width>0
                    segments.append({'x1':start[0],'x2':end[0],'offset':start[1]-baseline,'thickness':width})
                start=end=None
        assert any(segment['offset']<0 for segment in segments), 'No underline below baseline'
        assert any(segment['offset']>0 for segment in segments), 'No strike above baseline'
        result.append(segments)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roundtrip',type=Path);parser.add_argument('report',type=Path)
    parser.add_argument('--require-vertical-geometry',action='store_true',help='Require every roundtrip stage to match actual Reader Y offsets and stroke widths within0.002pt')
    args=parser.parse_args();assert not args.report.exists()
    data=json.loads(args.roundtrip.read_text());assert data['passed']
    measured=json.loads(Path(data['native_measurement']).read_text())
    fixture=next((ROOT/'Testing').glob({'2014':'*_2014_*.pdf','2024':'*_2024_*.pdf','ashnar':'Ashnar*.pdf'}[measured['fixture']]))
    scripts=w.script_hashes(fixture);actions=w.actions(fixture)
    report={'scope':__doc__,'presence_passed':False,'roundtrip':str(args.roundtrip.resolve()),'cases':[]}
    try:
        for case in data['cases']:
            path=Path(case['path']);assert path.resolve().is_relative_to(ROOT/'output/testing')
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            assert w.canonical_fields(w.PdfReader(path))[w.FIELD]['/V']==w.TEXT
            assert w.actions(path)==actions and w.script_hashes(path)==scripts
            segments=paths(w.appearances(path))
            assert hashlib.sha256(path.read_bytes()).hexdigest()==before
            report['cases'].append({'label':case['label'],'path':str(path),'sha256':before,'segments':segments})
        native=report['cases'][0]['segments'];reader=next(case['segments'] for case in report['cases'] if case['label']=='reader-save')
        # Compare unique offset/thickness pairs, keeping presence and equality
        # separate. Reader splits strike strokes into individual characters.
        signature=lambda rows:sorted({(round(segment['offset'],3),round(segment['thickness'],3)) for row in rows for segment in row})
        report['reader_geometry_equal']=signature(native)==signature(reader)
        def groups(rows):
            unique=[]
            for row in rows:
                for segment in row:
                    if not any(abs(segment['offset']-g['offset'])<.001 and abs(segment['thickness']-g['thickness'])<.001 for g in unique):unique.append({'offset':segment['offset'],'thickness':segment['thickness']})
            return sorted(unique,key=lambda g:g['offset'])
        reference=groups(reader)
        for case in report['cases']:
            observed=groups(case['segments']);case['vertical_geometry_equal']=len(observed)==len(reference) and all(abs(x['offset']-y['offset'])<=.002 and abs(x['thickness']-y['thickness'])<=.002 for x,y in zip(observed,reference))
        report['vertical_geometry_equal']=all(case['vertical_geometry_equal'] for case in report['cases'])
        report['comparison_scope']='Y offsets and stroke widths within0.002pt against actual Reader-save; x advances, path topology, colors and full pixels are not compared'
        report['compatibility_pass']=False
        if args.require_vertical_geometry:assert report['vertical_geometry_equal'], 'Roundtrip decoration geometry differs'
        report['presence_passed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:
        args.report.write_text(json.dumps(report,indent=2)+'\n');print(args.report)
    return 0


if __name__=='__main__':raise SystemExit(main())
