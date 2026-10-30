#!/usr/bin/env python3
"""Exact captured API comparison; deliberately excludes appearance qualification.

Rechecks saved ASCII carriers, Reader checksum/sentinel, original document and
field actions before comparing values, rich metadata, page/rect and widgets.
A passing API comparison does not pass mixed fonts or decoration rendering.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields,script_hashes
spec=importlib.util.spec_from_file_location('workflow',ROOT/'tools/native/rich-format-workflow.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('native',type=Path);parser.add_argument('reader',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    report={'passed':False,'scope':__doc__,'inputs':[{'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for path in [args.native,args.reader]]}
    try:
        native,reader=[json.loads(path.read_text()) for path in [args.native,args.reader]]
        assert native['execution_completed'] and reader['execution_completed']
        assert native['fixture']==reader['fixture'] and native['addon_sha256']==reader['addon_sha256']
        assert reader['reader_request']
        ready=json.loads(Path(reader['readiness']).read_text());assert ready['passed'] and len(ready['cases'])==24
        source=next((ROOT/'Testing').glob({'2014':'*_2014_*.pdf','2024':'*_2024_*.pdf','ashnar':'Ashnar*.pdf'}[reader['fixture']]))
        for side in [native,reader]:
            pdf=Path(side['pdf']);before=hashlib.sha256(pdf.read_bytes()).hexdigest()
            raw=canonical_fields(PdfReader(pdf))['PC Name']['/V'];assert raw.isascii()
            captured=json.loads(raw);assert captured==side['captured']
            assert [ord(ch) for ch in captured['sentinel']]==[160,8232,128512]
            assert script_hashes(pdf)==script_hashes(source)
            assert m.actions(pdf)==m.actions(source)==side['actions']
            if side is reader:
                a,b=1,0
                for ch in raw:a=(a+ord(ch))%65521;b=(b+a)%65521
                assert reader['reader_summary']=={'code_units':len(raw),'adler32_utf16':str((b*65536+a)&0xffffffff)}
            assert hashlib.sha256(pdf.read_bytes()).hexdigest()==before
        left,right=native['captured'],reader['captured']
        report['different_sections']=[key for key in sorted(left.keys()|right.keys()) if left.get(key)!=right.get(key)]
        report['passed']=not report['different_sections']
        report['native_binary_sha256']=native['binary_sha256']
    except Exception as error:report['error']=str(error)
    with args.output.open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(args.output,'PASS' if report['passed'] else 'FAIL',flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
