#!/usr/bin/env python3
"""Check read-response text against independent Reader UTF-16 summaries and PDF.

The source copy and synthetic Player Name are disposable. No expected values
are written to a reference PDF through a PDF library.
"""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from pypdf import PdfReader
from verify import canonical_fields

def summary(text):
 b=text.encode('utf-16-le');a=1;s=0
 for i in range(0,len(b),2):a=(a+int.from_bytes(b[i:i+2],'little'))%65521;s=(s+a)%65521
 return {'code_units':len(b)//2,'adler32_utf16':str((s*65536+a)&0xffffffff)}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--readiness',type=Path);p.add_argument('--preflight',type=Path,help='Focused qualification of a new transport before full readiness');a=p.parse_args();assert bool(a.readiness)!=bool(a.preflight);ready=json.loads((a.readiness or a.preflight).read_text());assert ready['passed'];
 if a.readiness:assert ready['harness_sha256']==c.harness_fingerprint()
 else:assert ready['guest']['adapterHash'].lower()==hashlib.sha256((ROOT/'tools/acrobat/windows/mpmb-testing.js').read_bytes()).hexdigest()
 source=a.input.resolve();before=hashlib.sha256(source.read_bytes()).hexdigest();folder=ROOT/'output/testing'/('reader-field-transport-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);remote=c.remote_path('runs/field-transport-'+str(time.time_ns())+'.pdf');opened=False;report={'execution_completed':False,'read_transport_exact':False,'source':str(source),'source_sha256':before,'cases':[]}
 try:
  with c.desktop_lock():
   assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()];subprocess.run(c.SCP+[str(source),c.SCP_TARGET + ':MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote)
   for field,value in [('Class Features',None),('Player Name','Bridge A&B C&&D E&&&F &amp; <x> "quote" \\path')]:
    if value is not None:c.script('set',path=remote,values={field:value})
    actual_summary=c.script('field_summary',path=remote,fields=[field])['fields'][field];text=c.script('read',path=remote,fields=[field])['fields'][field];report['cases'].append({'field':field,'read':text,'reader_summary':actual_summary,'read_summary':summary(text),'exact':summary(text)==actual_summary,'unescape_ampersand_summary':summary(text.replace('&&','&'))})
   saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved;report['close']=c.script('close',path=remote);opened=False;local=c.fetch(remote,folder/'reader.pdf');values=canonical_fields(PdfReader(local))
   for row in report['cases']:row['saved_value']=values[row['field']]['/V'];row['saved_summary']=summary(row['saved_value'])
   assert hashlib.sha256(source.read_bytes()).hexdigest()==before;report['execution_completed']=True;report['read_transport_exact']=all(row['exact'] for row in report['cases'])
 finally:
  if opened:
   try:
    with c.desktop_lock():
     saved=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=saved);report['cleanup_close']=c.script('close',path=saved);c.fetch(saved,folder/'failed-retained.pdf')
   except Exception as error:report['cleanup_error']=str(error)
  (folder/'transport.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'transport.json',flush=True)
if __name__=='__main__':main()
