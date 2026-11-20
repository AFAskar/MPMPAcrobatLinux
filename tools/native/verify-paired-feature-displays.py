#!/usr/bin/env python3
"""Compare exact captured values separately from paired PDF display text.

Report producers must disclose their capture exclusions. This verifier compares
only fields/resources/notesAndActions; it does not establish whole-character,
rich-span, checkbox/button-appearance, geometry, pixel or API compatibility.
"""
from pathlib import Path
import argparse,json,sys,hashlib,subprocess,resource,gc,unicodedata
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/acrobat'),str(ROOT/'tools/native')]
from verify import canonical_fields,inspect,script_hashes
from pypdf import PdfReader
from pypdf.generic import NameObject
from workflow_state_comparison import encoded_state
SELF=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
def file_hash(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def normalized(text):return ' '.join(unicodedata.normalize('NFKC',str(text or '')).split())
def action_hash(node):
 a=node.get('/AA',{}).get('/F');a=a.get_object() if hasattr(a,'get_object') else a
 if not a:return None
 assert a.get('/S')=='/JavaScript';s=a.get('/JS','');s=s.get_object() if hasattr(s,'get_object') else s
 data=s.get_data() if hasattr(s,'get_data') else str(s).encode();return hashlib.sha256(data).hexdigest()
def canonical(path,expected):
 reader=PdfReader(path);fields=canonical_fields(reader);result=[];text={}
 for n,wanted in expected.items():
  rec=fields[n];node=reader.get_object(rec['reference']);flags=int(node.get('/Ff',0));parent=node.get('/Parent')
  while '/Ff' not in node and parent:
   node=parent.get_object();flags=int(node.get('/Ff',0));parent=node.get('/Parent')
  node=reader.get_object(rec['reference']);literal=node.get('/V');value=rec['/V'];logical=value;push=rec['/FT']=='/Btn' and flags&65536
  if rec['/FT']=='/Btn' and not push:logical=str(literal)[1:] if isinstance(literal,NameObject) else 'Off' if value=='' else value
  assert logical==wanted,('Canonical mismatch',n)
  result.append({'field':n,'raw':value,'api':wanted,'type':str(rec['/FT']),'flags':flags,'pushbutton':bool(push),'format_sha256':action_hash(node)})
  if rec['/FT'] in ['/Tx','/Ch']:text[n]=value
 del reader;gc.collect();return result,text
def worker(request,out):
 resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024));q=json.loads(request.read_text());r={'passed':False,'source_sha256':SELF}
 try:
  n,nt=canonical(q['native'],q['expected']);ref,rt=canonical(q['reference'],q['expected']);assert nt==rt;assert [(x['field'],x['format_sha256']) for x in n]==[(x['field'],x['format_sha256']) for x in ref],'Field Format actions differ';r.update(native_canonical=n,reference_canonical=ref)
  if nt:
   a=inspect(q['native'],nt);gc.collect();b=inspect(q['reference'],rt);gc.collect();r['display']=[]
   for name in nt:
    left=[w for w in a['widgets'] if w['name']==name and w['visible']];right=[w for w in b['widgets'] if w['name']==name and w['visible']];assert len(left)==len(right),(name,'visible widget count')
    for x,y in zip(left,right):
     sx,sy=normalized(x['appearance_text']),normalized(y['appearance_text']);same=sx==sy
     if normalized(nt[name]):assert sx and sy,(name,'Populated visible field has no paired display')
     if not same and sx.lstrip('+-').isdigit() and sy.lstrip('+-').isdigit():same=int(sx)==int(sy)
     r['display'].append({'field':name,'native_page':x['page'],'reference_page':y['page'],'native_text':x['appearance_text'],'reference_text':y['appearance_text'],'native_AP':x['appearance'],'reference_AP':y['appearance'],'equal':same});assert same,(name,'formatted display text differs')
  r['passed']=True
 except Exception as e:r['error']=str(e)
 finally:r['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;out.write_text(json.dumps(r,indent=2))
 return 0 if r['passed'] else 1
p=argparse.ArgumentParser();p.add_argument('--native',type=Path);p.add_argument('--reference',type=Path);p.add_argument('--output',type=Path);p.add_argument('--diagnostic-prefix',type=int,help='Explicitly incomplete prefix diagnostic, never a completed workflow pair');p.add_argument('--original',type=Path);p.add_argument('--worker',type=Path);p.add_argument('--worker-output',type=Path);args=p.parse_args()
if args.worker:raise SystemExit(worker(args.worker,args.worker_output))
folder=args.output;folder.mkdir();report={'passed':False,'complete_report_pair':False,'scope':'Exact captured canonical values; matched original Field Format hashes; paired visible AP text normalized only NFKC/whitespace and integer leading signs. Raw canonical and both displays retained separately. Pushbutton/checkbox canonical only; widget geometry/raw-rich/pixel/API coverage NOT claimed. Diagnostic prefix is never a completed workflow pass.','source_sha256':SELF,'phases':[]}
try:
 n=json.loads(args.native.read_text());ref=json.loads(args.reference.read_text());assert n['passed'];count=len(n['phases']) if args.diagnostic_prefix is None else args.diagnostic_prefix;assert 0<count<=min(len(n['phases']),len(ref['phases']));report.update(native_report_sha256=file_hash(args.native),reference_report_sha256=file_hash(args.reference),original=str(args.original) if args.original else None);original_scripts=script_hashes(args.original) if args.original else None
 if args.diagnostic_prefix is None:assert ref['passed'] and len(ref['phases'])==len(n['phases'])
 for i in range(count):
  a,b=n['phases'][i],ref['phases'][i];assert a['label']==b['label'] and encoded_state(a['state'])==encoded_state(b['state']);s=a['state'];expected=dict(s['fields'],**s['resources'],**s['notesAndActions']);names=sorted(expected);phase={'label':a['label'],'batches':[],'native_sha256':file_hash(a['pdf']),'reference_sha256':file_hash(b['pdf'])};report['phases'].append(phase)
  for point,key in [(a,'native_sha256'),(b,'reference_sha256')]:
   if point.get('canonical',{}).get('input_sha256'):assert point['canonical']['input_sha256']==phase[key],'Qualified PDF hash differs'
   if original_scripts is not None:assert script_hashes(point['pdf'])==original_scripts,'Original script hashes differ'
  for bi,start in enumerate(range(0,len(names),8)):
   stem=folder/(str(i)+'-'+str(bi));request=stem.with_suffix('.request.json');out=stem.with_suffix('.result.json');request.write_text(json.dumps({'native':a['pdf'],'reference':b['pdf'],'expected':{k:expected[k] for k in names[start:start+8]}}))
   with stem.with_suffix('.log').open('w') as log:r=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(request),'--worker-output',str(out)],stdout=log,stderr=log,timeout=240)
   data=json.loads(out.read_text());phase['batches'].append({'result':str(out),'returncode':r.returncode,'peak_rss_kib':data.get('peak_rss_kib')});assert r.returncode==0 and data['passed'] and data['source_sha256']==SELF,(a['label'],str(out),data.get('error'))
  assert file_hash(a['pdf'])==phase['native_sha256'] and file_hash(b['pdf'])==phase['reference_sha256'],'PDF changed during comparison'
  (folder/'progress.json').write_text(json.dumps(report,indent=2))
 report.update(passed=True,complete_report_pair=args.diagnostic_prefix is None)
except Exception as e:report['error']=str(e);raise
finally:(folder/'comparison.json').write_text(json.dumps(report,indent=2));print(folder,flush=True)
