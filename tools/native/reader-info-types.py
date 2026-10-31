#!/usr/bin/env python3
"""Observe typed Reader metadata on authorized fixture copies.

Optional custom /Info strings are controlled diagnostic INPUTS, never expected
values written into Reader outputs. Preserve original scripts and all fixtures.
Sorted key sets and typed scalar/array data compare exactly; date epochs replace
locale display text. Enumeration order and metadata mutation are not qualified.
"""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
from pypdf import PdfWriter
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import script_hashes
VALUES={'Integer':'261023','Negative':'-12','LeadingZero':'0012','Decimal':'3.5','Exponent':'1e3','Whitespace':' 42 ','True':'true','NaN':'NaN','Infinity':'Infinity','Empty':'','Zero':'0','Hex':'0x10','Version':'4.2.0','Units':'12px','Unicode':'Ω','False':'false','TrueCapital':'True','FalseCapital':'FALSE','Signed':'+12','Fraction':'.5','NegativeFraction':'-.5','TrailingPoint':'12.','NegativeZero':'-0','FractionZeros':'01.50','Comma':'1,200','Null':'null','Undefined':'undefined','Newline':'1\n','DoubleSign':'--1','ExponentZero':'1e0'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--fixture',choices=['2014','2024','ashnar'],default='2024');p.add_argument('--controlled-strings',action='store_true');a=p.parse_args()
 folder=ROOT/'output/testing'/('reader-info-types-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
 fixture=json.loads((ROOT/'docs/fixtures.json').read_text())[{'2014':0,'2024':1,'ashnar':2}[a.fixture]];source=ROOT/'Testing'/fixture['file'];original=hashlib.sha256(source.read_bytes()).hexdigest();assert original==fixture['sha256'];input_pdf=folder/'input.pdf'
 if a.controlled_strings:
  writer=PdfWriter(clone_from=source);writer.add_metadata({'/MPMBTest'+key:value for key,value in VALUES.items()});writer.write(input_pdf)
 else:input_pdf.write_bytes(source.read_bytes())
 assert script_hashes(input_pdf)==script_hashes(source)
 keys=['MPMBTest'+key for key in VALUES] if a.controlled_strings else []
 observer=folder/'observer.js';observer.write_text('tDoc.__infoTypeKeys='+json.dumps(keys)+';\n'+(ROOT/'tools/native/info-types-observer.js').read_text())
 report={'passed':False,'scope':__doc__,'fixture':a.fixture,'original_sha256':original,'input':str(input_pdf),'controlled_input_strings':VALUES if a.controlled_strings else {},'observer':str(observer)}
 try:
  with (folder/'reader.log').open('w') as log:run=subprocess.run([sys.executable,str(ROOT/'tools/native/reader-script-observation.py'),'--input',str(input_pdf),'--observer',str(observer),'--readiness',str(a.readiness)],stdout=log,stderr=log,timeout=420)
  paths=[s.strip() for s in (folder/'reader.log').read_text().splitlines() if s.strip().endswith('/observation.json')];assert paths;ref=Path(paths[-1]);r=json.loads(ref.read_text());report['reader']=str(ref);assert run.returncode==0 and r['passed'],r.get('error');assert not r['captured']['errors'] and not any('getter_error' in v for v in r['captured']['values'].values());assert len(r['captured']['values'])==len(keys+['Title','Author','Authors','ContactEmail','Subject','Keywords','Creator','Producer','CreationDate','ModDate','Trapped','SheetVersion','SheetVersionType','SheetVersionBuild','SheetType'])*3
  assert hashlib.sha256(source.read_bytes()).hexdigest()==original;report['passed']=True
 finally:(folder/'info-types.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'info-types.json',flush=True)

if __name__=='__main__':main()
