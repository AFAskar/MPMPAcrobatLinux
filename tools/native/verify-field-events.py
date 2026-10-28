#!/usr/bin/env python3
"""Read-only exact runtime-trace comparison with independently saved Reader evidence.

This qualifies only the measured fixture/field/script profile. It does not
certify all field events, dialogs, edited rich save/reopen or appearance fidelity.
"""
import argparse,hashlib,json,sys
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields,script_hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('native',type=Path);parser.add_argument('reader',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    report={'passed':False,'scope':__doc__,'inputs':[{'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [args.native,args.reader]]}
    try:
        n,r=[json.loads(p.read_text()) for p in [args.native,args.reader]]
        assert n['execution_completed'] and r['execution_completed'],'A probe did not complete'
        assert n['fixture']==r['fixture'] and n['field']==r['field'],'Different fixture/field'
        for key in ['rich_data','style_data','rich_events']:assert bool(n.get(key))==bool(r.get(key)),key
        assert n['addon_sha256']==r['addon_sha256'],'Different original add-on inputs'
        qualification=json.loads(Path(r['readiness']).read_text());assert qualification['passed'] and len(qualification['cases'])==24,'Reference readiness failed'
        saved=Path(r['reader_saved']);text=canonical_fields(PdfReader(saved))['PC Name']['/V'];assert text.isascii(),'Reader carrier is not ASCII'
        a,b=1,0
        for ch in text:a=(a+ord(ch))%65521;b=(b+a)%65521
        assert r['reader_summary']=={'code_units':len(text),'adler32_utf16':str((b*65536+a)&0xffffffff)},'Saved Reader checksum mismatch'
        assert json.loads(text)==r['reader'],'Saved Reader diagnostic mismatch'
        fixture=next((ROOT/'Testing').glob({'2014':'*_2014_*.pdf','2024':'*_2024_*.pdf','ashnar':'Ashnar*.pdf'}[r['fixture']]))
        assert script_hashes(saved)==script_hashes(fixture),'Original scripts changed'
        assert [ord(ch) for ch in r['reader'][-1]['value']]==[160,8232,128512],'Reader sentinel changed'
        assert [ord(ch) for ch in n['native'][-1]['value']]==[160,8232,128512],'Native sentinel changed'
        differences=[]
        for i in range(max(len(n['native']),len(r['reader']))):
            left=n['native'][i] if i<len(n['native']) else {};right=r['reader'][i] if i<len(r['reader']) else {}
            if left!=right:differences.append({'index':i,'native_case':left.get('name'),'reader_case':right.get('name'),'different_keys':[k for k in sorted(left.keys()|right.keys()) if left.get(k)!=right.get(k)]})
        report.update(passed=not differences,cases=len(n['native']),differences=differences,reader_saved_sha256=hashlib.sha256(saved.read_bytes()).hexdigest(),native_binary_sha256=n['binary_sha256'])
    except Exception as error:report['error']=str(error)
    with args.output.open('x') as file:json.dump(report,file,indent=2);file.write('\n')
    print(args.output,'PASS' if report['passed'] else 'FAIL',flush=True);return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
