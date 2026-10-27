#!/usr/bin/env python3
"""Compare embedded-file metadata/menu behavior with independently opened Reader fixtures.

Own probe code runs through MPMB's original manual add-on workflow. No extracted
scripts or expected metadata are written into the reference output.
"""
import argparse, json, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import inspect, script_hashes
from attachments import payloads

ADDON = '''var iFileName="Attachment metadata probe.js";
(function(d){
 MakeFaqMenu_FaqOptions('justMenu');
 var metadata=d.dataObjects.map(function(n){return {name:n.name,path:n.path,size:n.size,MIMEType:n.MIMEType};});
 Value('PC Name',JSON.stringify({metadata:metadata,faq:Menus.faq.some(function(n){return n.cReturn==='faq#pdf';})}));
})(tDoc);'''


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('native_report',type=Path);parser.add_argument('--readiness',type=Path,required=True);args=parser.parse_args()
    native=json.loads(args.native_report.read_text());qualification=json.loads(args.readiness.read_text());assert native['passed'] and qualification['passed'] and len(qualification['cases'])==24
    folder=args.native_report.resolve().parent/('reader-attachments-'+str(time.time_ns()));folder.mkdir()
    report={'passed':False,'readiness':str(args.readiness.resolve()),'cases':[]};print(folder,flush=True)
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Reference suite requires no pre-existing document'
            for case in native['cases']:
                fixture=case['fixture'];reference='ashnar.pdf' if fixture=='ashnar' else 'blank-'+fixture+'.pdf'
                path=c.remote_path('runs/attachment-reference-'+str(time.time_ns())+'-'+fixture+'.pdf')
                c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/'+reference))+' '+c.literal(path)+' -Force;(Get-Item '+c.literal(path)+').IsReadOnly=$false')
                c.script('set',path=path,values={'User Script':ADDON});c.script('call',path=path,name='RunUserScript',args=[False])
                raw=c.script('read',path=path,fields=['PC Name'])['fields']['PC Name'];actual=json.loads(raw)
                # Always save/close and fetch before comparing so a mismatch
                # cannot leave a reference document open for the next suite.
                saved=path[:-4]+'-saved.pdf';c.script('save',path=path,output=saved);c.script('close',path=saved)
                local=c.fetch(saved,folder/(fixture+'-reader.pdf'))
                expected=sorted(case['metadata'],key=lambda n:n['name']);observed=sorted(actual['metadata'],key=lambda n:n['name'])
                assert observed==expected,{'native':expected,'reader':observed}
                assert actual['faq']
                source=Path(case['source']);assert payloads(local)==payloads(source)
                assert script_hashes(local)==script_hashes(source)
                assert inspect(local,{'PC Name':raw})['passed']
                report['cases'].append({'fixture':fixture,'passed':True,'reader_metadata':observed,'faq_menu':True,'payloads_equal':True,'reader_saved':str(local)})
                (folder/'reader-attachments.json').write_text(json.dumps(report,indent=2));print(fixture,'Reader attachment metadata/menu/persistence PASS',flush=True)
            report['passed']=True
    except Exception as error:
        report['error']=str(error)
        try:
            shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
        except Exception as screenshot_error:report['screenshot_error']=str(screenshot_error)
        raise
    finally:
        (folder/'reader-attachments.json').write_text(json.dumps(report,indent=2));print(folder/'reader-attachments.json',flush=True)

if __name__=='__main__':main()
