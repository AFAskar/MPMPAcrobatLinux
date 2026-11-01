#!/usr/bin/env python3
"""Compare vertical decoration metrics without hiding API or horizontal gaps."""
import argparse,json,re
from pathlib import Path

def face(name):return re.sub('[^a-z0-9]','',re.sub(r'^(?:MPMB|[A-Z]{6}\+)', '',name.lstrip('/')).lower())
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--require-api-equality',action='store_true');p.add_argument('--require-mode-topology',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();r=json.loads(a.reader.read_text());n=json.loads(a.native.read_text());assert r['measurement_completed'] and n['measurement_completed'];assert len(r['appearances'])==len(n['appearances'])
 report={'vertical_geometry_passed':False,'scope':'Match actual face/size and all measured Y-offset/stroke-width pairs within0.002pt. API capture equality, horizontal endpoints and path topology are reported separately. Full rendering/MPMB compatibility is not established.','reader':str(a.reader),'native':str(a.native),'api_capture_equal':r['captured']==n['captured'],'compatibility_pass':False,'rows':[]}
 try:
  for rr,nn in zip(r['appearances'],n['appearances']):
   assert len(rr['rows'])==len(nn['rows'])
   for source,target in zip(rr['rows'],nn['rows']):
    rg=sorted(source['geometry'],key=lambda g:g['offset']);ng=sorted(target['geometry'],key=lambda g:g['offset']);same_face=face(source['font']['base_font'])==face(target['font']['base_font']);same_size=abs(source['baseline']['size']-target['baseline']['size'])<.001
    errors=[{'offset':b['offset']-c['offset'],'thickness':b['thickness']-c['thickness']} for c,b in zip(rg,ng)];vertical=same_face and same_size and len(rg)==len(ng) and all(abs(v)<=.002 for e in errors for v in e.values())
    horizontal=[]
    for kind in [-1,1]:
     rs=[x for x in source['paths'] if x['offset']*kind>0];ns=[x for x in target['paths'] if x['offset']*kind>0]
     if rs and ns:horizontal.append({'kind':kind,'x1_error':min(x['x1'] for x in ns)-min(x['x1'] for x in rs),'x2_error':max(x['x2'] for x in ns)-max(x['x2'] for x in rs),'reader_segments':len(rs),'native_segments':len(ns)})
    report['rows'].append({'case':source['case'],'same_face':same_face,'same_size':same_size,'errors':errors,'vertical_passed':vertical,'mode_topology_equal':all(len([p for p in source['paths'] if p['offset']*kind>0])==len([p for p in target['paths'] if p['offset']*kind>0]) for kind in [-1,1]),'horizontal':horizontal})
  report['vertical_geometry_passed']=all(row['vertical_passed'] for row in report['rows']);assert report['vertical_geometry_passed'],'Vertical geometry differs'
  report['mode_topology_equal']=all(row['mode_topology_equal'] for row in report['rows'])
  if a.require_api_equality:assert report['api_capture_equal'],'Full API capture differs'
  if a.require_mode_topology:assert report['mode_topology_equal'],'Actual decoration segment counts differ'
 finally:a.output.write_text(json.dumps(report,indent=2)+'\n');print(a.output)
if __name__=='__main__':main()
