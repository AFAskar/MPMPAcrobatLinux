#!/usr/bin/env python3
"""Prepare a disclosed startup observer without re-executing imported add-ons.

This creates a diagnostic INPUT, never an oracle output. Every original document
script, canonical field and JavaScript field action must remain unchanged. It is
not a workflow or Reader-interoperability qualification by itself.
"""
import argparse,hashlib,importlib.util,json,sys,time
from pathlib import Path
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject,DictionaryObject,TextStringObject
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import script_hashes,canonical_fields
import fighter_additional_diagnostics as diagnostics
NAME='zz MPMB diagnostic startup observer'
MARKER='// MPMB workflow observer installed'
MODE='startup-script-timer'
CONSOLE_REQUEST='// MPMB workflow console request'
CONSOLE_DONE='// MPMB workflow console complete:'

def field_actions(reader):
    actions={}
    for name,field in canonical_fields(reader).items():
        node=reader.get_object(field['reference'])
        for key,action in node.get('/AA',{}).items():
            action=action.get_object()
            if action.get('/S')!='/JavaScript':
                raise ValueError('Unqualified non-JavaScript field action: '+name+' '+key)
            code=action.get('/JS','')
            if hasattr(code,'get_object'):code=code.get_object()
            data=code.get_data() if hasattr(code,'get_data') else str(code).encode('utf-8')
            actions[name+' '+key]=hashlib.sha256(data).hexdigest()
    return actions

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--observer',type=Path,required=True);args=p.parse_args()
    source=args.input.resolve();observer=args.observer.read_text();source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    spec=importlib.util.spec_from_file_location('profile',ROOT/'tools/native/fighter-styles.py');profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
    setup=diagnostics.install(profile.SETUP,observer)
    setup+=(';tDoc.__workflowConsoleCount=0;'
        'tDoc.__workflowShowConsole=function(){console.show();tDoc.__workflowConsoleCount++;'
        'tDoc.getField("User Script").value='+json.dumps(CONSOLE_DONE)+'+tDoc.__workflowConsoleCount;};'
        'tDoc.__workflowOriginalTick=tDoc.__fighterAdditionalTick;'
        'tDoc.__fighterAdditionalTick=function(){if(tDoc.getField("User Script").valueAsString==='+json.dumps(CONSOLE_REQUEST)+'){'
        'tDoc.getField("User Script").value="// MPMB workflow console pending";'
        'tDoc.__workflowConsoleShow=app.setTimeOut("tDoc.__workflowShowConsole()",1000);}'
        'tDoc.__workflowOriginalTick();};')
    code='tDoc.__workflowObserverInstall=function(){if(!app.calculate||!tDoc.calculate||tDoc.delay){tDoc.__workflowObserverBoot=app.setTimeOut("tDoc.__workflowObserverInstall()",250);return;}'+setup+';Value("User Script",'+json.dumps(MARKER)+');};tDoc.__workflowObserverBoot=app.setTimeOut("tDoc.__workflowObserverInstall()",250);'
    assert code.isascii(),'Use ASCII source escapes for diagnostic transport'
    folder=ROOT/'output/testing'/('workflow-startup-input-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);(folder/'bootstrap.js').write_text(code)
    before_reader=PdfReader(source);before_actions=field_actions(before_reader);writer=PdfWriter(clone_from=source);tree=writer._root_object['/Names']['/JavaScript']
    assert '/Kids' not in tree and NAME not in [str(x) for x in tree['/Names'][::2]],'Requires an uninstrumented direct JavaScript name tree'
    tree['/Names'].extend([TextStringObject(NAME),writer._add_object(DictionaryObject({NameObject('/S'):NameObject('/JavaScript'),NameObject('/JS'):TextStringObject(code)}))]);pdf=folder/'instrumented.pdf';writer.write(pdf)
    original_scripts=script_hashes(source);after_scripts=script_hashes(pdf);assert after_scripts.pop(NAME)==hashlib.sha256(code.encode()).hexdigest() and original_scripts==after_scripts
    after_reader=PdfReader(pdf);before=canonical_fields(before_reader);after=canonical_fields(after_reader);strip=lambda fields:{n:{k:v for k,v in row.items() if k!='reference'} for n,row in fields.items()};assert strip(before)==strip(after);assert before_actions==field_actions(after_reader);assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
    manifest={'passed':True,'scope':__doc__,'mode':MODE,'original':str(source),'original_sha256':source_hash,'input':str(pdf),'input_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'observer':str(args.observer.resolve()),'observer_sha256':hashlib.sha256(observer.encode()).hexdigest(),'added_script':NAME,'bootstrap_sha256':hashlib.sha256(code.encode()).hexdigest(),'diagnostic_helper_sha256':hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest(),'canonical_comparison':'All canonical properties except physical object reference IDs, which cloning can renumber','field_count':len(before),'original_script_count':len(original_scripts),'original_field_action_count':len(before_actions),'field_actions':before_actions,'ready_marker':MARKER,'console_request':CONSOLE_REQUEST,'console_done':CONSOLE_DONE};(folder/'input.json').write_text(json.dumps(manifest,indent=2)+'\n');print(folder/'input.json',flush=True)

if __name__=='__main__':main()
