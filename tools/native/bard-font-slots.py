#!/usr/bin/env python3
"""Native 2024 Font manual bookkeeping with actual generated spell slots.

The original feature describes spending a slot to regain one Inspiration use;
this tests manual checkbox/counter edits, not invented automatic conversion.
Short Rest clears Inspiration but retains ordinary slots; Long Rest clears both.
Reader and desktop input qualification are separate requirements.
"""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields, inspect, script_hashes
import subclass_audit_qualification as qualification

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'target/debug/mpmb-reader');a=p.parse_args();source=a.input.resolve();before=canonical_fields(PdfReader(source));assert before['Character Level']['/V']=='5' and before['Class and Levels']['/V']=='Bard (College of Lore)' and before['Limited Feature Recovery 1']['/V']=='SR/SS 1+';prefix=before['Template.extras.SSfront']['/V'].split(',')[-1];assert prefix
 boxes=[]
 for page in PdfReader(source).pages:
  for ref in page.get('/Annots',[]):
   node=ref.get_object();chain=[node]
   while chain[-1].get('/Parent'):chain.append(chain[-1]['/Parent'].get_object())
   name='.'.join(str(n['/T']) for n in reversed(chain) if n.get('/T'))
   if name.startswith(prefix+'SpellSlots.Checkboxes.lvl1.') and not int(node.get('/F',0))&34:boxes.append(name)
 assert len(boxes)==len(set(boxes))==4,boxes
 folder=ROOT/'output/testing'/('native-bard-font-slots-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';shutil.copy2(a.binary.resolve(),binary);digest=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();report={'passed':False,'reader_qualified':False,'scope':__doc__,'input':str(source),'input_sha256':digest(source),'binary_sha256':digest(binary),'boxes':boxes,'selected_slot':boxes[0],'phases':[],'probe_qualifications':[]};names=['Class and Levels','Character Level','Cha','Limited Feature 1','Limited Feature Max Usages 1','Limited Feature Recovery 1','Limited Feature Used 1',prefix+'SpellSlots.CheckboxesSet.lvl1']+boxes
 spec=importlib.util.spec_from_file_location('slot_widgets',ROOT/'tools/native/verify-bard-slot-widgets.py');widgets=importlib.util.module_from_spec(spec);spec.loader.exec_module(widgets)
 spec=importlib.util.spec_from_file_location('raw_values',ROOT/'tools/native/field-state-comparison.py');raw=importlib.util.module_from_spec(spec);spec.loader.exec_module(raw)
 read='(function(){var r={};'+json.dumps(names)+'.forEach(function(n){r[n]=getField(n).valueAsString});return r})()'
 def capture(steps,captures,label,used,slot):
  steps.extend([{'op':'advance','ms':1000},{'op':'eval','code':read}]);pdf=folder/(label+'.pdf');captures.append((label,len(steps)-1,pdf,used,slot));steps.append({'op':'save','path':str(pdf)});return pdf
 def run(label,pdf,steps,captures):
  scenario=folder/(label+'-scenario.json');evidence=folder/(label+'-probe.json');scenario.write_text(json.dumps({'steps':steps,'dialogs':[]}))
  with (folder/(label+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(pdf),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=480)
  data=json.loads(evidence.read_text());q=qualification.qualify_probe(proc.returncode,data);report['probe_qualifications'].append(dict(q,probe=str(evidence)));assert q['passed'],q
  for name,index,saved,used,slot in captures:
   values=data['stages'][index]['result'];assert set(values)==set(names)
   assert values['Limited Feature Used 1']==used and values['Limited Feature Max Usages 1']=='5' and values[prefix+'SpellSlots.CheckboxesSet.lvl1']=='4'
   expected={n:slot if n==boxes[0] else 'Off' for n in boxes};assert all(values[n]==v for n,v in expected.items()),(name,expected,values)
   canonical=raw.compare(saved,values);visible=inspect(saved,{'Limited Feature Used 1':used,'Limited Feature Max Usages 1':'5'});assert visible['passed'];usage=[w for w in visible['widgets'] if w['name']=='Limited Feature Used 1' and w['visible'] and w['page'] is not None];assert usage and all((w['appearance_text'] or '').strip()==used for w in usage)
   checked=widgets.widgets(saved,expected);assert script_hashes(saved)==script_hashes(source);report['phases'].append({'label':name,'pdf':str(saved),'fields':values,'canonical':canonical,'visible':visible,'slot_widgets':checked,'probe':str(evidence)})
 try:
  steps=[{'op':'advance','ms':5100}];caps=[];capture(steps,caps,'baseline','','Off');steps.append({'op':'user-edit','field':'Limited Feature Used 1','value':'3'});capture(steps,caps,'spent-inspiration','3','Off');steps.extend([{'op':'eval','code':'__host.activate('+json.dumps(boxes[0])+')'},{'op':'user-edit','field':'Limited Feature Used 1','value':'2'}]);capture(steps,caps,'manual-slot-recovery','2','True');steps.append({'op':'eval','code':"__host.command(\"resetLimFeaUsed('short rest')\")"});saved=capture(steps,caps,'short-rest','','True');run('workflow',source,steps,caps)
  steps=[{'op':'advance','ms':5100}];caps=[];capture(steps,caps,'cold-spent-slot','','True');steps.append({'op':'eval','code':"__host.command(\"resetLimFeaUsed('long rest')\")"});capture(steps,caps,'long-rest','','Off');run('cold',saved,steps,caps);assert len(report['phases'])==6 and digest(source)==report['input_sha256'];report['passed']=True
 except Exception as e:report['error']=str(e);raise
 finally:(folder/'slots.json').write_text(json.dumps(report,indent=2));print(folder/'slots.json',flush=True)
if __name__=='__main__':main()
