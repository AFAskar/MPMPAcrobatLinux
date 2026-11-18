"""Strict captured JSON comparison: ignore object order, preserve primitive types."""
import argparse
import hashlib
import json
from pathlib import Path


def encoded_state(state, ignore_generated_prefixes=False):
    if ignore_generated_prefixes:
        assert isinstance(state.get('rawPrefixes'), list), 'Missing retained generated addresses'
        state = {key:value for key,value in state.items() if key != 'rawPrefixes'}
    return json.dumps(state, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def compare(expected, actual, ignore_generated_prefixes=False):
    assert expected['passed'] is True and actual['passed'] is True, 'Require complete successful reports'
    left, right = expected['phases'], actual['phases']
    labels = [p['label'] for p in left]
    assert labels and len(set(labels)) == len(labels)
    assert labels == [p['label'] for p in right], 'Different completed case sequences'
    pairs=[]
    for a,b in zip(left,right):
        x=encoded_state(a['state'],ignore_generated_prefixes)
        y=encoded_state(b['state'],ignore_generated_prefixes)
        assert x == y, ('Captured JSON mismatch',a['label'])
        pairs.append({'label':a['label'],'sha256':hashlib.sha256(x.encode()).hexdigest(),
                      'expected_raw_prefixes':a['state'].get('rawPrefixes'),
                      'actual_raw_prefixes':b['state'].get('rawPrefixes')})
    return {'passed':True,'scope':'All captured JSON properties and array order retained; object member order ignored. Boolean/number/string/null distinctions retained. '+
            ('Only rawPrefixes addresses excluded; logical page/suffix maps remain exact and raw addresses retained.' if ignore_generated_prefixes else 'No captured properties excluded.'),'pairs':pairs}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected',type=Path,required=True)
    parser.add_argument('--actual',type=Path,required=True)
    parser.add_argument('--ignore-generated-prefixes',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=compare(json.loads(args.expected.read_text()),json.loads(args.actual.read_text()),args.ignore_generated_prefixes)
    result.update(expected=str(args.expected),actual=str(args.actual),
                  expected_sha256=hashlib.sha256(args.expected.read_bytes()).hexdigest(),
                  actual_sha256=hashlib.sha256(args.actual.read_bytes()).hexdigest())
    with args.output.open('x') as stream:json.dump(result,stream,indent=2)


if __name__=='__main__':
    main()
