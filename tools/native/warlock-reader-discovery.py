#!/usr/bin/env python3
"""Discover original Reader Warlock spell controls, with optional real text selection.

Default mode cancels discovery. --select-spells additionally types three actual
offered cantrips and six spells and generates a sheet; invocation, subsequent
reopen and complete table qualification remain separate. Reader computes all
derived values; the observer never supplies expected result fields.
"""
import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from spells import wait_dialog
from verify import inspect
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py')
style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
spec_input=importlib.util.spec_from_file_location('spell_input',ROOT/'tools/native/reader-spell-input.py')
spell_input=importlib.util.module_from_spec(spec_input);spec_input.loader.exec_module(spell_input)
ADDON=r"""var iFileName='Warlock spell options observer.js';(function(d){
 var w=CurrentSpells.warlock,k=classes.known.warlock;
 var result={identity:{level:k.level,subclass:k.subclass},excludedSources:CurrentSources.globalExcl,
 cantrips:spDias.spellSelect.listCa[2],spells:spDias.spellSelect.listSp[2],
 invocations:GetFeatureChoice('classes','warlock','eldritch invocations',true),selectedCantrips:w.selectCa||[],selectedSpells:w.selectSp||[],fields:{},generated:[],sentinel:'\u00a0\u2028\ud83d\ude00'};
 ['Class and Levels','Character Level','Proficiency Bonus','Attack.1.To Hit','Attack.1.Damage'].forEach(function(n){result.fields[n]=d.getField(n).valueAsString});
 var pref=What('Template.extras.SSfront').split(','),prefix='';for(var p=0;p<pref.length;p++){if(pref[p])prefix=pref[p];}
 if(prefix){for(var row=0;row<100;row++){var rn=prefix+'spells.remember.'+row,rf=d.getField(rn);if(rf&&/^eldritch blast##/.test(rf.valueAsString)){var dn=prefix+'spells.description.'+row;result.generated.push({remember:rn,description:dn});result.fields[rn]=rf.valueAsString;result.fields[dn]=d.getField(dn).valueAsString;}}}
 Value('PC Name',JSON.stringify(result).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);"""


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--readiness',type=Path,required=True);parser.add_argument('--select-spells',action='store_true');parser.add_argument('--native-report',type=Path);args=parser.parse_args()
    native=json.loads(args.native_report.read_text()) if args.native_report else None
    if native:assert args.select_spells and native['passed'] and native['source_profile']=='original startup defaults'
    ready=json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24
    assert ready['harness_sha256']==c.harness_fingerprint(), 'Reference harness changed; rerun preflight/readiness'
    folder=ROOT/'output/testing'/('reader-warlock-discovery-'+str(time.time_ns()));folder.mkdir()
    report={'passed':False,'scope':__doc__,'readiness':str(args.readiness.resolve())};print(folder,flush=True)
    remote=c.remote_path('runs/warlock-discovery-'+str(time.time_ns())+'.pdf');report['reader_path']=remote;opened=False;pending=None
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/blank-2024.pdf'))+' '+c.literal(remote)+' -Force;(Get-Item '+c.literal(remote)+').IsReadOnly=$false')
            opened=True;c.ensure_document(remote)
            c.script('set',path=remote,values={name:'18' for name in ['Str','Dex','Con','Int','Wis','Cha']})
            pending=c.script_submit('call',path=remote,name='ApplyClasses',args=['Warlock (The Fiend) 5',False]);report['class_request']=pending
            report['class_result']=c.script_result(pending,timeout=120);pending=None
            ident=c.script_submit('call',path=remote,name='GenerateSpellSheet',args=[]);pending=ident;report['spell_request']=ident
            root,elements=wait_dialog('SPELL SELECTION DIALOG',time.monotonic()+90)
            (folder/'dialog-native.json').write_text(json.dumps(elements,indent=2)+'\n')
            combos=[item for item in elements if item.get('owner')==root['handle'] and item.get('class')=='ComboBox' and item.get('enabled')]
            assert combos, 'No enabled native dropdowns found'
            report['observed_combo_count']=len(combos)
            report['combo_first_state']=c.command('dialog_control',owner=root['handle'],handle=combos[0]['handle'])
            report['editable_controls']=[item for item in elements if item.get('owner')==root['handle'] and item.get('class') in ('Edit','RICHEDIT50W') and item.get('enabled') and item.get('read_only') is False]
            assert report['editable_controls'], 'No editable spell controls observed'
            shot=c.command('screenshot');c.fetch(shot['path'],folder/'spell-dialog.png')
            assert any(e.get('owner')==root['handle'] and e.get('name')=='Cancel and Stop' for e in elements), 'Cancel is not offered'
            c.command('invoke',name='Cancel and Stop',owner=root['handle'])
            report['cancel_result']=c.script_result(ident,timeout=90);pending=None
            c.script('set',path=remote,values={'User Script':ADDON})
            observer=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);report['observer_request']=observer;c.script_result(observer,timeout=90)
            summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['reader_summary']=summary
            c.script('set',path=remote,values={'User Script':''})
            saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);report['reader_saved_path']=saved;remote=saved
            report['close']=c.script('close',path=saved);opened=False
            local=c.fetch(saved,folder/'reader.pdf')
            source=next((ROOT/'Testing').glob('*_2024_*.pdf'))
            report['captured']=style.saved_capture(local,summary,source)
            assert report['captured']['identity']=={'level':5,'subclass':'warlock-fiend'}
            report['pdf']=str(local)
            if args.select_spells:
                opened=True;c.ensure_document(remote)
                # Use the original field focus/edit/Tab route so weapon actions
                # run as they do during table use.
                c.script('focus',path=remote,field='Attack.1.Weapon Selection')
                typed=c.command('paste',value='Eldritch Blast');assert typed['verified']
                pending=c.script_submit('call',path=remote,name='GenerateSpellSheet',args=[])
                root,elements=wait_dialog('SPELL SELECTION DIALOG',time.monotonic()+90)
                (folder/'selection-native.json').write_text(json.dumps(elements,indent=2)+'\n')
                report['spell_inputs']=spell_input.type_selection(c,root['handle'],elements,report['captured'])
                options=[e for e in elements if e.get('owner')==root['handle'] and e.get('class')=='Button' and e.get('name','').startswith('3rd-level and lower spells known')];assert len(options)==1
                report['spell_list_option']=options[0]['name'];c.command('invoke',name=options[0]['name'],owner=root['handle'])
                buttons=[e for e in elements if e.get('owner')==root['handle'] and e.get('class')=='Button' and e.get('name')=='Continue to Next Dialog >>'];assert len(buttons)==1
                c.command('invoke',name=buttons[0]['name'],owner=root['handle'])
                root,elements=wait_dialog('SPELL LIST GENERATION DIALOG',time.monotonic()+90)
                assert any(e.get('owner')==root['handle'] and e.get('class')=='Button' and e.get('name')=='Generate the Spell Sheet' for e in elements)
                c.command('invoke',name='Generate the Spell Sheet',owner=root['handle'])
                report['generation']=c.script_result(pending,timeout=120);pending=None
                c.script('set',path=remote,values={'User Script':ADDON})
                pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);c.script_result(pending,timeout=90);pending=None
                summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name']
                report['selected_reader_summary']=summary;c.script('set',path=remote,values={'User Script':''})
                saved=remote[:-4]+'-selected.pdf';c.script('save',path=remote,output=saved);remote=saved
                report['selected_close']=c.script('close',path=saved);opened=False
                local=c.fetch(saved,folder/'reader-selected.pdf');captured=style.saved_capture(local,summary,source)
                report['selected']=captured
                assert sorted(captured['selectedCantrips'])==sorted(spell_input.CANTRIPS)
                assert sorted(captured['selectedSpells'])==sorted(spell_input.SPELLS)
                assert captured['fields']['Attack.1.To Hit']=='+7' and captured['fields']['Attack.1.Damage']=='2×1d10'
                assert len(captured['generated'])==1, 'Expected one generated Eldritch Blast row'
                assert inspect(local,captured['fields'])['passed'], 'Saved generated/derived fields differ'
                report['selected_pdf']=str(local)
                if native:
                    phase=native['phases']['selected-spells']
                    nd=[value for name,value in phase['fields'].items() if 'spells.description.' in name];assert len(nd)==1
                    rd=captured['fields'][captured['generated'][0]['description']]
                    normalize=lambda value:value.replace('\r\n','\n').replace('\r','\n')
                    comparison={
                        'source_exclusions_as_sets':sorted(set(phase['excludedSources']))==sorted(set(captured['excludedSources'])),
                        'cantrips':sorted(phase['cantrips'])==sorted(captured['selectedCantrips']),
                        'spells':sorted(phase['spells'])==sorted(captured['selectedSpells']),
                        'invocations':phase['choice']==captured['invocations'],
                        'attack_fields':all(phase['fields'][n]==captured['fields'][n] for n in ['Attack.1.To Hit','Attack.1.Damage']),
                        'generated_description_line_endings_normalized':normalize(nd[0])==normalize(rd),
                    }
                    report['native_comparison']={'report':str(args.native_report.resolve()),'checks':comparison,'scope':'Initial selected-spell phase only; source sets, spell sets, invocation list, exact attack fields and generated Eldritch Blast description with CR/CRLF to LF normalization. Other phase/state/rendering parity remains unqualified.'}
                    assert all(comparison.values()), 'Native/Reader selected-spell comparison differs'

            report['passed']=True
    except Exception as error:
        report['error']=str(error)
        try:
            shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
            (folder/'failure-native.json').write_text(json.dumps(c.command('inspect'),indent=2)+'\n')
        except Exception as diagnostic_error:report['diagnostic_error']=str(diagnostic_error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    report['cleanup_cancellations']=[]
                    for _ in range(3):
                        elements=c.command('inspect');foreground=c.command('health')['foreground_handle']
                        roots=[r for r in elements if r.get('handle')==foreground and r.get('class')=='#32770']
                        if not roots:break
                        buttons=[e for e in elements if e.get('class')=='Button' and e.get('owner')==foreground and e.get('name','').startswith('Cancel')]
                        if len(buttons)!=1:break
                        report['cleanup_cancellations'].append(c.command('invoke',name=buttons[0]['name'],owner=foreground))
                    if pending:
                        try:report['cleanup_result']=c.script_result(pending,timeout=90)
                        except Exception as result_error:report['cleanup_result_error']=str(result_error)
                    retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
            except Exception as cleanup_error:report['cleanup_error']=str(cleanup_error)
        (folder/'discovery.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'discovery.json',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
