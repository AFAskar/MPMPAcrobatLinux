#!/usr/bin/env python3
"""Read-only bounded native/Reader original-import data/error comparison.

The raw strict native suite stays failed for its two original format2 errors.
This comparison requires those same observed Reader errors and exact checked
fields. It does not qualify complete styles, metadata, rendering or other imports.
"""
import argparse,hashlib,importlib.util,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from pypdf import PdfReader
from verify import canonical_fields,inspect,script_hashes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--reader',type=Path,required=True);args=p.parse_args()
    native=json.loads((args.native/'report.json').read_text());reader=json.loads(args.reader.read_text());assert reader['passed']
    pdf=args.native/'native.pdf';text=canonical_fields(PdfReader(pdf))['PC Name']['/V'];assert text.isascii()
    captured=json.loads(text);assert [ord(ch) for ch in captured.pop('sentinel')]==[160,8232,128512]
    summary_stages=[stage['result'] for stage in native['stages'] if isinstance(stage.get('result'),dict) and 'adler32_utf16' in stage['result']]
    if summary_stages:
        assert len(summary_stages)==1
        a,b=1,0
        for ch in text:a=(a+ord(ch))%65521;b=(b+a)%65521
        assert summary_stages[0]=={'code_units':len(text),'adler32_utf16':str((b*65536+a)&0xffffffff)}
    expected=reader['captured'];source=next((ROOT/'Testing').glob('*_2024_*.pdf'))
    folder=ROOT/'output/testing'/('direct-import-comparison-'+str(time.time_ns()));folder.mkdir();report={'passed':False,'scope':__doc__,'native':str(args.native.resolve()),'reader':str(args.reader.resolve()),'strict_native_probe_passed':native['passed']};print(folder,flush=True)
    try:
        assert all(stage['passed'] for stage in native['stages'])
        errors=native['diagnostics']['errors'];assert not native['passed'] and len(errors)==2
        assert all(error.get('field')=='Carrying Capacity Multiplier' and error.get('event')=='F' and error.get('error','').startswith('TypeError:') and 'format2' in error.get('stack','') for error in errors)
        normalize_errors=lambda records:[{key:value for key,value in record.items() if key!='error'} for record in records]
        checks={key:captured[key]==expected[key] for key in ['returned','openDocuments','leftImportGlobals','cleanupPerformed','identity','choice','fields','pages']}
        checks.update({key:sorted(set(captured[key]))==sorted(set(expected[key])) for key in ['cantrips','spells','excludedSources']})
        checks['observed_original_errors']=normalize_errors(captured['originalActionErrors'])==normalize_errors(expected['originalActionErrors']) and len(expected['originalActionErrors'])==2
        checks['native_saved_fields']=inspect(pdf,captured['fields'])['passed']
        checks['scripts']=script_hashes(pdf)==script_hashes(source)
        scenario=json.loads((args.native/'scenario.json').read_text());from_path=Path(next(reply['values']['fLoc'] for reply in scenario['dialogs'] if reply.get('title')=='IMPORT FROM PDF DIALOG'))
        checks['source_unchanged']=hashlib.sha256(from_path.read_bytes()).hexdigest()==reader['source_sha256']
        report.update(checks=checks,captured=captured,runtime_gaps=native['diagnostics']['gaps'],normalization='Spell/cantrip/source lists compare as sets; other checked data is exact. Original error messages are engine-specific: compare field/event/error type/input type/input text and counts, retain both raw messages. Not full API/appearance equality.',reader_original_errors=expected['originalActionErrors'])
        assert all(checks.values()),checks
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:(folder/'comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'comparison.json',flush=True)


if __name__=='__main__':main()
