#!/usr/bin/env python3
"""Read-only canonical field comparison with MPMB serialized-state interpretation.

Source expressions are evaluated in a bounded Node context. Function bodies
must match as source; their behavior remains unqualified. This compares stored
state, not widget appearances or complete MPMB compatibility.
"""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import canonical_fields

COMPARE = r'''
const vm=require('node:vm'),fs=require('node:fs'),crypto=require('node:crypto');
const digest=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
function canonical(x,seen=new Set(),depth=0){
 if(depth>64||seen.size>200000)throw Error('Serialized object exceeds comparison limits');
 const type=typeof x;
 if(type==='symbol'||type==='bigint')throw Error('Unsupported serialized primitive: '+type);
 if(type==='undefined')return {kind:'undefined'};
 if(type==='function')return {kind:'function',value:Function.prototype.toString.call(x)};
 if(x===null)return {kind:'null'};
 if(type!=='object')return {kind:type,value:type==='number'?(Object.is(x,-0)?'-0':String(x)):x};
 if(seen.has(x))throw Error('Cyclic serialized object');
 seen.add(x);
 try{
  const tag=Object.prototype.toString.call(x);
  if(tag==='[object RegExp]')return {kind:'regexp',value:x.source,flags:x.flags};
  if(tag==='[object Date]')return {kind:'date',value:String(Date.prototype.getTime.call(x))};
  if(Array.isArray(x))return {kind:'array',entries:Array.from({length:x.length},(_,i)=>Object.hasOwn(x,i)?canonical(x[i],seen,depth+1):{kind:'hole'})};
  if(tag!=='[object Object]')throw Error('Unsupported serialized object type: '+tag);
  const entries={};
  for(const k of Object.keys(x).sort()){
   const prop=Object.getOwnPropertyDescriptor(x,k);
   if(prop.get||prop.set)throw Error('Accessor requires separate behavioral comparison');
   entries[k]=canonical(prop.value,seen,depth+1);
  }
  return {kind:'object',entries};
 }finally{seen.delete(x)}
}
function compare(a,b,path,out){
 if(JSON.stringify(a)===JSON.stringify(b))return;
 if(a.kind===b.kind&&(a.kind==='object'||a.kind==='array')){
  for(const k of new Set([...Object.keys(a.entries),...Object.keys(b.entries)]))
   compare(a.entries[k]||{kind:'absent'},b.entries[k]||{kind:'absent'},path+'['+JSON.stringify(k)+']',out);
  return;
 }
 out.push({path,kinds:[a.kind,b.kind],sha256:[digest(a),digest(b)]});
}
function parse(name,source){
 const parts=name==='CurrentSpells.Stringified'?source.split('##########'):[source];
 if(name==='CurrentSpells.Stringified'&&parts.length!==2)throw Error('Expected original CurrentSpells/CurrentCasters separator');
 return {kind:'array',entries:parts.map(s=>canonical(vm.runInNewContext('('+s+')',Object.create(null),{timeout:1000})))};
}
const pairs=JSON.parse(fs.readFileSync(0,'utf8')),out={};
for(const [name,values] of Object.entries(pairs)){
 try{const [a,b]=values.map(s=>parse(name,s)),differences=[];compare(a,b,'$',differences);out[name]={equal:!differences.length,differences};}
 catch(e){out[name]={equal:false,error:String(e)}}
}
process.stdout.write(JSON.stringify(out));
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native', type=Path); parser.add_argument('reader', type=Path); parser.add_argument('report', type=Path)
    args = parser.parse_args()
    left, right = [canonical_fields(PdfReader(p)) for p in [args.native, args.reader]]
    text = lambda f: str(f.get('/V', '')).replace('\r\n', '\n').replace('\r', '\n')
    changed = [n for n in sorted(left.keys() | right.keys()) if n not in left or n not in right or text(left[n]) != text(right[n])]
    serialized = {n: [text(left[n]), text(right[n])] for n in changed if n in left and n in right and n.endswith('.Stringified')}
    result = subprocess.run(['node', '-e', COMPARE], input=json.dumps(serialized), text=True, capture_output=True, timeout=60, check=True)
    state = json.loads(result.stdout)
    other = [n for n in changed if n not in serialized]
    report = {'passed': not other and all(v['equal'] for v in state.values()), 'scope': __doc__,
              'inputs': [{'path': str(p.resolve()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in [args.native, args.reader]],
              'field_counts': [len(left), len(right)], 'text_difference_count': len(changed),
              'nonserialized_value_differences': other, 'serialized_comparison': state,
              'original_spells_parser': 'Split CurrentSpells.Stringified at ##########, then evaluate both expressions like GetStringifieds.'}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(args.report, 'PASS' if report['passed'] else 'FAIL', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
