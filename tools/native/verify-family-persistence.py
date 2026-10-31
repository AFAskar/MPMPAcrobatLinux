#!/usr/bin/env python3
"""Read-only AP face/text/vertical checks for mixed-font persistence.

Font-property checks are a defined subset. Full span API equality, horizontal
advance/topology and full pixel compatibility are not claimed.
"""
import argparse,hashlib,importlib.util,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import inspect,script_hashes
spec=importlib.util.spec_from_file_location('matrix',ROOT/'tools/native/rich-decoration-matrix.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def face(name):return re.sub('[^a-z0-9]','',re.sub(r'^(?:MPMB|[A-Z]{6}\+)', '',name.lstrip('/')).lower())
def same(a,b):
 if len(a)!=len(b):return False
 for left,right in zip(a,b):
  if len(left['rows'])!=len(right['rows']):return False
  for x,y in zip(left['rows'],right['rows']):
   if face(x['font']['base_font'])!=face(y['font']['base_font']) or abs(x['baseline']['size']-y['baseline']['size'])>.001:return False
   gx=sorted(x['geometry'],key=lambda g:g['offset']);gy=sorted(y['geometry'],key=lambda g:g['offset'])
   if len(gx)!=len(gy) or any(abs(p['offset']-q['offset'])>.002 or abs(p['thickness']-q['thickness'])>.002 for p,q in zip(gx,gy)):return False
 return True

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--persistence',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--negative-fonts-pdf',type=Path);a=p.parse_args();assert not a.report.exists();data=json.loads(a.persistence.read_text());assert data['passed'];source=Path(data['source']);assert hashlib.sha256(source.read_bytes()).hexdigest()==data['source_sha256'];first=data['native'][0]['captured'];reference=m.measure(source,first);scripts=script_hashes(source);report={'passed':False,'scope':__doc__,'persistence':str(a.persistence),'cases':[]}
 try:
  native=[(Path(case['path']),case['captured']) for case in data['native']];ref=Path(data['reader']);reader=json.loads(ref.read_text());assert reader['passed'];native.append((ref.parent/'reader.pdf',reader['captured']))
  for pdf,capture in native:
   before=hashlib.sha256(pdf.read_bytes()).hexdigest();measured=m.measure(pdf,capture);equal=same(reference,measured);checked=inspect(pdf,{'Extra.Notes':capture['field']['value']});assert checked['passed'];assert any(w['visible'] and w['appearance_matches'] for w in checked['widgets']);assert equal and script_hashes(pdf)==scripts;assert hashlib.sha256(pdf.read_bytes()).hexdigest()==before;report['cases'].append({'pdf':str(pdf),'sha256':before,'actual_faces_sizes_vertical_equal':equal,'independent':checked})
  if a.negative_fonts_pdf:
   before=hashlib.sha256(a.negative_fonts_pdf.read_bytes()).hexdigest();negative=m.measure(a.negative_fonts_pdf,first);report['negative_wrong_face_rejected']=not same(reference,negative);assert report['negative_wrong_face_rejected'];assert hashlib.sha256(a.negative_fonts_pdf.read_bytes()).hexdigest()==before
  report['passed']=True
 finally:a.report.write_text(json.dumps(report,indent=2)+'\n');print(a.report)
if __name__=='__main__':main()
