#!/usr/bin/env python3
"""Original Reader DirectImport of a saved Warlock or legacy Ashnar character.

The format2 observer forwards the original call/exception and catches logging
getter errors locally. It is diagnostic interposition, not an original-script
repair. Source bytes must remain unchanged; no derived expectations are written.
"""
import argparse,hashlib,importlib.util,json,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from spells import wait_dialog
from verify import inspect,script_hashes
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
SCRIPT=r"""var iFileName='Original PDF import observation.js';(function(d){Value('User Script','');d.__importFormatErrors=[];var original=format2;format2=function(){try{return original.apply(this,arguments)}catch(error){var row={};function read(key,fn){try{row[key]=fn()}catch(e){row[key]={getter_error:String(e)}}}read('field',function(){return event.target.name});read('event',function(){return event.name});read('errorType',function(){return error.name});read('error',function(){return String(error)});read('valueType',function(){return typeof event.value});read('value',function(){return String(event.value)});d.__importFormatErrors.push(row);throw error}};var r={returned:false,sentinel:'\u00a0\u2028\ud83d\ude00'};try{DirectImport(true);r.returned=true}catch(error){r.operation_error=String(error)}finally{format2=original}r.originalActionErrors=d.__importFormatErrors;delete d.__importFormatErrors;r.openDocuments=app.activeDocs.length;r.leftImportGlobals=!!(global.docFrom||global.docTo);r.cleanupPerformed=false;if(global.docFrom&&global.docFrom.path!==d.path){global.docFrom.dirty=false;global.docFrom.closeDoc(true);delete global.docFrom;delete global.docTo;r.cleanupPerformed=true}var known=classes.known.warlock||{},spells=CurrentSpells.warlock||{};r.identity={level:known.level,subclass:known.subclass};r.cantrips=spells.selectCa||[];r.spells=spells.selectSp||[];r.choice=GetFeatureChoice('classes','warlock','eldritch invocations',true);r.excludedSources=CurrentSources.globalExcl;r.fields={};['Class and Levels','Character Level','Proficiency Bonus','Cha','Attack.1.To Hit','Attack.1.Damage','Carrying Capacity Multiplier'].forEach(function(name){try{r.fields[name]=d.getField(name).valueAsString}catch(error){r.fields[name]={getter_error:String(error)}}});r.pages=d.numPages;Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""


LEGACY_FIELDS=['Class and Levels','Character Level','Proficiency Bonus','Str','Dex','Con','Int','Wis','Cha','Str Mod','Dex Mod','Con Mod','Int Mod','Wis Mod','Cha Mod','HP Max','HP Current','AC','Initiative bonus','Carrying Capacity Multiplier','Speed','Spell save DC 1','Spell save DC 2']
for attack in range(1,4):
    LEGACY_FIELDS += ['Attack.'+str(attack)+'.'+suffix for suffix in ['Weapon Selection','To Hit','Damage','Mod','Range','Description']]
for resource in range(1,17):
    LEGACY_FIELDS += [prefix+' '+str(resource) for prefix in ['Limited Feature','Limited Feature Max Usages','Limited Feature Recovery','Limited Feature Used']]
LEGACY_CAPTURE=r"""r.identity={};Object.keys(classes.known).forEach(function(key){var k=classes.known[key];r.identity[key]={level:k.level,subclass:k.subclass}});r.spellcasting={};Object.keys(CurrentSpells).forEach(function(key){var s=CurrentSpells[key];r.spellcasting[key]={ability:s.ability,selectCa:s.selectCa||[],selectSp:s.selectSp||[],selectSpSB:s.selectSpSB||[],selectSpP:s.selectSpP||[]}});r.choices=CurrentFeatureChoices;r.excludedSources=CurrentSources.globalExcl;r.fields={};__FIELDS__.forEach(function(name){try{var f=d.getField(name);r.fields[name]=f?f.valueAsString:null}catch(error){r.fields[name]={getter_error:String(error)}}});r.rememberedSpells={};for(var i=0;i<d.numFields;i++){var n=d.getNthFieldName(i);if(/\.spells\.remember\./i.test(n))r.rememberedSpells[n]=d.getField(n).valueAsString}r.importedScripts={};var scripts=eval(d.getField('User_Imported_Files.Stringified').valueAsString);Object.keys(scripts).forEach(function(name){var text=String(scripts[name]),a=1,b=0;for(var i=0;i<text.length;i++){a=(a+text.charCodeAt(i))%65521;b=(b+a)%65521}r.importedScripts[name]={code_units:text.length,adler32_utf16:String((b*65536+a)>>>0)}});r.pages=d.numPages;Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""
LEGACY_SCRIPT=SCRIPT[:SCRIPT.index('var known=classes.known.warlock')]+LEGACY_CAPTURE.replace('__FIELDS__',json.dumps(LEGACY_FIELDS))


def validate_legacy_capture(captured):
    assert captured['returned'] and not captured.get('operation_error')
    assert captured['openDocuments']==1 and not captured['leftImportGlobals'] and not captured['cleanupPerformed']
    assert list(captured['identity'])==['monk'] and captured['identity']['monk']['level']==12
    assert captured['fields']['Character Level']=='12' and captured['fields']['Proficiency Bonus']=='4'
    assert captured['importedScripts'], 'The supplied legacy character has imported content'
    assert captured['rememberedSpells'], 'The supplied legacy character has a remembered spell page'


def acknowledge(owner,elements):
    buttons=[item for item in elements if item.get('owner')==owner and item.get('class')=='Button' and item.get('name')=='OK']
    assert len(buttons)==1,'Expected exact owned OK button'
    focus=c.command('inspect_focused')
    if focus['in_reader'] and focus['type']=='ControlType.Button' and focus['name']=='OK' and focus['native_window_handle']==buttons[0]['handle']:
        return c.command('keys',keys=' ')
    return c.command('invoke',name='OK',owner=owner)


def import_console(report,elements):
    roots=[item for item in elements if item.get('class')=='#32770' and item.get('name')=='JavaScript Debugger']
    if not roots:return None
    assert len(roots)==1,'More than one Reader console'
    owner=roots[0]['handle'];edits=[item for item in elements if item.get('owner')==owner and item.get('class')=='RICHEDIT50W'];assert len(edits)==1
    edit=edits[0];live=c.command('dialog_control',owner=owner,handle=edit['handle']);text=live['text']
    assert 'An error occurred during importing:' in text or 'requires you to make a selection of a sub-choice' in text,'Unexpected console content; no input sent'
    observed={'owner':owner,'edit':edit['handle'],'live':live}
    previous=report.setdefault('original_console',[])
    if not previous or previous[-1]['live']['text']!=text:previous.append(observed)
    return observed


def close_import_console(report):
    observed=import_console(report,c.command('inspect'))
    if observed is None:return
    focused=c.command('focus_control',owner=observed['owner'],handle=observed['edit']);assert focused['focused']
    report['console_close']={'focus':focused,'action':c.command('keys',keys='%{F4}')}
    assert not [item for item in c.command('inspect') if item.get('class')=='#32770' and item.get('name')=='JavaScript Debugger']


def wait_import_summary(source,report,folder):
    deadline=time.monotonic()+300
    normalize=lambda value:re.sub(r'\\+',lambda _:chr(92),value).replace('\r','').replace('\n','').lower()
    while time.monotonic()<deadline:
        elements=c.command('inspect')
        roots=[item for item in elements if item.get('class')=='#32770']
        for root in roots:
            if root.get('name')=='Things to consider about the import':return root,elements
            if root.get('name')=='Security Warning':
                owner=root['handle'];text=''.join(item.get('name','') for item in elements if item.get('owner')==owner)
                assert normalize(source) in normalize(text), 'Security warning is not the exact uploaded source PDF'
                allowed=[item for item in elements if item.get('owner')==owner and item.get('class')=='Button' and item.get('name')=='Allow'];assert len(allowed)==1
                report.setdefault('file_access',[]).append({'dialog':elements,'action':c.command('invoke',name='Allow',owner=owner)})
                (folder/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
            elif root.get('name')=='JavaScript Debugger':
                import_console(report,elements)
                (folder/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
            elif root.get('name')!='IMPORT FROM PDF DIALOG':
                report['unexpected_dialog']=elements
                raise RuntimeError('Unexpected import dialog: '+str(root.get('name')))
    raise RuntimeError('Original import summary did not appear within300 seconds')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--target',choices=['2014','2024'],default='2024');p.add_argument('--profile',choices=['warlock','legacy'],default='warlock');args=p.parse_args();observer=LEGACY_SCRIPT if args.profile=='legacy' else SCRIPT
    ready=json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
    assert args.source.is_file();source=next((ROOT/'Testing').glob('*_'+args.target+'_*.pdf'));folder=ROOT/'output/testing'/('reader-direct-import-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    remote=c.remote_path('runs/direct-import-target-'+str(time.time_ns())+'.pdf');from_path=c.remote_path('runs/direct-import-source-'+str(time.time_ns())+'.pdf')
    report={'passed':False,'scope':__doc__,'readiness':str(args.readiness.resolve()),'target':remote,'target_fixture':str(source.resolve()),'profile':args.profile,'source':from_path,'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest()};opened=False;pending=None
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            for local,path in [(source,remote),(args.source,from_path)]:subprocess.run(c.SCP+[str(local),c.SCP_TARGET + ':MPMB-Testing/runs/'+path.replace('\\','/').split('/')[-1]],check=True,capture_output=True)
            assert c.powershell('(Get-FileHash -Algorithm SHA256 '+c.literal(from_path)+').Hash').strip().lower()==report['source_sha256']
            opened=True;c.ensure_document(remote);c.script('set',path=remote,values={'User Script':observer});pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);report['request']=pending
            root,elements=wait_dialog('IMPORT FROM PDF DIALOG',time.monotonic()+90);report['import_controls']=elements
            edits=[item for item in elements if item.get('owner')==root['handle'] and re.fullmatch(r'Edit|RICHEDIT[0-9]+W',item.get('class','')) and item.get('enabled') and item.get('read_only') is False and item.get('name')=='']
            assert len(edits)==1,'Expected one observed editable source path'
            edit=edits[0];report['focus']=c.command('focus_control',owner=root['handle'],handle=edit['handle']);report['paste']=c.command('paste',value=from_path);assert report['paste']['verified']
            report['path_control']=c.command('dialog_control',owner=root['handle'],handle=edit['handle']);assert report['path_control']['text']==from_path
            buttons=[item for item in c.command('inspect') if item.get('owner')==root['handle'] and item.get('class')=='Button' and item.get('name')=='Import (takes a while)'];assert len(buttons)==1
            report['import_click']=c.command('invoke',name=buttons[0]['name'],owner=root['handle'])
            root,elements=wait_import_summary(from_path,report,folder);report['summary_controls']=elements;report['summary_ack']=acknowledge(root['handle'],elements)
            report['completion']=c.script_result(pending,timeout=120);pending=None
            close_import_console(report)
            summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['summary']=summary
            c.script('set',path=remote,values={'User Script':''});saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved
            report['close']=c.script('close',path=remote);opened=False;local=c.fetch(remote,folder/'reader-imported.pdf');captured=style.saved_capture(local,summary,source);report['captured']=captured
            assert captured['returned'] and not captured.get('operation_error') and not captured['cleanupPerformed'] and not captured['leftImportGlobals'] and captured['openDocuments']==1
            if args.profile=='legacy':validate_legacy_capture(captured)
            else:
                assert captured['identity']=={'level':5,'subclass':'warlock-fiend'} and captured['fields']['Attack.1.Damage']=='2×1d10+4'
                assert len(captured['cantrips'])==3 and len(captured['spells'])==6 and captured['choice']==['agonizing blast: eldritch blast']
            assert inspect(local,captured['fields'])['passed'] and script_hashes(local)==script_hashes(source)
            report['source_after_sha256']=c.powershell('(Get-FileHash -Algorithm SHA256 '+c.literal(from_path)+').Hash').strip().lower();assert report['source_after_sha256']==report['source_sha256']
            report['observation_verified']=True
            report['workflow_passed']=not any('An error occurred during importing:' in entry['live']['text'] for entry in report.get('original_console',[]))
            report['passed']=report['workflow_passed']
            if not report['passed']:report['error']='Original DirectImport reported an internal failure; see original_console'
    except Exception as error:
        report['error']=str(error)
        if opened:
            try:shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
            except Exception as diagnostic:report['diagnostic_error']=str(diagnostic)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    elements=c.command('inspect');roots=[e for e in elements if e.get('class')=='#32770']
                    for root in roots:
                        if root.get('name')=='IMPORT FROM PDF DIALOG':c.command('invoke',name='Cancel',owner=root['handle'])
                        elif root.get('name') in ['Things to consider about the import','File not found','File is not one of MPMB\'s Character Record Sheets']:acknowledge(root['handle'],elements)
                    if pending:report['original_completion']=c.script_result(pending,timeout=90)
                    close_import_console(report)
                    retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
            except Exception as error:report['cleanup_error']=str(error)
        (folder/'direct-import.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'direct-import.json',flush=True)

    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
