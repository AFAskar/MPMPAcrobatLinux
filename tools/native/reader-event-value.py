#!/usr/bin/env python3
"""Freeze original actions for the isolated event.value setter type diagnostic."""
import argparse,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
spec=importlib.util.spec_from_file_location('events',ROOT/'tools/native/reader-xfdf-events.py');events=importlib.util.module_from_spec(spec);spec.loader.exec_module(events)


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--observer',type=Path,default=ROOT/'tools/native/event-value-write-observer.js');p.add_argument('--expected-cases',type=int,default=68);p.add_argument('--observer-options',default='{}');p.add_argument('--hide-carrier',action='store_true',help='Hide diagnostic PC Name widget before writing a large JSON trace');p.add_argument('--carrier-size',type=float,help='Explicit fixed point size on the diagnostic carrier');args=p.parse_args();options=json.loads(args.observer_options);assert isinstance(options,dict)
 source=next((ROOT/'Testing').glob('*_2024_*.pdf'));original=events.actions(source);folder=ROOT/'output/testing'/('reader-event-value-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
 originals={'player':{kind:original['Player Name'][key] for kind,key in [('Keystroke','K'),('Validate','V'),('Format','F')]},'calc':original['Str Mod']['C']};assert originals['calc']
 from pypdf import PdfReader
 from verify import canonical_fields,field_text
 pdf=PdfReader(source);node=pdf.get_object(canonical_fields(pdf)['Str Mod']['reference']);aa=node.get('/AA',{});aa=aa.get_object() if hasattr(aa,'get_object') else aa
 originals['calcEvents']={kind:field_text(aa['/'+key].get_object().get('/JS','')) if '/'+key in aa else '' for kind,key in [('Keystroke','K'),('Validate','V'),('Format','F')]}
 public=args.observer;public_bytes=public.read_bytes();carrier_setup=('tDoc.getField("PC Name").display=display.hidden;\n' if args.hide_carrier else '')
 if args.carrier_size is not None:
  import math
  assert math.isfinite(args.carrier_size) and args.carrier_size>0;carrier_setup+='tDoc.getField("PC Name").textSize='+json.dumps(args.carrier_size)+';\n'
 observer=folder/'observer.js';observer.write_text(carrier_setup+'tDoc.__eventWriteOriginal='+json.dumps(originals,ensure_ascii=True)+';tDoc.__eventProbeOptions='+json.dumps(options,ensure_ascii=True)+';\n'+public_bytes.decode('utf-8'))
 with (folder/'reader.log').open('w') as log:run=subprocess.run([sys.executable,str(ROOT/'tools/native/reader-script-observation.py'),'--input',str(source),'--observer',str(observer),'--readiness',str(args.readiness)],stdout=log,stderr=log,timeout=420)
 paths=[line.strip() for line in (folder/'reader.log').read_text().splitlines() if line.strip().endswith('/observation.json')];assert paths
 ref=Path(paths[-1]);report=json.loads(ref.read_text());assert run.returncode==0 and report['passed'],report.get('error');assert not report['captured']['errors'] and len(report['captured']['cases'])==args.expected_cases
 assert all(case.get('trace') for case in report['captured']['cases']), 'A counted case did not execute its target events'
 assert events.actions(ref.parent/'reader.pdf')==original
 (folder/'event-value.json').write_text(json.dumps({'passed':True,'scope':'Isolated event.value write conversion, not original MPMB workflow qualification','reader':str(ref),'public_observer_sha256':hashlib.sha256(public_bytes).hexdigest(),'original_actions_restored':True,'observer_options':options,'hidden_carrier':args.hide_carrier,'carrier_size':args.carrier_size},indent=2)+'\n');print(folder/'event-value.json',flush=True)


if __name__=='__main__':main()
