#!/usr/bin/env python3
"""Read-only recovery of completed progression affected by proven alert escaping.

Preserves the original failed report. Applies only the experimentally verified
old alert ampersand inverse, and records API Off versus absent checkbox V as a
separate logical/raw comparison. Never changes saved Reader PDFs.
"""
import argparse,hashlib,importlib.util,json,re,sys
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields,inspect,script_hashes
spec=importlib.util.spec_from_file_location('field_state',ROOT/'tools/native/field-state-comparison.py');field_state=importlib.util.module_from_spec(spec);spec.loader.exec_module(field_state)

def decode(value):
 if isinstance(value,str):
  assert all(len(s)%2==0 for s in re.findall(r'&+',value)),'Unpaired transport ampersand'
  return value.replace('&&','&')
 if isinstance(value,list):return [decode(v) for v in value]
 if isinstance(value,dict):return {decode(k):decode(v) for k,v in value.items()}
 return value

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--completed',type=Path,required=True);p.add_argument('--transport-proof',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();proof=json.loads(a.transport_proof.read_text());assert proof['execution_completed'] and not proof['read_transport_exact'];assert all(row['unescape_ampersand_summary']==row['reader_summary']==row['saved_summary'] for row in proof['cases']);original=json.loads(a.completed.read_text());assert not original['passed'] and 'close' in original;source=Path(original['input']);assert hashlib.sha256(source.read_bytes()).hexdigest()==original['input_sha256'];report={**original,'passed':False,'scope':__doc__,'recovered_from':str(a.completed),'transport_proof':str(a.transport_proof),'raw_report_still_failed':True,'phases':[]}
 try:
  for stage in original['phases']:
   pdf=Path(stage['pdf']);before=hashlib.sha256(pdf.read_bytes()).hexdigest();r=PdfReader(pdf);fields=canonical_fields(r);logical=decode(stage['fields']);raw_expected={};normalization=[]
   normalized=field_state.compare(pdf,logical);raw_expected=normalized['raw_expected'];normalization=normalized['representation_rules']
   checked=inspect(pdf,raw_expected);assert checked['actual']==raw_expected and checked['widgets'] and all(w['matches'] for w in checked['widgets']);assert script_hashes(pdf)==script_hashes(source);assert hashlib.sha256(pdf.read_bytes()).hexdigest()==before;report['phases'].append({**stage,'fields':logical,'original_transport_fields':stage['fields'],'logical_raw_normalization':normalization,'raw_expected':raw_expected,'canonical_widgets_scripts':True,'pdf_sha256':before})
  report['passed']=True
 finally:a.output.write_text(json.dumps(report,indent=2)+'\n');print(a.output)
if __name__=='__main__':main()
