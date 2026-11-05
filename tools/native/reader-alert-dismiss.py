#!/usr/bin/env python3
"""Measure Reader alerts through original RunUserScript and actual owned controls.

Use a qualified, idle reference desktop. The original PDF is copied unchanged;
ASCII diagnostics retain a real Unicode sentinel and independent saved checksum.
"""
from pathlib import Path
import sys,json,time,subprocess,hashlib
r=Path(__file__).resolve().parents[2];sys.path.insert(0,str(r/'tools/acrobat'));import control as c
from pypdf import PdfReader
from verify import canonical_fields,script_hashes
import importlib.util
spec=importlib.util.spec_from_file_location("style",r/"tools/native/default-style-persistence.py");style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
import argparse
p=argparse.ArgumentParser();p.add_argument('--readiness',type=Path,required=True);p.add_argument('--mode',choices=['dismiss','enter'],default='dismiss');args=p.parse_args()
ready=json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
folder=r/'output/testing'/('alert-dismiss-control-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
source=next((r/'Testing').glob('*_2024_*.pdf'));before=hashlib.sha256(source.read_bytes()).hexdigest();remote=c.remote_path('runs/alert-dismiss-'+str(time.time_ns())+'.pdf');opened=False;pending=None
report={'passed':False,'scope':'Actual Reader app.alert keyboard/window-close contract; not class or generic dialog qualification','mode':args.mode,'readiness':str(args.readiness.resolve()),'harness_sha256':c.harness_fingerprint(),'test_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'input_sha256':before,'cases':[]}
try:
 with c.desktop_lock():
  assert not [w for w in c.command('inspect') if w.get('class')=='AcrobatSDIWindow' and '.pdf' in w.get('name','').lower()]
  subprocess.run(c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote)
  for kind in range(4):
   for method,key in ([('enter','{ENTER}')] if args.mode=='enter' else [('escape','{ESC}'),('window-close','%{F4}')]):
    title='Alert dismiss %s %s'%(kind,method);case={'type':kind,'method':method,'title':title};report['cases'].append(case)
    script=("var iFileName='Alert dismissal diagnostic.js';var result=app.alert({cMsg:'Controlled dismissal test',cTitle:%s,nType:%d});"%(json.dumps(title),kind))+r"""if(!tDoc.__alertDismissResults)tDoc.__alertDismissResults=[];tDoc.__alertDismissResults.push({type:__TYPE__,method:__METHOD__,button:result});Value('PC Name',JSON.stringify({results:tDoc.__alertDismissResults,sentinel:'\u00a0\u2028\ud83d\ude00'}).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));""".replace('__TYPE__',str(kind)).replace('__METHOD__',json.dumps(method))
    c.script('set',path=remote,values={'User Script':script});pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);case['request']=pending;deadline=time.monotonic()+60
    while True:
     windows=c.command('inspect');roots=[w for w in windows if w.get('class')=='#32770' and w.get('name')==title]
     if roots:break
     assert time.monotonic()<deadline,windows
    assert len(roots)==1;root=roots[0];case['dialog']=root;case['controls']=[w for w in windows if w.get('owner')==root['handle']];case['focus_before']=c.command('inspect_focused');assert case['focus_before'].get('in_reader') and case['focus_before'].get('foreground_class')=='#32770',case['focus_before'];case['dismiss_input']=c.command('keys',keys=key)
    windows=c.command('inspect');remaining=[w for w in windows if w.get('handle')==root['handle'] and w.get('name')==title];case['dismissed']=not remaining
    if remaining:
     fallback_label={0:'OK',1:'Cancel',2:'No',3:'Cancel'}[kind];buttons=[w for w in windows if w.get('owner')==root['handle'] and w.get('class')=='Button' and w.get('name').replace('&','')==fallback_label and w.get('enabled')];assert len(buttons)==1,windows
     case['fallback']=c.command('invoke',name=buttons[0]['name'],owner=root['handle'])
    case['completion']=c.script_result(pending,timeout=120);pending=None
    case['result']=json.loads(c.script('read',path=remote,fields=['PC Name'])['fields']['PC Name'])['results'][-1];assert isinstance(case['result']['button'],int),case
    (folder/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
  summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['summary']=summary;c.script('set',path=remote,values={'User Script':''});saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved;report['close']=c.script('close',path=remote);opened=False;pdf=c.fetch(remote,folder/'reader.pdf')
  actual=style.saved_capture(pdf,summary,source);report['captured']=actual;assert actual=={'results':[v['result'] for v in report['cases']]};assert script_hashes(pdf)==script_hashes(source) and hashlib.sha256(source.read_bytes()).hexdigest()==before;assert c.harness_fingerprint()==ready['harness_sha256'];report['passed']=True
except Exception as e:report['error']=str(e);raise
finally:
 if opened:
  report['retention_required']=remote
  try:
   with c.desktop_lock():
    rows=c.command('inspect');blocking=[v for v in rows if v.get('class')=='#32770']
    for alert in blocking:
     assert alert.get('name')==title,'Unrecognized blocking dialog; preserve it'
     buttons=[v for v in rows if v.get('owner')==alert['handle'] and v.get('class')=='Button' and v.get('enabled')]
     matches=[]
     for label in ['Cancel','No','OK']:
      matches=[v for v in buttons if v.get('name','').replace('&','')==label]
      if matches:break
     assert len(matches)==1
     report['cleanup_button']=c.command('invoke',name=matches[0]['name'],owner=alert['handle'])
    if pending:
     try:report['cleanup_original_completion']=c.script_result(pending,timeout=120)
     except Exception as e:report['cleanup_original_error']=str(e)
    retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
  except Exception as e:report['cleanup_error']=str(e)
 (folder/'control.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'control.json',flush=True)
