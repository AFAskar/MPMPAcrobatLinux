#!/usr/bin/env python3
"""Load source rich metadata and preserve /DS, /RV and original scripts in projections.

Optional Reader comparison covers initial Ashnar Class Features metadata only.
Live rich field APIs, events, edits and rich persistence remain incomplete.
"""
import argparse,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields,field_text,script_hashes


def stored_metadata(path):
    reader=PdfReader(path);out={}
    for name,field in canonical_fields(reader).items():
        node=reader.get_object(field['reference'])
        values={key:hashlib.sha256(field_text(node[key]).encode()).hexdigest() for key in ['/DS','/RV'] if key in node}
        if values:out[name]=values
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reader-trace',type=Path);args=parser.parse_args()
    reference=None
    if args.reader_trace:
        trace=json.loads(args.reader_trace.read_text());assert trace['execution_completed'] and trace['fixture']=='ashnar' and trace['field']=='Class Features' and trace['reader_summary']
        qualification=json.loads(Path(trace['readiness']).read_text());assert qualification['passed'] and len(qualification['cases'])==24
        reference=next(r for r in trace['reader'] if r['name']=='initial rich data')
    folder=ROOT/'output/testing'/('rich-metadata-'+str(time.time_ns()));folder.mkdir();binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
    report={'passed':False,'scope':__doc__,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'reader_trace':str(args.reader_trace),'reader_trace_sha256':hashlib.sha256(args.reader_trace.read_bytes()).hexdigest() if args.reader_trace else None,'fixtures':[]};print(folder,flush=True)
    try:
        for label,pattern in [('2014','*_2014_*.pdf'),('2024','*_2024_*.pdf'),('ashnar','Ashnar*.pdf')]:
            source=next((ROOT/'Testing').glob(pattern));original_hash=hashlib.sha256(source.read_bytes()).hexdigest();output=folder/(label+'.pdf')
            spec={'dialogs':[{'result':'ok'}]*30,'alerts':[1]*30,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':"({classFeatures:__host.data.fields['Class Features'].rich_metadata,richFields:__host.names.filter(n=>__host.data.fields[n]&&__host.data.fields[n].rich_metadata.spans.length).length})"},{'op':'save','path':str(output)}]}
            scenario,evidence=folder/(label+'-scenario.json'),folder/(label+'-report.json');scenario.write_text(json.dumps(spec))
            with (folder/(label+'.log')).open('w') as log:r=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=240)
            data=json.loads(evidence.read_text());assert r.returncode==0 and data['passed'],data.get('error');metadata=data['stages'][-2]['result']
            case={'fixture':label,'passed':False,'probe':str(evidence),'output':str(output),'rich_fields':metadata['richFields'],'class_feature_spans':len(metadata['classFeatures']['spans'])};report['fixtures'].append(case)
            assert stored_metadata(source)==stored_metadata(output),'Source /DS or /RV changed in projection'
            assert script_hashes(source)==script_hashes(output),'Original scripts changed'
            assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash,'Original fixture changed'
            case['source_metadata_and_scripts_preserved']=True
            if label=='ashnar' and reference:
                case['reader_default_equal']=metadata['classFeatures']['defaultStyle']==reference['defaultStyle'];case['reader_spans_equal']=metadata['classFeatures']['spans']==reference['richValue']
                assert case['reader_default_equal'] and case['reader_spans_equal'],case
            case['passed']=True;(folder/'metadata.json').write_text(json.dumps(report,indent=2)+'\n');print(label,'rich source metadata/projection PASS',flush=True)
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:(folder/'metadata.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'metadata.json',flush=True)


if __name__=='__main__':main()
