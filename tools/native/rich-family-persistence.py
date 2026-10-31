#!/usr/bin/env python3
"""Edited mixed-family persistence with exact font-property and AP-face checks.

These action-cleared diagnostics compare font properties, not full rich APIs:
underline enum/false-property gaps are retained and reported separately. Edits
change existing loaded spans; no expected font styles are injected on reopen.
"""
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import script_hashes
spec=importlib.util.spec_from_file_location('matrix',ROOT/'tools/native/rich-decoration-matrix.py');matrix=importlib.util.module_from_spec(spec);spec.loader.exec_module(matrix)
spec=importlib.util.spec_from_file_location('verify_family',ROOT/'tools/native/verify-family-persistence.py');verify_family=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify_family)
PROPERTIES=['text','fontFamily','fontWeight','fontStyle','fontStretch','textSize','textColor','alignment','linespacing']
READ="({value:getField('Extra.Notes').valueAsString,spans:getField('Extra.Notes').richValue})"

def font_state(field):return {'value':field['value'],'spans':[{key:span.get(key,{'missing':True}) for key in PROPERTIES} for span in field['spans']]}
def changed(field,suffix):
 state=json.loads(json.dumps(field));state['value']+=suffix;state['spans'][-1]['text']+=suffix;return state

def observer(cases,mode,suffix):
 edit="var spans=f.richValue;spans[spans.length-1].text+="+json.dumps(suffix)+";f.richValue=spans;" if mode=='append' else "var spans=f.richValue,last=spans[spans.length-1];if(last.text.slice(-suffix.length)!==suffix)throw Error('Edit suffix missing');last.text=last.text.slice(0,-suffix.length);f.richValue=spans;" if mode=='restore' else ''
 return "var iFileName='Mixed font loaded-span edit.js';Value('User Script','');(function(d){var suffix="+json.dumps(suffix)+",f=d.getField('Extra.Notes'),r={cases:"+json.dumps(cases)+",errors:[],before:"+READ+",field:null,sentinel:'\\u00a0\\u2028\\ud83d\\ude00'};try{['Keystroke','Validate','Format','Calculate'].forEach(function(k){f.setAction(k,'')});"+edit+"r.field="+READ+"}catch(e){r.errors.push({name:e.name,message:String(e)})}Value('PC Name',JSON.stringify(r).replace(/[\\u007f-\\uffff]/g,function(ch){return '\\\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native-comparison',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);a=p.parse_args();initial=json.loads(a.native_comparison.read_text());assert initial['strict_native_probe_passed'];source=a.native_comparison.parent/'native.pdf';cases=initial['captured']['cases'];expected=font_state(initial['captured']['field']);expected_appearances=matrix.measure(source,initial['captured'])
 folder=ROOT/'output/testing'/('rich-family-persistence-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary);source_hash=hashlib.sha256(source.read_bytes()).hexdigest();scripts=script_hashes(source)
 report={'passed':False,'scope':__doc__,'source':str(source),'source_sha256':source_hash,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'properties_compared':PROPERTIES,'full_api_equality_claimed':False,'initial_full_api_comparison_passed':initial['passed'],'native':[]}
 def native(label,input_pdf,before,after,mode,suffix):
  output=folder/(label+'.pdf');code=observer(cases,mode,suffix);scenario={'dialogs':[{'result':'ok'}]*10,'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':READ},{'op':'eval','code':"Value('User Script',"+json.dumps(code)+")"},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'eval','code':"JSON.parse(getField('PC Name').valueAsString)"},{'op':'eval','code':"(function(){var s=JSON.parse(__host.snapshot())['Extra.Notes'];return {appearanceDirty:s.appearanceDirty,richValueChanged:s.richValueChanged}})()"},{'op':'save','path':str(output)}]};plan=folder/(label+'.json');plan.write_text(json.dumps(scenario));empty=folder/'no-executables';empty.mkdir(exist_ok=True)
  with (folder/(label+'.log')).open('w') as log:run=subprocess.run([str(binary),str(input_pdf),'--probe',str(plan),str(folder/(label+'-probe.json'))],stdout=log,stderr=log,env={**os.environ,'PATH':str(empty)},timeout=300)
  data=json.loads((folder/(label+'-probe.json')).read_text());assert run.returncode==0 and data['passed'] and not data['diagnostics']['errors'],data.get('error') or data['diagnostics']['errors'];loaded=data['stages'][1]['result'];capture=data['stages'][-3]['result'];assert not capture['errors'];assert font_state(loaded)==before,'Loaded font state changed';assert font_state(capture['before'])==before,'Original RunUserScript entry altered fonts before edit';assert font_state(capture['field'])==after,'Edited font properties changed'
  trigger=data['stages'][-2]['result'];value_changed=capture['field']['value']!=loaded['value']
  if mode!='read':assert trigger['appearanceDirty'] or trigger['richValueChanged'] or value_changed,'Edit did not invalidate appearance'
  from pypdf import PdfReader
  from verify import canonical_fields
  saved=canonical_fields(PdfReader(output))['PC Name']['/V'];assert saved.isascii() and json.loads(saved)==capture;assert [ord(c) for c in capture['sentinel']]==[160,8232,128512]
  assert script_hashes(output)==scripts;measured=matrix.measure(output,capture);assert verify_family.same(expected_appearances,measured),'Actual AP face/size/vertical geometry changed';checked=verify_family.inspect(output,{'Extra.Notes':capture['field']['value']});assert checked['passed'] and any(w['visible'] and w['appearance_matches'] for w in checked['widgets']);report['native'].append({'label':label,'path':str(output),'loaded':loaded,'captured':capture,'appearances':measured,'rebuild_triggers':{**trigger,'valueChanged':value_changed},'full_span_getter_equal':loaded==initial['captured']['field']});return output,capture
 try:
  suffix=' [native edit]';first,_=native('native-changed',source,expected,changed(expected,suffix),'append',suffix);restored,_=native('native-restored',first,changed(expected,suffix),expected,'restore',suffix)
  read_suffix=' [Reader edit]';obs=folder/'reader-observer.js';obs.write_text(observer(cases,'append',read_suffix))
  with (folder/'reader.log').open('w') as log:run=subprocess.run([sys.executable,str(ROOT/'tools/native/reader-script-observation.py'),'--input',str(restored),'--observer',str(obs),'--readiness',str(a.readiness)],stdout=log,stderr=log,timeout=420)
  paths=[s.strip() for s in (folder/'reader.log').read_text().splitlines() if s.strip().endswith('/observation.json')];assert paths;ref=Path(paths[-1]);r=json.loads(ref.read_text());report['reader']=str(ref);assert run.returncode==0 and r['passed'],r.get('error');c=r['captured'];assert not c['errors'];assert font_state(c['before'])==expected;assert font_state(c['field'])==changed(expected,read_suffix);reader_pdf=ref.parent/'reader.pdf';report['reader_appearances']=matrix.measure(reader_pdf,c);assert verify_family.same(expected_appearances,report['reader_appearances']),'Reader AP face/size/vertical geometry changed';assert script_hashes(reader_pdf)==scripts
  final,_=native('reader-native-restored',reader_pdf,changed(expected,read_suffix),expected,'restore',read_suffix);native('native-final-reopen',final,expected,expected,'read','');assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash;report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'persistence.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'persistence.json',flush=True)

if __name__=='__main__':main()
