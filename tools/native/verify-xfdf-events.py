#!/usr/bin/env python3
"""Compare native import against a qualified Reader original-action event trace.

The original observer is reused. Only the native picker is replaced by an
explicit path to the same hashed input; no expected values are assigned.
"""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import script_hashes, inspect
spec=importlib.util.spec_from_file_location('events',ROOT/'tools/native/reader-xfdf-events.py');events=importlib.util.module_from_spec(spec);spec.loader.exec_module(events)


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'target/debug/mpmb-reader');p.add_argument('--reader-text-profile',action='store_true',help='Use the original text-options dialog to disable forced multiline formatting, matching this Windows reference');p.add_argument('--reopen',action='store_true',help='Fresh native save/reopen twice and compare all captured field getters');args=p.parse_args()
 reference=json.loads(args.reader.read_text());assert reference['passed'] and reference['original_action_sha256']
 if args.reader_text_profile and reference.get('fixture')=='ashnar':p.error('The qualified legacy text-options dialog has no ckFF control; use original options')
 source=Path(reference['source']);observer=(args.reader.parent/'observer.js').read_text();xml=args.reader.parent/'input.xfdf'
 assert hashlib.sha256(source.read_bytes()).hexdigest()==reference['source_sha256'];assert hashlib.sha256(observer.encode()).hexdigest()==reference['observer_sha256'];assert hashlib.sha256(xml.read_bytes()).hexdigest()==reference['input_sha256']
 folder=ROOT/'output/testing'/('native-xfdf-events-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(args.binary,binary)
 report={'passed':False,'scope':__doc__,'reader':str(args.reader.resolve()),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'reader_text_profile':args.reader_text_profile}
 summary="(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
 code="var controlledImport=tDoc.importAnXFDF;tDoc.importAnXFDF=function(){return controlledImport.call(tDoc,"+json.dumps(str(xml.resolve()))+")};Value('User Script',"+json.dumps(observer)+")"
 setup=[{'op':'advance','ms':4100}];dialogs=[] if reference.get('fixture')=='ashnar' else [{'title':'SOURCE SELECTION DIALOG','result':'ok'}]
 if args.reader_text_profile:
  dialogs.append({'title':'Set the Font and the Font Size','result':'ok','values':{'ckFF':False}});setup+=[{'op':'eval','code':"__host.command('SetTextOptions_Button()')"},{'op':'eval','code':"if(CurrentVars.fixRichTextFormatting!==false)throw Error('Original text option was not disabled');({forceFixed:CurrentVars.fixRichTextFormatting})"}]
 alerts=([{'title':"Before you get started with MPMB's Character Record Sheet",'button':1},{'title':'Is everything ready for importing?','button':4},{'title':'Notes on Importing','button':1}] if reference.get('original_wrapper') else [1]*20)
 scenario={'dialogs':dialogs,'alerts':alerts,'steps':setup+[{'op':'eval','code':code},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'eval','code':summary},{'op':'save','path':str(folder/'native.pdf')}]};(folder/'scenario.json').write_text(json.dumps(scenario))
 try:
  with (folder/'probe.log').open('w') as log:run=subprocess.run([str(binary),str(source),'--probe',str(folder/'scenario.json'),str(folder/'probe.json')],stdout=log,stderr=log,timeout=300,env={**os.environ,'MPMB_DIALOG_TRACE_DIR':str(folder/'dialogs')})
  data=json.loads((folder/'probe.json').read_text());report['strict_probe_passed']=data['passed'];assert run.returncode==0 and data['passed'],data.get('error')
  captured=events.interop.xfdf.style.saved_capture(folder/'native.pdf',data['stages'][-2]['result'],source);report['captured']=captured
  report['exact_observation_equal']=captured==reference['captured'];assert report['exact_observation_equal'],'Import event/state trace differs'
  assert events.actions(folder/'native.pdf',reference.get('empty_controls',False))==events.actions(source,reference.get('empty_controls',False));assert script_hashes(folder/'native.pdf')==script_hashes(source)
  if args.reopen:
   report['reopens']=[];current=folder/'native.pdf'
   fields=reference['captured']['fields'];expected={item['field']:item['value'] for item in fields}
   field_loop="['Hair colour','Attack.1.Weapon Selection'].forEach" if reference.get('empty_controls') else "['Player Name','Notes.Left'].forEach"
   body=observer[observer.index(field_loop):observer.index('}catch(e){r.errors.push')]
   read_observer="var iFileName='Read XFDF imported state.js';Value('User Script','');(function(d){var r={fields:[],errors:[],sentinel:'\\u00a0\\u2028\\ud83d\\ude00'};"+body+";Value('PC Name',JSON.stringify(r).replace(/[\\u007f-\\uffff]/g,function(ch){return '\\\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"
   (folder/'reopen-observer.js').write_text(read_observer)
   for index in range(2):
    output=folder/('reopen-'+str(index)+'.pdf');plan={'dialogs':([] if reference.get('fixture')=='ashnar' else [{'title':'SOURCE SELECTION DIALOG','result':'ok'}]),'alerts':[1]*20,'steps':[{'op':'advance','ms':4100},{'op':'assert','values':expected},{'op':'eval','code':"Value('User Script',"+json.dumps(read_observer)+")"},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'eval','code':summary},{'op':'save','path':str(output)}]};plan_path=folder/('reopen-'+str(index)+'.json');plan_path.write_text(json.dumps(plan));probe=folder/('reopen-'+str(index)+'-probe.json')
    with (folder/('reopen-'+str(index)+'.log')).open('w') as log:result=subprocess.run([str(binary),str(current),'--probe',str(plan_path),str(probe)],stdout=log,stderr=log,timeout=300)
    data=json.loads(probe.read_text());assert result.returncode==0 and data['passed'],data.get('error')
    state=events.interop.xfdf.style.saved_capture(output,data['stages'][-2]['result'],source);assert state['fields']==fields,(state['fields'],fields)
    independent=inspect(output,expected);assert independent['passed'];assert script_hashes(output)==script_hashes(source)
    report['reopens'].append({'output':str(output),'full_getters_equal':True,'independent':independent});current=output
  report['passed']=True
 except Exception as error:report['error']=str(error);raise
 finally:(folder/'events.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'events.json',flush=True)


if __name__=='__main__':main()
