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
def _require(condition, message):
 if not condition:raise AssertionError(message)
def file_hash(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def producer_digests(point):
 found={}
 if point.get('pdf_sha256'):found['pdf_sha256']=point['pdf_sha256']
 canonical_block=point.get('canonical') or {}
 if canonical_block.get('input_sha256'):found['canonical.input_sha256']=canonical_block['input_sha256']
 independent=canonical_block.get('independent') or {}
 if independent.get('sha256'):found['canonical.independent.sha256']=independent['sha256']
 return found
def normalized(text):return ' '.join(unicodedata.normalize('NFKC',str(text or '')).split())
def action_hash(node):
 a=node.get('/AA',{}).get('/F');a=a.get_object() if hasattr(a,'get_object') else a
 if not a:return None
 _require(a.get('/S')=='/JavaScript',('Non-JavaScript Format action',a.get('/S')));s=a.get('/JS','');s=s.get_object() if hasattr(s,'get_object') else s
 data=s.get_data() if hasattr(s,'get_data') else str(s).encode();return hashlib.sha256(data).hexdigest()
def canonical(path,expected):
 reader=PdfReader(path);fields=canonical_fields(reader);result=[];text={}
 for n,wanted in expected.items():
  rec=fields[n];node=reader.get_object(rec['reference']);flags=int(node.get('/Ff',0));parent=node.get('/Parent')
  while '/Ff' not in node and parent:
   node=parent.get_object();flags=int(node.get('/Ff',0));parent=node.get('/Parent')
  node=reader.get_object(rec['reference']);literal=node.get('/V');value=rec['/V'];logical=value;push=rec['/FT']=='/Btn' and flags&65536
  if rec['/FT']=='/Btn' and not push:logical=str(literal)[1:] if isinstance(literal,NameObject) else 'Off' if value=='' else value
  _require(logical==wanted,('Canonical mismatch',n))
  result.append({'field':n,'raw':value,'api':wanted,'type':str(rec['/FT']),'flags':flags,'pushbutton':bool(push),'format_sha256':action_hash(node)})
  if rec['/FT'] in ['/Tx','/Ch']:text[n]=value
 del reader;gc.collect();return result,text
def worker(request,out):
 resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024));q=json.loads(request.read_text());r={'passed':False,'source_sha256':SELF}
 try:
  n,nt=canonical(q['native'],q['expected']);ref,rt=canonical(q['reference'],q['expected']);_require(nt==rt,'Text field sets differ');_require([(x['field'],x['format_sha256']) for x in n]==[(x['field'],x['format_sha256']) for x in ref],'Field Format actions differ');r.update(native_canonical=n,reference_canonical=ref)
  if nt:
   a=inspect(q['native'],nt);gc.collect();b=inspect(q['reference'],rt);gc.collect();r['display']=[]
   for name in nt:
    left=[w for w in a['widgets'] if w['name']==name and w['visible']];right=[w for w in b['widgets'] if w['name']==name and w['visible']];_require(len(left)==len(right),(name,'visible widget count'))
    if normalized(nt[name]):_require(left and right,(name,'Populated field has no visible widgets'))
    for x,y in zip(left,right):
     _require(x['page']==y['page'],(name,'visible widget page mismatch',x['page'],y['page']))
     sx,sy=normalized(x['appearance_text']),normalized(y['appearance_text']);same=sx==sy
     if normalized(nt[name]):_require(sx and sy,(name,'Populated visible field has no paired display'))
     if not same and sx.lstrip('+-').isdigit() and sy.lstrip('+-').isdigit():same=int(sx)==int(sy)
     r['display'].append({'field':name,'native_page':x['page'],'reference_page':y['page'],'native_text':x['appearance_text'],'reference_text':y['appearance_text'],'native_AP':x['appearance'],'reference_AP':y['appearance'],'equal':same});_require(same,(name,'formatted display text differs'))
  r['passed']=True
 except Exception as e:r['error']=str(e)
 finally:r['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;out.write_text(json.dumps(r,indent=2))
 return 0 if r['passed'] else 1
p=argparse.ArgumentParser();p.add_argument('--native',type=Path);p.add_argument('--reference',type=Path);p.add_argument('--output',type=Path);p.add_argument('--diagnostic-prefix',type=int,help='Explicitly incomplete prefix diagnostic, never a completed workflow pair');p.add_argument('--original',type=Path);p.add_argument('--worker',type=Path);p.add_argument('--worker-output',type=Path);args=p.parse_args()
if args.worker:raise SystemExit(worker(args.worker,args.worker_output))
folder=args.output;folder.mkdir();report={'passed':False,'complete_report_pair':False,'scope':'Exact captured canonical values; verified producer PDF provenance digests; matched original Field Format hashes; paired visible AP text matched by logical page and occurrence, normalized only NFKC/whitespace and integer leading signs. Raw canonical and both displays retained separately. Pushbutton/checkbox canonical only; widget geometry/raw-rich/pixel/API coverage NOT claimed. Diagnostic prefix is never a completed workflow pass.','source_sha256':SELF,'phases':[]}
try:
 n=json.loads(args.native.read_text());ref=json.loads(args.reference.read_text());_require(n.get('passed') is True,'Native report must have passed=True');count=len(n['phases']) if args.diagnostic_prefix is None else args.diagnostic_prefix;_require(0<count<=min(len(n['phases']),len(ref['phases'])),'Invalid phase count');report.update(native_report_sha256=file_hash(args.native),reference_report_sha256=file_hash(args.reference),original=str(args.original) if args.original else None);original_scripts=script_hashes(args.original) if args.original else None
 if args.diagnostic_prefix is None:_require(ref.get('passed') is True and len(ref['phases'])==len(n['phases']),'Reference report must pass with matching phase count')
 for i in range(count):
  a,b=n['phases'][i],ref['phases'][i];_require(a['label']==b['label'] and encoded_state(a['state'])==encoded_state(b['state']),('Phase label or state mismatch',a.get('label'),b.get('label')));s=a['state'];expected=dict(s['fields'],**s['resources'],**s['notesAndActions']);names=sorted(expected);_require(bool(names),('Phase has no captured fields/resources/notesAndActions to compare',a['label']));phase={'label':a['label'],'batches':[],'native_sha256':file_hash(a['pdf']),'reference_sha256':file_hash(b['pdf'])};report['phases'].append(phase)
  for point,key in [(a,'native_sha256'),(b,'reference_sha256')]:
   recorded=producer_digests(point)
   _require(bool(recorded),('Missing producer PDF sha256 digest',a['label'],key))
   for digest_key,digest_val in recorded.items():
    _require(digest_val==phase[key],('Qualified PDF hash differs',a['label'],key,digest_key,digest_val,phase[key]))
   if original_scripts is not None:_require(script_hashes(point['pdf'])==original_scripts,'Original script hashes differ')
  for bi,start in enumerate(range(0,len(names),8)):
   stem=folder/(str(i)+'-'+str(bi));request=stem.with_suffix('.request.json');out=stem.with_suffix('.result.json');request.write_text(json.dumps({'native':a['pdf'],'reference':b['pdf'],'expected':{k:expected[k] for k in names[start:start+8]}}))
   with stem.with_suffix('.log').open('w') as log:r=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(request),'--worker-output',str(out)],stdout=log,stderr=log,timeout=240)
   data=json.loads(out.read_text());phase['batches'].append({'result':str(out),'returncode':r.returncode,'peak_rss_kib':data.get('peak_rss_kib')});_require(r.returncode==0 and data.get('passed') is True and data.get('source_sha256')==SELF,(a['label'],str(out),data.get('error')))
  _require(bool(phase['batches']),('Phase executed zero comparison batches',a['label']))
  _require(file_hash(a['pdf'])==phase['native_sha256'] and file_hash(b['pdf'])==phase['reference_sha256'],'PDF changed during comparison')
  (folder/'progress.json').write_text(json.dumps(report,indent=2))
 report.update(passed=True,complete_report_pair=args.diagnostic_prefix is None)
except Exception as e:report['error']=str(e);raise
finally:(folder/'comparison.json').write_text(json.dumps(report,indent=2));print(folder,flush=True)
