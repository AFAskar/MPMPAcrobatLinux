#!/usr/bin/env python3
"""Exact isolated runtime observation and optional formatted-appearance comparison.

Uses the same original RunUserScript entry as Reader, then checks the ASCII
carrier checksum/sentinel, scripts, exact captured JSON and selected decoded
AP text. Isolated action overrides are diagnostics, not original workflow passes.
"""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'target/debug/mpmb-reader');p.add_argument('--dialogs',type=Path,help='Explicit native dialog profile matching the observed Reader choices');p.add_argument('--reader-saved',action='store_true',help='Use the actual Reader-saved output for a fresh native reopen comparison');p.add_argument('--field');p.add_argument('--canonical-value');p.add_argument('--display-value');args=p.parse_args()
    if args.field:assert args.canonical_value is not None and args.display_value is not None
    reader=json.loads(args.reader.read_text());assert reader['passed'];source=Path(reader['input']);observer=Path(reader['observer']).read_text();assert hashlib.sha256(observer.encode()).hexdigest()==reader['observer_sha256'];assert hashlib.sha256(source.read_bytes()).hexdigest()==reader['input_sha256']
    measured_source=source
    if args.reader_saved:source=args.reader.parent/'reader.pdf';assert source.is_file()
    folder=ROOT/'output/testing'/('script-observation-comparison-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(args.binary,binary)
    report={'passed':False,'scope':__doc__,'reader':str(args.reader.resolve()),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'reader_saved':args.reader_saved,'source':str(source.resolve()),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'measured_source':str(measured_source)}
    dialogs=json.loads(args.dialogs.read_text()) if args.dialogs else [{'result':'ok'}]*10
    assert isinstance(dialogs,list)
    report['native_dialog_profile']=str(args.dialogs.resolve()) if args.dialogs else None
    report['native_dialog_profile_sha256']=hashlib.sha256(args.dialogs.read_bytes()).hexdigest() if args.dialogs else None
    summary="(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    output=folder/'native.pdf';scenario={'dialogs':dialogs,'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':"Value('User Script',"+json.dumps(observer)+")"},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'eval','code':summary},{'op':'save','path':str(output)}]}
    scenario_path=folder/'scenario.json';scenario_path.write_text(json.dumps(scenario))
    try:
        with (folder/'probe.log').open('w') as log:run=subprocess.run([str(binary),str(source),'--probe',str(scenario_path),str(folder/'probe.json')],stdout=log,stderr=log,timeout=300)
        native=json.loads((folder/'probe.json').read_text());report['strict_native_probe_passed']=native['passed'];assert run.returncode==0 and native['passed'],native.get('error')
        captured=style.saved_capture(output,native['stages'][-2]['result'],source);report['captured']=captured;report['exact_observations_equal']=captured==reader['captured'];assert report['exact_observations_equal'],'Captured event order/state differs'
        if args.field:
            report['formatted_appearance']={}
            for label,path in [('native',output),('reader',args.reader.parent/'reader.pdf')]:
                inspected=inspect(path,{args.field:args.canonical_value});widgets=inspected['widgets'];assert widgets
                checks={'canonical':inspected['actual'][args.field]==args.canonical_value,'widget_values':all(w['matches'] for w in widgets),'decoded_display':all(w['appearance'] and w['appearance_text']==args.display_value for w in widgets if w['visible'])}
                assert any(w['visible'] for w in widgets);report['formatted_appearance'][label]={'checks':checks,'display_texts':[w['appearance_text'] for w in widgets if w['visible']],'expected_display':args.display_value,'canonical_value':args.canonical_value};assert all(checks.values())
        assert hashlib.sha256(measured_source.read_bytes()).hexdigest()==reader['input_sha256'];assert hashlib.sha256(source.read_bytes()).hexdigest()==report['source_sha256'];report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:(folder/'comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'comparison.json',flush=True)


if __name__=='__main__':main()
