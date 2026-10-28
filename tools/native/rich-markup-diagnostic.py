#!/usr/bin/env python3
"""Diagnose Reader rich-markup versions using disposable native inputs.

This changes native diagnostic inputs only, never Reader outputs. Observations
are not implementation qualification. The unchanged final variant is a control.
"""
import sys,json,time,subprocess,hashlib,re,argparse
from pathlib import Path
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject,ByteStringObject,NumberObject,DictionaryObject
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/acrobat'));import control as c
from verify import canonical_fields,field_text,script_hashes
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('native',type=Path);parser.add_argument('reader_authored',type=Path);parser.add_argument('--readiness',type=Path,required=True);args=parser.parse_args()
qualification=json.loads(args.readiness.read_text());assert qualification['passed'] and len(qualification['cases'])==24
base,gold=[p.resolve() for p in [args.native,args.reader_authored]]
for path in [base,gold]:assert path.is_relative_to(ROOT/'output/testing'), 'Use disposable local run inputs only'
folder=ROOT/'output/testing'/('rich-markup-version-variants-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
br=PdfReader(base);gr=PdfReader(gold)
def node(r,n):return r.get_object(canonical_fields(r)[n]['reference'])
raw=field_text(node(br,'Extra.Notes')['/RV']);goldxml=field_text(node(gr,'Extra.Notes')['/RV']);value=field_text(node(br,'Extra.Notes')['/V']);names=['Personality Trait','Ideal','Bond','Flaw','Extra.Notes']
variants=[goldxml.replace('Acrobat:26.2.0','Acroform:2.7.0.0'),goldxml.replace('xfa:spec="2.0.2"','xfa:spec="2.1"'),goldxml.replace('Acrobat:26.2.0','MPMBNative:0.1.0'),re.sub(r' xfa:APIVersion="[^"]*"','',goldxml),goldxml]
assert script_hashes(base)==script_hashes(gold), 'Different original document scripts'
assert field_text(node(br,'Extra.Notes')['/V'])==field_text(node(gr,'Extra.Notes')['/V']), 'Different authored text'
fields=canonical_fields(br)
for i,name in enumerate(names):
 f=br.get_object(fields[name]['reference']);f[NameObject('/RV')]=ByteStringObject(b'\xfe\xff'+variants[i].encode('utf-16-be'));f[NameObject('/V')]=node(br,'Extra.Notes')['/V'];f[NameObject('/DS')]=node(br,'Extra.Notes')['/DS'];f[NameObject('/Ff')]=NumberObject(int(f.get('/Ff',0))|33554432|4096);f[NameObject('/AA')]=DictionaryObject()
 for k in f.get('/Kids',[]):k.get_object()[NameObject('/AA')]=DictionaryObject()
local=folder/'native-variants.pdf';PdfWriter(clone_from=br).write(local);assert script_hashes(local)==script_hashes(base)
addon="var iFileName='Observe native markup variants.js';(function(d){var result={};"+json.dumps(names)+".forEach(function(n){var f=d.getField(n);result[n]={value:f.valueAsString,spans:f.richValue}});result.sentinel='\\u00a0\\u2028\\ud83d\\ude00';Value('PC Name',JSON.stringify(result).replace(/[\\u007f-\\uffff]/g,function(c){return '\\\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"
report={'scope':'Diagnostic native inputs only; PDF library changes native inputs, never Reader outputs. Five positive-backbone variants isolate legacy producer, spec 2.1, native producer, omitted producer; final control unchanged. Not implementation qualification.','readiness':str(args.readiness.resolve()),'inputs':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [base,gold]],'addon_sha256':hashlib.sha256(addon.encode()).hexdigest(),'variants':dict(zip(names,['legacy producer only','spec 2.1 only','native producer','omitted producer','unchanged positive control']))}
try:
 with c.desktop_lock():
  assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()]
  remote='runs/rich-markup-variants-'+str(time.time_ns())+'.pdf';report['remote']=remote;subprocess.run(c.SCP+[str(local),'mpmb-test@127.0.0.1:MPMB-Testing/'+remote],check=True,capture_output=True);path=c.remote_path(remote)
  c.script('set',path=path,values={'User Script':addon});c.script('call',path=path,name='RunUserScript',args=[False]);summary=c.script('field_summary',path=path,fields=['PC Name'])['fields']['PC Name'];c.script('set',path=path,values={'User Script':''});saved=path[:-4]+'-reader.pdf';c.script('save',path=path,output=saved);c.script('close',path=saved);output=c.fetch(saved,folder/'reader.pdf');text=canonical_fields(PdfReader(output))['PC Name']['/V'];a,b=1,0
  for ch in text:a=(a+ord(ch))%65521;b=(b+a)%65521
  assert summary=={'code_units':len(text),'adler32_utf16':str((b*65536+a)&0xffffffff)};data=json.loads(text);assert [ord(ch) for ch in data.pop('sentinel')]==[160,8232,128512];assert script_hashes(output)==script_hashes(base);report['reader']=data;report['summary']=summary;report['execution_completed']=True
except Exception as e:report['error']=str(e);raise
finally:(folder/'variants.json').write_text(json.dumps(report,indent=2));print(folder/'variants.json',flush=True)
