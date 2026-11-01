#!/usr/bin/env python3
"""Edited mixed-family persistence with exact font-property and AP-face checks.

These action-cleared diagnostics compare font properties by default. Optional
--full-spans qualifies complete decoded span properties, including decoration
reassignment, and actual stroke segment counts. Horizontal/pixel equality is not
claimed. Edits
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
FULL_SPANS=False
API_ONLY=False
READ="({value:getField('Extra.Notes').valueAsString,spans:getField('Extra.Notes').richValue})"

def font_state(field):return json.loads(json.dumps(field)) if FULL_SPANS else {'value':field['value'],'spans':[{key:span.get(key,{'missing':True}) for key in PROPERTIES} for span in field['spans']]}
def reassigned(field):
 state=json.loads(json.dumps(field))
 if FULL_SPANS:
  # Measured direct span assignment: an empty enum/false strike is ignored.
  # Explicit 'none' produces these getter values, but copying them back clears
  # their explicit properties. Assert the prediction in native AND real Reader.
  for span in state['spans']:
   if span.get('underline')=='':span.pop('underline')
   if span.get('strikethrough') is False:span.pop('strikethrough')
 return state
def changed(field,suffix):
 state=reassigned(field);state['value']+=suffix;state['spans'][-1]['text']+=suffix;return state

def observer(cases,mode,suffix):
 edit="var spans=f.richValue;spans[spans.length-1].text+="+json.dumps(suffix)+";f.richValue=spans;" if mode=='append' else "var spans=f.richValue,last=spans[spans.length-1];if(last.text.slice(-suffix.length)!==suffix)throw Error('Edit suffix missing');last.text=last.text.slice(0,-suffix.length);f.richValue=spans;" if mode=='restore' else ''
 return "var iFileName='Mixed font loaded-span edit.js';Value('User Script','');(function(d){var suffix="+json.dumps(suffix)+",f=d.getField('Extra.Notes'),r={cases:"+json.dumps(cases)+",errors:[],before:"+READ+",field:null,sentinel:'\\u00a0\\u2028\\ud83d\\ude00'};try{['Keystroke','Validate','Format','Calculate'].forEach(function(k){f.setAction(k,'')});"+edit+"r.field="+READ+"}catch(e){r.errors.push({name:e.name,message:String(e)})}Value('PC Name',JSON.stringify(r).replace(/[\\u007f-\\uffff]/g,function(ch){return '\\\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"

def main():
 global FULL_SPANS,API_ONLY
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--api-only',action='store_true',help='Require complete canonical/widget values and API spans; retain/report appearance-text failures without qualifying them');p.add_argument('--full-spans',action='store_true',help='Exact complete decoded span/value equality, including decoration flags; explicit empty/false reassignment is tested');p.add_argument('--native-comparison',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);a=p.parse_args();FULL_SPANS=a.full_spans;API_ONLY=a.api_only;initial=json.loads(a.native_comparison.read_text());assert initial['strict_native_probe_passed'];assert not FULL_SPANS or initial['passed'],'Complete span persistence requires a passing source API comparison';source=a.native_comparison.parent/'native.pdf';cases=initial['captured']['cases'];expected=font_state(initial['captured']['field']);baseline=reassigned(expected);expected_appearances=matrix.measure(source,initial['captured'])
 folder=ROOT/'output/testing'/('rich-family-persistence-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary);source_hash=hashlib.sha256(source.read_bytes()).hexdigest();scripts=script_hashes(source)
 report={'passed':False,'scope':__doc__,'source':str(source),'source_sha256':source_hash,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'properties_compared':'all decoded span properties and value; object member order ignored, array order exact' if FULL_SPANS else PROPERTIES,'full_api_equality_claimed':FULL_SPANS,'appearance_text_required':not API_ONLY,'reassignment_expected':baseline,'initial_full_api_comparison_passed':initial['passed'],'native':[]}
 def native(label,input_pdf,before,after,mode,suffix):
  output=folder/(label+'.pdf');code=observer(cases,mode,suffix);scenario={'dialogs':[{'result':'ok'}]*10,'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':READ},{'op':'eval','code':"Value('User Script',"+json.dumps(code)+")"},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'eval','code':"JSON.parse(getField('PC Name').valueAsString)"},{'op':'eval','code':"(function(){var s=JSON.parse(__host.snapshot())['Extra.Notes'];return {appearanceDirty:s.appearanceDirty,richValueChanged:s.richValueChanged}})()"},{'op':'save','path':str(output)}]};plan=folder/(label+'.json');plan.write_text(json.dumps(scenario));empty=folder/'no-executables';empty.mkdir(exist_ok=True)
  with (folder/(label+'.log')).open('w') as log:run=subprocess.run([str(binary),str(input_pdf),'--probe',str(plan),str(folder/(label+'-probe.json'))],stdout=log,stderr=log,env={**os.environ,'PATH':str(empty)},timeout=300)
  data=json.loads((folder/(label+'-probe.json')).read_text());assert run.returncode==0 and data['passed'] and not data['diagnostics']['errors'],data.get('error') or data['diagnostics']['errors'];loaded=data['stages'][1]['result'];capture=data['stages'][-3]['result'];assert not capture['errors'];assert font_state(loaded)==before,'Loaded font state changed';assert font_state(capture['before'])==before,'Original RunUserScript entry altered fonts before edit';assert font_state(capture['field'])==after,'Edited font properties changed'
  trigger=data['stages'][-2]['result'];value_changed=capture['field']['value']!=loaded['value']
  if mode!='read':assert trigger['appearanceDirty'] or trigger['richValueChanged'] or value_changed,'Edit did not invalidate appearance'
  from pypdf import PdfReader
  from verify import canonical_fields
  saved=canonical_fields(PdfReader(output))['PC Name']['/V'];assert saved.isascii() and json.loads(saved)==capture;assert [ord(c) for c in capture['sentinel']]==[160,8232,128512]
  assert script_hashes(output)==scripts;measured=matrix.measure(output,capture);assert verify_family.same(expected_appearances,measured,topology=FULL_SPANS),'Actual AP face/size/vertical geometry changed';checked=verify_family.inspect(output,{'Extra.Notes':capture['field']['value']});assert checked['actual']=={'Extra.Notes':capture['field']['value']} and checked['widgets'] and all(w['matches'] for w in checked['widgets']);
  if not API_ONLY:assert checked['passed'] and any(w['visible'] and w['appearance_matches'] for w in checked['widgets'])
  report['native'].append({'label':label,'path':str(output),'loaded':loaded,'captured':capture,'appearances':measured,'raw_appearance_text_inspection_passed':checked['passed'],'rebuild_triggers':{**trigger,'valueChanged':value_changed},'full_span_getter_equal':loaded==initial['captured']['field']});return output,capture
 try:
  suffix=' [native edit]';first,_=native('native-changed',source,expected,changed(expected,suffix),'append',suffix);restored,_=native('native-restored',first,changed(expected,suffix),baseline,'restore',suffix)
  read_suffix=' [Reader edit]';obs=folder/'reader-observer.js';obs.write_text(observer(cases,'append',read_suffix))
  with (folder/'reader.log').open('w') as log:run=subprocess.run([sys.executable,str(ROOT/'tools/native/reader-script-observation.py'),'--input',str(restored),'--observer',str(obs),'--readiness',str(a.readiness)],stdout=log,stderr=log,timeout=420)
  paths=[s.strip() for s in (folder/'reader.log').read_text().splitlines() if s.strip().endswith('/observation.json')];assert paths;ref=Path(paths[-1]);r=json.loads(ref.read_text());report['reader']=str(ref);assert run.returncode==0 and r['passed'],r.get('error');c=r['captured'];assert not c['errors'];assert font_state(c['before'])==baseline;assert font_state(c['field'])==changed(baseline,read_suffix);reader_pdf=ref.parent/'reader.pdf';report['reader_appearances']=matrix.measure(reader_pdf,c);assert verify_family.same(expected_appearances,report['reader_appearances'],topology=FULL_SPANS),'Reader AP face/size/vertical geometry changed';assert script_hashes(reader_pdf)==scripts
  final,_=native('reader-native-restored',reader_pdf,changed(baseline,read_suffix),baseline,'restore',read_suffix);native('native-final-reopen',final,baseline,baseline,'read','');assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash;report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'persistence.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'persistence.json',flush=True)

if __name__=='__main__':main()
