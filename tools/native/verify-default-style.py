#!/usr/bin/env python3
"""Read-only comparison of seven measured defaultStyle runtime cases.

Compares field/default-style state and event behavior except event.richValue.
Does not qualify rich spans, rich event payloads, appearances or persistence.
"""
import argparse,hashlib,json
from pathlib import Path
CASES=['defaultStyle getter copy','textSize defaultStyle coupling','textFont defaultStyle coupling','textColor defaultStyle coupling','alignment defaultStyle coupling','defaultStyle assignment','restore field style']
KEYS=['defaultStyle','fieldStyle','value','valueType','richText','multiline','beforeCalculate']


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('native',type=Path);parser.add_argument('reader',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    native,reader=[json.loads(p.read_text()) for p in [args.native,args.reader]]
    assert native['execution_completed'] and reader['execution_completed'] and reader['reader_summary']
    assert native['fixture']==reader['fixture'] and native['field']==reader['field'] and native['style_data'] and reader['style_data']
    qualification=json.loads(Path(reader['readiness']).read_text());assert qualification['passed'] and len(qualification['cases'])==24
    cases=[]
    for name in CASES:
        left=[r for r in native['native'] if r['name']==name];right=[r for r in reader['reader'] if r['name']==name]
        if len(left)!=1 or len(right)!=1:
            cases.append({'name':name,'passed':False,'error':'Missing/ambiguous measured case'});continue
        def project(row):
            if 'error' in row:return {'error':row['error']}
            out={k:row.get(k,{'missing':True}) for k in KEYS}
            out['events']=[{k:v for k,v in e.items() if k!='richValue'} for e in row.get('events',[])]
            return out
        a,b=project(left[0]),project(right[0]);differences={k:{'native':a.get(k),'reader':b.get(k)} for k in a.keys()|b.keys() if a.get(k)!=b.get(k)}
        cases.append({'name':name,'passed':not differences and 'error' not in a and 'error' not in b,'differences':differences})
    report={'passed':all(c['passed'] for c in cases),'scope':__doc__,'inputs':[{'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [args.native,args.reader]],'cases':cases}
    with args.output.open('x') as file:json.dump(report,file,indent=2);file.write('\n')
    print(args.output,'PASS' if report['passed'] else 'FAIL',flush=True);return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
