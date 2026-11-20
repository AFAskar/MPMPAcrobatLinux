#!/usr/bin/env python3
"""Reject stale text in visible widgets of captured empty resource fields.

Canonical /V must be exactly empty. Appearance text may contain whitespace or
have no appearance; this is not pixel/unchecked-button/rich-layout equality.
Only names in state.resources are covered; unobserved aliases are not qualified.
Each PDF must match its recorded canonical-verification input hash.
Fresh eight-field children use768MiB address-space limits; no PDF is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
SOURCE_HASH=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

def worker(request,output):
 resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
 sys.path.insert(0,str(ROOT/'tools/acrobat'))
 from verify import inspect
 data=json.loads(request.read_text());r={'passed':False,'source_sha256':SOURCE_HASH,'request':str(request)}
 try:
  checked=inspect(data['pdf'],data['expected']);assert checked['passed'], 'Canonical field/widget verification failed'
  assert checked['sha256']==data['pdf_sha256'],'PDF changed'
  visible=[w for w in checked['widgets'] if w['visible']]
  bad=[w for w in visible if str(w['appearance_text'] or '').strip()]
  r.update(verification=checked,visible_empty_widgets=len(visible),missing_appearances=sum(not w['appearance'] for w in visible),stale_widgets=bad)
  assert not bad,'Visible empty resource has nonempty appearance text'
  r['passed']=True
 except Exception as e:r['error']=str(e)
 finally:r['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;output.write_text(json.dumps(r,indent=2))
 return 0 if r['passed'] else 1

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--report',type=Path,action='append')
 parser.add_argument('--output',type=Path)
 parser.add_argument('--worker',type=Path)
 parser.add_argument('--worker-output',type=Path)
 args=parser.parse_args()
 if args.worker:return worker(args.worker,args.worker_output)
 assert args.report and args.output;folder=args.output;folder.mkdir(parents=True,exist_ok=False)
 report={'passed':False,'scope':__doc__,'source_sha256':SOURCE_HASH,'reports':[]}
 try:
  for ri,path in enumerate(args.report):
   data=json.loads(path.read_text());assert data['passed'] is True and data['phases'],'Require completed successful workflow'
   phases=data['phases'];labels=[p['label'] for p in phases];assert len(set(labels))==len(labels)
   entry={'report':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'phases':[]};report['reports'].append(entry)
   for pi,phase in enumerate(phases):
    expected={k:v for k,v in phase['state']['resources'].items() if v==''}
    assert expected and all(re.fullmatch(r'Limited Feature (?:Max Usages |Used |Recovery )?\d+',n) for n in expected)
    pdf=Path(phase['pdf']);pdf_hash=hashlib.sha256(pdf.read_bytes()).hexdigest();assert pdf_hash==phase['canonical']['input_sha256'],'Workflow PDF hash differs from qualified canonical input';item={'label':phase['label'],'pdf':str(pdf),'pdf_sha256':pdf_hash,'captured_resource_fields':len(phase['state']['resources']),'empty_field_count':len(expected),'batches':[],'visible_empty_widgets':0,'missing_appearances':0};entry['phases'].append(item);names=sorted(expected)
    for bi,start in enumerate(range(0,len(names),8)):
     prefix=folder/(str(ri)+'-'+str(pi)+'-'+str(bi));request=prefix.with_suffix('.request.json');result=prefix.with_suffix('.result.json');request.write_text(json.dumps({'pdf':str(pdf.resolve()),'pdf_sha256':pdf_hash,'expected':{n:'' for n in names[start:start+8]}}))
     with prefix.with_suffix('.log').open('w') as log:process=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(request),'--worker-output',str(result)],stdout=log,stderr=log,timeout=180)
     child=json.loads(result.read_text()) if result.exists() else {'passed':False,'error':'No completed child response'}
     item['batches'].append({'result':str(result),'returncode':process.returncode,'peak_rss_kib':child.get('peak_rss_kib')})
     assert process.returncode==0 and child['passed'] and child['source_sha256']==SOURCE_HASH,(phase['label'],str(result),child.get('error'))
     item['visible_empty_widgets']+=child['visible_empty_widgets'];item['missing_appearances']+=child['missing_appearances']
    assert item['visible_empty_widgets']>0,'No visible empty widgets observed'
    assert hashlib.sha256(pdf.read_bytes()).hexdigest()==pdf_hash
    (folder/'progress.json').write_text(json.dumps(report,indent=2))
   assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
  assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==SOURCE_HASH
  report['passed']=True
 except Exception as e:report['error']=str(e);raise
 finally:(folder/'blank-resource-appearances.json').write_text(json.dumps(report,indent=2));print(folder,flush=True)
 return 0


if __name__=='__main__':raise SystemExit(main())
