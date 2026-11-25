#!/usr/bin/env python3
"""Read a structured original-document runtime observation through Reader's menu.

The supplied diagnostic script must write ASCII JSON with a Unicode sentinel to
PC Name. This verifies transport/scripts/input hashes, not MPMB workflow parity.
"""
import argparse,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--observer',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True)
    p.add_argument('--pre-values',type=Path,help='JSON object of separate original field assignments before observing the ready document')
    args=p.parse_args()
    ready=json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
    source=args.input.resolve();observer=args.observer.read_text();folder=ROOT/'output/testing'/('reader-script-observation-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    frozen=folder/'observer.js';frozen.write_text(observer)
    remote=c.remote_path('runs/script-observation-'+str(time.time_ns())+'.pdf');opened=False;pending=None
    report={'passed':False,'scope':__doc__,'input':str(source),'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'observer':str(frozen.resolve()),'observer_source':str(args.observer.resolve()),'observer_sha256':hashlib.sha256(observer.encode()).hexdigest(),'readiness':str(args.readiness.resolve())}
    pre_values=json.loads(args.pre_values.read_text()) if args.pre_values else None
    if pre_values is not None:
        assert isinstance(pre_values,dict) and pre_values and all(isinstance(k,str) and isinstance(v,(str,int,float,bool)) for k,v in pre_values.items())
        (folder/'pre-values.json').write_text(json.dumps(pre_values,indent=2)+'\n');report['pre_values']=pre_values;report['pre_values_sha256']=hashlib.sha256(args.pre_values.read_bytes()).hexdigest()
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP+[str(source),c.SCP_TARGET + ':MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True)
            opened=True;c.ensure_document(remote)
            if pre_values is not None:c.script('set',path=remote,values=pre_values)
            c.script('set',path=remote,values={'User Script':observer});pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);report['request']=pending;report['completion']=c.script_result(pending,timeout=120);pending=None
            summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['summary']=summary
            c.script('set',path=remote,values={'User Script':''});saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved
            report['close']=c.script('close',path=remote);opened=False;local=c.fetch(remote,folder/'reader.pdf');report['captured']=style.saved_capture(local,summary,source)
            assert hashlib.sha256(source.read_bytes()).hexdigest()==report['input_sha256'];report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
                    if pending:report['original_completion']=c.script_result(pending,timeout=90)
                    retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
            except Exception as error:report['cleanup_error']=str(error)
        (folder/'observation.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'observation.json',flush=True)


if __name__=='__main__':main()
