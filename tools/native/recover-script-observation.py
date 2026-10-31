#!/usr/bin/env python3
"""Retain/close a completed failed diagnostic without replaying its mutation.

A fresh read-only function/readiness query and exact owned-document checks are
required before save. Recovery checks do not relabel the failed suite as passed.
"""
import argparse,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--failed',type=Path,required=True);args=p.parse_args();failed=json.loads(args.failed.read_text());assert failed['passed'] is False and failed['original_completion']['value'] is True
 folder=args.failed.parent;name=failed['original_completion']['path'].replace('\\','/').split('/')[-1];path=c.remote_path('runs/'+name);output=path[:-4]+'-recovered-retained.pdf';report={'passed':False,'qualification_passed':False,'scope':__doc__,'failed_report':str(args.failed.resolve()),'original_request':failed['request']}
 try:
  with c.desktop_lock():
   windows=[e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()];assert len(windows)==1 and name in windows[0]['name']
   report['state']=c.raw_script('functions',path=path,names=['InitializeEverything','CalcMod']);state=report['state'];assert len(state['openDocuments'])==1 and state['openDocuments'][0].endswith('/'+name);assert all(v=='function' for v in state['functions'].values());assert state['calculation']['app'] and state['calculation']['doc'] and not state['calculation']['delay']
   report['summary']=c.raw_script('field_summary',path=path,fields=['PC Name'])['fields']['PC Name']
   report['save']=c.raw_script('save',path=path,output=output);report['close']=c.command('close_document',path=output);assert report['close']['closed'] and report['close']['process_terminated'];(c.STATE/'reader-session.json').unlink(missing_ok=True)
   local=c.fetch(output,folder/'recovered-retained.pdf')
  report['captured']=style.saved_capture(local,report['summary'],Path(failed['input']));assert not report['captured']['errors'];report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'recovery.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'recovery.json',flush=True)


if __name__=='__main__':main()
