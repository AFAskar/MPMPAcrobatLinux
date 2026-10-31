#!/usr/bin/env python3
"""Freeze original actions for the isolated event.value setter type diagnostic."""
import argparse,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
spec=importlib.util.spec_from_file_location('events',ROOT/'tools/native/reader-xfdf-events.py');events=importlib.util.module_from_spec(spec);spec.loader.exec_module(events)


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--observer',type=Path,default=ROOT/'tools/native/event-value-write-observer.js');p.add_argument('--expected-cases',type=int,default=68);args=p.parse_args()
 source=next((ROOT/'Testing').glob('*_2024_*.pdf'));original=events.actions(source);folder=ROOT/'output/testing'/('reader-event-value-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
 originals={'player':{kind:original['Player Name'][key] for kind,key in [('Keystroke','K'),('Validate','V'),('Format','F')]},'calc':original['Str Mod']['C']};assert originals['calc']
 from pypdf import PdfReader
 from verify import canonical_fields,field_text
 pdf=PdfReader(source);node=pdf.get_object(canonical_fields(pdf)['Str Mod']['reference']);aa=node.get('/AA',{});aa=aa.get_object() if hasattr(aa,'get_object') else aa
 originals['calcEvents']={kind:field_text(aa['/'+key].get_object().get('/JS','')) if '/'+key in aa else '' for kind,key in [('Keystroke','K'),('Validate','V'),('Format','F')]}
 public=args.observer;observer=folder/'observer.js';observer.write_text('tDoc.__eventWriteOriginal='+json.dumps(originals,ensure_ascii=True)+';\n'+public.read_text())
 with (folder/'reader.log').open('w') as log:run=subprocess.run([sys.executable,str(ROOT/'tools/native/reader-script-observation.py'),'--input',str(source),'--observer',str(observer),'--readiness',str(args.readiness)],stdout=log,stderr=log,timeout=420)
 paths=[line.strip() for line in (folder/'reader.log').read_text().splitlines() if line.strip().endswith('/observation.json')];assert paths
 ref=Path(paths[-1]);report=json.loads(ref.read_text());assert run.returncode==0 and report['passed'],report.get('error');assert not report['captured']['errors'] and len(report['captured']['cases'])==args.expected_cases
 assert events.actions(ref.parent/'reader.pdf')==original
 (folder/'event-value.json').write_text(json.dumps({'passed':True,'scope':'Isolated event.value write conversion, not original MPMB workflow qualification','reader':str(ref),'public_observer_sha256':hashlib.sha256(public.read_bytes()).hexdigest(),'original_actions_restored':True},indent=2)+'\n');print(folder/'event-value.json',flush=True)


if __name__=='__main__':main()
