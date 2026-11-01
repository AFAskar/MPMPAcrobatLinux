#!/usr/bin/env python3
"""Read-only physical CO preservation and Reader/native order qualification.

Compare every logical slot, retain the original non-leaf object references and
verify reference/native behavioral assertions. Counts alone are insufficient.
"""
import argparse,hashlib,json,sys
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields,script_hashes

def order(path):
 r=PdfReader(path);names={f['reference']:n for n,f in canonical_fields(r).items()};result=[]
 for ref in r.trailer['/Root']['/AcroForm'].get('/CO',[]):
  assert ref.get_object() is not None
  result.append({'field':names[ref.idnum]} if ref.idnum in names else {'reference':[ref.idnum,ref.generation]})
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--comparison',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();report={'passed':False,'scope':__doc__,'cases':[]}
 try:
  for comparison in a.comparison:
   native=json.loads(comparison.read_text());assert native['passed'];ref=Path(native['reader']);reader=json.loads(ref.read_text());assert reader['passed'];assert native['captured']==reader['captured'];assert not native['captured']['errors'] and all(native['captured']['assertions'].values())
   source=Path(reader['input']);npdf=comparison.parent/'native.pdf';rpdf=ref.parent/'reader.pdf';hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,npdf,rpdf]};original=order(source);rn=order(rpdf);nn=order(npdf);preserved=[e for e in original if 'reference' in e];assert preserved;assert [e for e in rn if 'reference' in e]==preserved;assert [e for e in nn if 'reference' in e]==preserved;assert rn==nn,'Physical calculation slot order differs';assert script_hashes(source)==script_hashes(npdf)==script_hashes(rpdf)
   for path,value in hashes.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==value
   report['cases'].append({'comparison':str(comparison),'sha256':hashes,'ordered_slots':len(nn),'preserved_non_leaf_slots':len(preserved),'behavior_assertions':native['captured']['assertions'],'logical_order_equal':True,'original_group_references_retained':True})
  report['passed']=True
 finally:a.output.write_text(json.dumps(report,indent=2)+'\n');print(a.output)
if __name__=='__main__':main()
