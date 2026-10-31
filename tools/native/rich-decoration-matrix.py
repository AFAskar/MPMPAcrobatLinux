#!/usr/bin/env python3
"""Measure actual saved AP decoration geometry and embedded font metrics.

Original target actions are deliberately cleared. Execution/measurement passing
is not a compatibility pass; original notes formatting remains a separate gate.
No coordinates or expected values are written into Reader outputs.
"""
import argparse,hashlib,json,math,struct,subprocess,sys,time
from pathlib import Path
from pypdf import PdfReader
from pypdf.generic import ContentStream
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields,script_hashes

def font_metrics(font):
 font=font.get_object();descendant=font.get('/DescendantFonts');font=descendant[0].get_object() if descendant else font;descriptor=font.get('/FontDescriptor',{});descriptor=descriptor.get_object() if hasattr(descriptor,'get_object') else descriptor
 result={'base_font':str(font.get('/BaseFont')),'descriptor':{k:str(descriptor[k]) for k in ['/FontName','/Ascent','/Descent','/CapHeight','/FontBBox','/StemV'] if k in descriptor}}
 program=descriptor.get('/FontFile2') or descriptor.get('/FontFile3')
 if not program:return result
 data=program.get_object().get_data();result['program_sha256']=hashlib.sha256(data).hexdigest();result['program_bytes']=len(data)
 if data[:4] not in [b'\x00\x01\x00\x00',b'OTTO',b'true']:return result
 count=struct.unpack_from('>H',data,4)[0];tables={}
 for i in range(count):
  tag,checksum,offset,length=struct.unpack_from('>4sIII',data,12+i*16);assert offset+length<=len(data);tables[tag]=data[offset:offset+length]
 values={}
 for table,entries in {b'head':{'upem':(18,'H'),'xmin':(36,'h'),'ymin':(38,'h'),'xmax':(40,'h'),'ymax':(42,'h')},b'post':{'underline_position':(8,'h'),'underline_thickness':(10,'h')},b'OS/2':{'strike_thickness':(26,'h'),'strike_position':(28,'h'),'typo_ascent':(68,'h'),'typo_descent':(70,'h'),'typo_gap':(72,'h')},b'hhea':{'hhea_ascent':(4,'h'),'hhea_descent':(6,'h'),'hhea_gap':(8,'h')}}.items():
  if table in tables:
   for key,(offset,fmt) in entries.items():
    if len(tables[table])>=offset+2:values[key]=struct.unpack_from('>'+fmt,tables[table],offset)[0]
 result['metrics']=values;return result

def measure(pdf,captured):
 r=PdfReader(pdf);fields=canonical_fields(r);field=r.get_object(fields['Extra.Notes']['reference']);active={a.idnum for p in r.pages for a in p.get('/Annots',[])};result=[]
 for ref in field.get('/Kids',[field]):
  widget=ref.get_object()
  if widget.indirect_reference.idnum not in active:continue
  ap=widget['/AP']['/N'].get_object();fonts={str(k):font_metrics(v) for k,v in ap['/Resources']['/Font'].items()};baselines=[];paths=[];x=y=0.;leading=0.;width=1.;start=end=None;font=None;size=None
  for args,op in ContentStream(ap,r).operations:
   if op==b'BT':x=y=0.;leading=0.
   elif op==b'Tf':font=str(args[0]);size=float(args[1])
   elif op==b'Tm':
    assert list(map(float,args[:4]))==[1.,0.,0.,1.], 'Unsupported text transform';x,y=map(float,args[4:])
   elif op in [b'Td',b'TD']:
    x+=float(args[0]);y+=float(args[1])
    if op==b'TD':leading=-float(args[1])
   elif op==b'TL':leading=float(args[0])
   elif op==b'T*':y-=leading
   elif op in [b'Tj',b'TJ']:
    if not any(abs(b['y']-y)<.001 for b in baselines):baselines.append({'x':x,'y':y,'size':size,'font':font})
   elif op==b'cm':assert list(map(float,args))==[1.,0.,0.,1.,0.,0.], 'Unsupported graphics transform'
   elif op==b'w':width=float(args[0])
   elif op==b'm':start=list(map(float,args))
   elif op==b'l':end=list(map(float,args))
   elif op in [b'S',b's']:
    if start is not None and end is not None and abs(start[1]-end[1])<.001 and end[0]>start[0]:paths.append({'x1':start[0],'x2':end[0],'y':start[1],'thickness':width})
    start=end=None
  baselines.sort(key=lambda b:-b['y']);assert len(baselines)==len(captured['cases']), f'Expected {len(captured["cases"])} nonempty rows, got {len(baselines)}'
  rows=[]
  for index,(baseline,case) in enumerate(zip(baselines,captured['cases'])):
   getter_size=captured['field']['spans'][index]['textSize'];assert abs(baseline['size']-getter_size)<.001, 'AP differs from actual getter size'
   selected=[]
   for path in paths:
    nearest=min(range(len(baselines)),key=lambda n:abs(path['y']-baselines[n]['y']))
    if nearest==index and abs(path['y']-baseline['y'])<baseline['size']/2:
     selected.append({**path,'offset':path['y']-baseline['y']})
   geometry=[]
   for path in selected:
    if not any(abs(p['offset']-path['offset'])<.001 and abs(p['thickness']-path['thickness'])<.001 for p in geometry):geometry.append({'offset':path['offset'],'thickness':path['thickness']})
   assert any(p['offset']<0 for p in geometry)==case['underline'];assert any(p['offset']>0 for p in geometry)==case['strike'];assert all(math.isfinite(v) for p in geometry for v in p.values())
   rows.append({'case':case,'getter_size':getter_size,'requested_size_equal':abs(baseline['size']-case['size'])<.001,'baseline':baseline,'geometry':geometry,'paths':selected,'font':fonts[baseline['font']]})
  result.append({'bbox':list(map(float,ap['/BBox'])),'rows':rows})
 assert result,'No active target appearance';return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--readiness',type=Path);p.add_argument('--observation',type=Path,help='Measure an already completed Reader/native observation');p.add_argument('--pdf',type=Path,help='Override saved PDF for an existing capture');p.add_argument('--failed-comparison-diagnostic',action='store_true',help='Read completed native data from a failed comparison without qualifying it');p.add_argument('--holdout',action='store_true',help='Additional families and fractional sizes after freezing a hypothesis');a=p.parse_args()
 folder=ROOT/'output/testing'/('rich-decoration-matrix-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);report={'measurement_completed':False,'scope':__doc__,'compatibility_pass':False}
 try:
  ref=a.observation
  if ref is None:
   assert a.readiness
   source=next((ROOT/'Testing').glob('*_2024_*.pdf'));observer=ROOT/'tools/native/rich-decoration-observer.js'
   if a.holdout:
    cases=[{'family':family,'weight':400,'style':'normal','size':size,'underline':True,'strike':True} for family in ['Georgia','Verdana','Tahoma','Trebuchet MS'] for size in [8.5,12.25,17.75]]
    selected=folder/'observer.js';selected.write_text('tDoc.__decorationCases='+json.dumps(cases)+';\n'+observer.read_text());observer=selected;report['profile']='held-out families/fractional sizes'
   else:report['profile']='initial26 rows'
   with (folder/'reader.log').open('w') as log:run=subprocess.run([sys.executable,str(ROOT/'tools/native/reader-script-observation.py'),'--input',str(source),'--observer',str(observer),'--readiness',str(a.readiness)],stdout=log,stderr=log,timeout=420)
   paths=[s.strip() for s in (folder/'reader.log').read_text().splitlines() if s.strip().endswith('/observation.json')];assert paths;ref=Path(paths[-1]);assert run.returncode==0
  data=json.loads(ref.read_text());assert data.get('passed') or (a.failed_comparison_diagnostic and data.get('strict_native_probe_passed'));report['source_observation_passed']=data.get('passed');report['observation']=str(ref.resolve());captured=data['captured'];pdf=a.pdf or ref.parent/'reader.pdf';before=hashlib.sha256(pdf.read_bytes()).hexdigest();report.update({'observation':str(ref.resolve()),'pdf':str(pdf.resolve()),'pdf_sha256':before,'captured':captured,'appearances':measure(pdf,captured)});assert script_hashes(pdf)==script_hashes(Path(data.get('input',data.get('source'))));assert hashlib.sha256(pdf.read_bytes()).hexdigest()==before;report['measurement_completed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'matrix.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'matrix.json',flush=True)

if __name__=='__main__':main()
