#!/usr/bin/env python3
"""Inspect/cancel the original Reader class feature popup on a selected Warlock.

Transport discovery only; no invocation selection is qualified by cancellation.
"""
import argparse,importlib.util,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import inspect,script_hashes
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--readiness',type=Path);p.add_argument('--preflight',type=Path);p.add_argument('--native-menu',action='store_true');p.add_argument('--field-button',action='store_true');p.add_argument('--enter',action='store_true');p.add_argument('--catalog',action='store_true');p.add_argument('--expand',action='store_true');args=p.parse_args()
    reference=json.loads(args.reader.read_text());assert reference['passed']
    if args.preflight:
        qualification=json.loads(args.preflight.read_text());assert qualification['passed'] and qualification['checks']['popup-menu-controls']
    else:
        assert args.readiness;ready=json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
    folder=ROOT/'output/testing'/('reader-warlock-menu-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    report={'passed':False,'scope':__doc__,'activation':('original focused PDF pushbutton + '+('Enter' if args.enter else 'Space')) if args.field_button else 'original function through application menu','qualification':str((args.preflight or args.readiness).resolve()),'pre_readiness_transport_probe':bool(args.preflight)};pending=None;opened=False;observed_menu=False;summary=None;remote=c.remote_path('runs/warlock-menu-'+str(time.time_ns())+'.pdf');report['reader_path']=remote
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP+[reference['selected_pdf'],c.SCP_TARGET + ':MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True)
            opened=True;c.ensure_document(remote);fields=reference['selected']['fields'];assert c.script('read',path=remote,fields=list(fields))['fields']==fields
            summary=None
            if args.catalog:
                observer=r"""var iFileName='Warlock menu catalog observer.js';(function(d){var made=MakeClassMenu(),k=classes.known.warlock||{},cl=CurrentClasses.warlock||{},f=(cl.features||{})['eldritch invocations']||{},r={made:made,level:k.level,currentClasses:Object.keys(CurrentClasses),features:Object.keys(cl.features||{}),invocationChoices:(f.extrachoices||[]).length,roots:[],targets:[],sentinel:'\u00a0\u2028\ud83d\ude00'};function walk(a,p){for(var i=0;i<a.length;i++){var n=a[i],path=p.concat(n.cName);if(/agonizing/i.test(n.cName||''))r.targets.push({path:path,result:n.cReturn,enabled:n.bEnabled,marked:n.bMarked});if(n.oSubMenu)walk(n.oSubMenu,path);}}for(var i=0;i<Menus.classfeatures.length;i++)r.roots.push({name:Menus.classfeatures[i].cName,enabled:Menus.classfeatures[i].bEnabled});walk(Menus.classfeatures,[]);Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""
                c.script('set',path=remote,values={'User Script':observer});pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);c.script_result(pending,timeout=90);pending=None
                summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['catalog_summary']=summary;c.script('set',path=remote,values={'User Script':''})
            if args.field_button:
                c.script('focus',path=remote,field='Class Features Menu');report['button_activation']=c.command('keys',keys='{ENTER}' if args.enter else ' ')
            else:
                pending=c.script_submit('call',path=remote,name='ClassFeatureOptions',args=[]);report['request']=pending
            if args.native_menu:
                elements=c.command('inspect');menus=[e for e in elements if e.get('class')=='#32768'];assert len(menus)==1, 'Expected one observed native popup'
                observed_menu=True;owner=menus[0]['handle'];report['native_before']=c.command('inspect_menu',owner=owner)
                report['focus_before']=c.command('inspect_focused')
            ui=c.command('inspect_uia');(folder/'popup-uia.json').write_text(json.dumps(ui,indent=2)+'\n')
            if args.native_menu:
                report['native_after']=c.command('inspect_menu',owner=owner)
                report['focus_after']=c.command('inspect_focused')
                assert report['native_after']==report['native_before'], 'Inspection changed the popup'
                assert report['focus_before']['foreground_pid']==report['focus_after']['foreground_pid'] and report['focus_after']['in_reader'], 'Inspection changed Reader focus'
                report['focused_menu_items']=report['focus_after'].get('children',[])
                assert len(report['focused_menu_items'])==len(report['native_before']['items']) and all(item.get('name') and item.get('type')=='ControlType.MenuItem' for item in report['focused_menu_items']), 'Full focused-provider menu labels are unavailable'
            else:observed_menu=any(e.get('type') in ['ControlType.Menu','ControlType.MenuItem'] for e in ui)
            if args.expand:
                assert args.native_menu
                target=report['focused_menu_items'][0]
                try:c.command('activate_menu',owner=owner,position=0,name=target['name']+' - wrong name')
                except RuntimeError as error:assert 'name differs' in str(error);report['wrong_name_rejected']=True
                else:raise AssertionError('Incorrect popup name accepted')
                report['expanded']=c.command('activate_menu',owner=owner,position=0,name=target['name'])
                expanded=c.command('inspect_focused');report['expanded_focus']=expanded
                assert expanded['in_reader'] and expanded['type']=='ControlType.Menu'
                assert any(item['name'].startswith('Eldritch Invocation') for item in expanded['children']), 'Invocation category is absent after actual expansion'
            report['menu_observed']=observed_menu
            shot=c.command('screenshot');c.fetch(shot['path'],folder/'popup.png')
            assert observed_menu, 'No accessible popup menu observed'
            report['offered']=[e for e in ui if e.get('type')=='ControlType.MenuItem']
            for _ in range(4):
                c.command('keys',keys='{ESC}')
                ui=c.command('inspect_uia')
                if not any(e.get('type') in ['ControlType.Menu','ControlType.MenuItem'] or e.get('class')=='#32768' for e in ui):break
            else:raise AssertionError('Popup still visible after bounded cancellation')
            if pending:report['cancel_result']=c.script_result(pending,timeout=90);pending=None
            assert c.script('read',path=remote,fields=list(fields))['fields']==fields
            saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved
            report['close']=c.script('close',path=remote);opened=False;local=c.fetch(remote,folder/'reader.pdf')
            assert inspect(local,fields)['passed'];source=next((ROOT/'Testing').glob('*_2024_*.pdf'));assert script_hashes(local)==script_hashes(source)
            if summary:report['catalog']=style.saved_capture(local,summary,source)
            report['passed']=True
    except Exception as error:
        report['error']=str(error)
        try:shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
        except Exception as diagnostic:report['diagnostic_error']=str(diagnostic)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    if observed_menu:c.command('keys',keys='{ESC}')
                    if pending:report['cleanup_result']=c.script_result(pending,timeout=10)
                    retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);local=c.fetch(retained,folder/'failed-retained.pdf')
                    if summary:report['catalog']=style.saved_capture(local,summary,next((ROOT/'Testing').glob('*_2024_*.pdf')))
            except Exception as error:report['cleanup_error']=str(error)
        (folder/'menu.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'menu.json',flush=True)


if __name__=='__main__':main()
