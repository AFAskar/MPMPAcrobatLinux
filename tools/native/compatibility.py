#!/usr/bin/env python3
"""Count API call sites without emitting paid source or character values."""
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FEATURES={
 'app.execDialog':('partial','Original lifecycle and handlers with native controls; layout/control coverage incomplete.'),
 'app.popUpMenuEx':('partial','Original hierarchical popup commands and marked/enabled items in a native modal; focused runtime test passes.'),
 'app.setTimeOut':('partial','Chronological cancellable queue in document global; UI ticks or explicit probe advance.'),
 'getTemplate(':('partial','Named template ownership, shared and renamed fields, structural journal and saved page tree; generated workflows qualified.'),
 '.spawn(':('partial','Renamed and shared-value page spawning, deletion and calculation-order projection; overlay explicitly unsupported.'),
 'toSource(':('partial','Objects, arrays, functions, RegExp, Error; cyclic structures reject.'),
 'saveAs(':('unsupported','Native save-new projection available; document API not implemented.'),
 'util.readFileIntoStream':('partial','Local UTF-8 files and native file picker; URLs and binary streams unsupported.'),
}
PARTIAL={'app':{'execDialog','alert','setTimeOut','clearTimeOut','addMenuItem','addSubMenu','removeMenuItem','removeSubMenu','addToolButton','removeToolButton','popUpMenu','popUpMenuEx','response'},'util':{'printf','printd','scand','readFileIntoStream','stringFromStream'},'tDoc':{'getField','getNthFieldName','calculateNow','resetForm','getTemplate','deletePages','removeField'},'dialog':{'load','store','enable','visible','end','setFocus','setForeColorRed','focus','insertEntryInList','removeAllEntriesFromList'}}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--acceptance');p.add_argument('--acrobat');p.add_argument('--desktop',action='append',default=[]);p.add_argument('--imports');p.add_argument('--ashnar');p.add_argument('--generated');p.add_argument('--extended');p.add_argument('--generated-acrobat');p.add_argument('--lifecycle');p.add_argument('--lifecycle-acrobat');p.add_argument('--comparisons');p.add_argument('--native-regression');p.add_argument('--classes');p.add_argument('--scope-audit');p.add_argument('--reference-qualification');p.add_argument('--validation');p.add_argument('--ashnar-comparison');args=p.parse_args()
 base=json.loads((ROOT/'docs/reference-feature-inventory.json').read_text());sources={k:list((ROOT/'output/testing/inventory'/k).glob('*.js')) for k in base}
 report={'goal':{'target':'100% of reachable MPMB behavior in the supplied 2014, 2024 and Ashnar PDFs, including all predefined class choices and real table usage','general_acrobat_javascript_is_target':False,'achieved':False},'schema':4,'claim':'Call sites are inventory, not behavioral passes. Partial support does not establish full compatibility.','features':[],'observed_calls':[],'evidence':{}}
 for api,(status,note) in FEATURES.items():
  report['features'].append(dict(api=api,status=status,note=note,call_sites={k:sum(f.read_text().count(api) for f in files) if files else None for k,files in sources.items()},reference_counts={k:v['api_usage'][api] for k,v in base.items()}))
 counts={}
 for fixture,files in sources.items():
  for f in files:
   for obj,method in re.findall(r'\b(app|util|tDoc|dialog)\.([A-Za-z_]\w*)\s*\(',f.read_text()):
    key=obj+'.'+method;counts.setdefault(key,{})[fixture]=counts.setdefault(key,{}).get(fixture,0)+1
 for api,values in sorted(counts.items()):
  obj,method=api.split('.');report['observed_calls'].append({'api':api,'call_sites':{k:values.get(k,0) for k in base},'status':'partial' if method in PARTIAL.get(obj,set()) else 'unsupported-or-unverified'})
 def evidence(name,path):
  if not path:return None
  file=Path(path);data=json.loads(file.read_text());report['evidence'][name]={'path':str(file.relative_to(ROOT) if file.is_absolute() and file.is_relative_to(ROOT) else file),'passed':data.get('passed',False)};return data
 evidence('fresh_reference_qualification',args.reference_qualification);evidence('fresh_three_fixture_reader_validation',args.validation)
 if args.ashnar_comparison:
  comparison=json.loads(Path(args.ashnar_comparison).read_text());report['ashnar_complete_comparison']={k:v for k,v in comparison.items() if k not in ['native','reader','value_differences']}
 a=evidence('native_acceptance',args.acceptance);w=evidence('acrobat_roundtrips',args.acrobat)
 desktops=[evidence('desktop_'+str(i),s) for i,s in enumerate(args.desktop)]
 imp=evidence('local_file_import',args.imports);ash=evidence('ashnar',args.ashnar);gen=evidence('generated_page_probe',args.generated)
 core=bool(a and a.get('passed') and w and w.get('passed') and len(w.get('cases',[]))==2 and len(desktops)==2 and all(d and d.get('passed') for d in desktops))
 report['milestone']={'status':'passed-defined-slice' if core else 'unverified-or-incomplete','native_cases':len(a.get('cases',[])) if a else 0,'acrobat_cases':len(w.get('cases',[])) if w else 0,'desktop_cases':len(desktops),'scope':'Both supplied sheets: original initialization, edit/calculation, original class selection, rendering, native save/reopen, real Acrobat reopen/save, independent fields/widgets/appearance/scripts checks. Full compatibility remains incomplete.'}
 evidence('latest_native_regression',args.native_regression)
 ext=evidence('extended',args.extended)
 if ext:
  imp=ext.get('workflows',{}).get('imports');ash=ext.get('workflows',{}).get('ashnar')
 gw=evidence('generated_page_acrobat',args.generated_acrobat)
 life=evidence('page_lifecycle',args.lifecycle);lr=evidence('page_lifecycle_acrobat',args.lifecycle_acrobat)
 if args.comparisons:
  report['generated_comparisons']=json.loads(Path(args.comparisons).read_text())
 report['page_lifecycle']={'native':'passed-defined-probe' if life and life.get('passed') else 'unverified','acrobat':'passed-defined-probe' if lr and lr.get('passed') else 'failed-or-unverified','scope':'Hide/reveal shared template, remove/readd companion, retained character fields and changed Calculate action/order save and native reopen.'}
 workflows={name:('passed-defined-probe' if gen and gen.get('passed') and len([c for c in gen.get('cases',[]) if c.get('workflow')==name and c.get('passed')])==2 else 'unverified') for name in ['companion','wildshape','spells']}
 report['generated_acrobat_cases']=len(gw.get('cases',[])) if gw else 0
 report['runtime_repairs']=[{'id':'mpmb-2024-261023-wildshape-pop-typo','authorized_by_user':True,'qualification':'Exact Functions2 SHA-256 fingerprint and function markers','embedded_scripts_modified':False,'strict_mode':'MPMB_STRICT_ORIGINAL_SCRIPTS=1','behavior':'Replaces erroneous pop property reads with the local prop in the runtime function only.'}]
 report['next_workflows']={'companion_pages':workflows['companion'],'wild_shape_pages':workflows['wildshape'],'spell_generation':workflows['spells'],'local_file_import':'passed-defined-probe' if imp and imp.get('passed') else 'unverified','ashnar':'passed-defined-probe' if ash and ash.get('passed') else 'failing-or-unverified'}
 classes=evidence('class_progression_audit',args.classes);scope=evidence('actual_mpmb_counterexamples',args.scope_audit)
 if classes:
  report['class_coverage']={'full_mpmb_compatibility':False,'scope':classes['scope'],'fixtures':[{'fixture':f['fixture'],'tested_class_cases':len(f['cases']),'passed':sum(c['passed'] for c in f['cases']),'failed':sum(not c['passed'] for c in f['cases']),'excluded_or_ambiguous':len(f['excluded_or_ambiguous'])} for f in classes['fixtures']]}
 if scope:report['observed_incompatible_mpmb_workflows']=scope['cases']
 field_methods=['buttonGetIcon','buttonSetIcon','buttonSetCaption','getArray','setAction','checkThisBox','isBoxChecked','setItems','clearItems','insertItemAt','deleteItemAt','getItemAt','setFocus']
 report['observed_field_method_calls']=[{'method':method,'status':'partial-or-unverified','call_sites':{k:sum(len(re.findall(r'\.'+method+r'\s*\(',f.read_text())) for f in files) if files else None for k,files in sources.items()}} for method in field_methods]
 report['field_method_count_scope']='Method-name call sites may include other object types (for example Bookmark.setAction); dynamic receiver resolution and field-action source are not inferred as behavioral passes.'
 report['static_inventory_scope']='Regex call sites in original embedded document scripts; dynamic field actions and indirect calls are additional coverage work.'
 report['unsupported_outside_confirmed_mpmb_usage']=['Template overlay spawning (current inspected MPMB calls request overlay=false)']
 report['remaining_gaps']=['All predefined class/subclass/source selections and table-use workflows beyond base-class progression smoke','Wider generated-creature and spell combinations beyond the six qualified cases','Non-normal icon faces and distinct rollover/down button captions','Full dialog control coverage and exact layout','Complete rich text/font/appearance fidelity','URL/binary imports and printing/export','Field/widget/appearance differences outside the defined assertions','Bookmark actions, style and tree persistence']
 (ROOT/'docs/native-compatibility.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
