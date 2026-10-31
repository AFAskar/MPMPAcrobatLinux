#!/usr/bin/env python3
"""Reader-selected Warlock -> edited native -> edited Reader -> edited native.

Each fresh runtime changes the actual weapon and restores Eldritch Blast through
original field actions, and edits/restores the editable generated description
before resaving. An optional captured invocation phase checks that exact state.
This is bounded selected-spell/invocation state and single-line positioning
persistence, not full rendering or complete invocation coverage.
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import inspect,script_hashes,canonical_fields
from pypdf import PdfReader
from pypdf.generic import ContentStream
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py')
style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)


def baseline(path,field):
    reader=PdfReader(path);node=reader.get_object(canonical_fields(reader)[field]['reference'])
    ids={ref.get_object().indirect_reference.idnum for ref in node.get('/Kids',[node])}
    widgets=[ref.get_object() for page in reader.pages for ref in page.get('/Annots',[]) if ref.idnum in ids]
    assert len(widgets)==1, 'Expected one active description widget'
    ap=widgets[0]['/AP']['/N'].get_object()
    assert list(ap.get('/Matrix',[1,0,0,1,0,0]))==[1,0,0,1,0,0]
    operations=ContentStream(ap,reader).operations
    first=next(i for i,(_,op) in enumerate(operations) if op in [b'Tm',b'Td'])
    assert not any(op==b'cm' for _,op in operations[:first]), 'Transformed appearance needs separate qualification'
    operands,operator=operations[first];y=float(operands[5] if operator==b'Tm' else operands[1]);x=float(operands[4] if operator==b'Tm' else operands[0])
    if operator==b'Tm':assert list(operands[:4])==[1,0,0,1], 'Scaled text needs separate qualification'
    fonts=[str(font.get_object().get('/BaseFont')) for font in ap['/Resources'].get('/Font',{}).values()]
    return {'baseline':y,'horizontal_origin':x,'font_names':fonts,'normal_appearance_sha256':hashlib.sha256(ap.get_data()).hexdigest()}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--check-origin',action='store_true',help='Also require rebuilt horizontal text origins to match Reader');p.add_argument('--invocation-phase',choices=['selected-spells','invocation','removed','readded'],help='Use this saved phase from a passing original Reader invocation report');args=p.parse_args()
    reference=json.loads(args.reader.read_text());native=json.loads(args.native.read_text());ready=json.loads(args.readiness.read_text())
    assert reference['passed'] and native['passed'] and ready['passed'] and len(ready['cases'])==24
    assert ready['harness_sha256']==c.harness_fingerprint()
    if args.invocation_phase:
        phase=reference['phases'][args.invocation_phase];captured=phase['captured']
        assert all(phase['checks'].values()), 'Invocation phase comparisons did not pass'
        reference={'passed':reference['passed'],'selected_pdf':phase['pdf'],'selected':{
            'identity':captured['identity'],'fields':captured['fields'],
            'selectedCantrips':captured['cantrips'],'selectedSpells':captured['spells'],
            'invocations':captured['choice'],'excludedSources':captured['excludedSources']}}
    expected=reference['selected'];fields=expected['fields'];descriptions=[name for name in fields if 'spells.description.' in name];assert len(descriptions)==1;description=descriptions[0];marker='MPMB editable description check';source=next((ROOT/'Testing').glob('*_2024_*.pdf'))
    binary=args.native.parent/'mpmb-reader';assert hashlib.sha256(binary.read_bytes()).hexdigest()==native['binary_sha256']
    folder=ROOT/'output/testing'/('warlock-selected-roundtrip-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    frozen=folder/'mpmb-reader';shutil.copy2(binary,frozen)
    report={'passed':False,'scope':__doc__,'invocation_phase':args.invocation_phase,'native_report':str(args.native.resolve()),'reader_report':str(args.reader.resolve()),'readiness':str(args.readiness.resolve()),'binary_sha256':native['binary_sha256'],'description_edited':True};opened=False;remote=None;pending=None
    state_assert="""(function(){var w=CurrentSpells.warlock,k=classes.known.warlock;
      if(k.level!==5||k.subclass!=='warlock-fiend')throw Error('Warlock identity changed');
      var state={cantrips:w.selectCa,spells:w.selectSp,invocations:GetFeatureChoice('classes','warlock','eldritch invocations',true),excludedSources:CurrentSources.globalExcl};
    """
    for name,key in [('cantrips','selectedCantrips'),('spells','selectedSpells'),('invocations','invocations'),('excludedSources','excludedSources')]:
        state_assert+='if(JSON.stringify(state['+json.dumps(name)+'].slice().sort())!=='+json.dumps(json.dumps(sorted(expected[key]),separators=(',',':')))+')throw Error('+json.dumps(name+' changed after reopen')+');'
    state_assert+='return state;})()'
    def native_edit(label,pdf):
        def execute(suffix,input_pdf,steps,out,wanted):
            scenario=folder/(suffix+'-scenario.json');evidence=folder/(suffix+'-report.json')
            scenario.write_text(json.dumps({'steps':steps,'dialogs':[{'result':'ok'}]*30,'alerts':[1]*100}))
            with (folder/(suffix+'.log')).open('w') as log:
                result=subprocess.run([str(frozen),str(input_pdf),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=300)
            data=json.loads(evidence.read_text());assert result.returncode==0 and data['passed'],data.get('error')
            assert inspect(out,wanted)['passed'];assert script_hashes(out)==script_hashes(source)
            return str(evidence)
        out=folder/(label+'.pdf');marked=folder/(label+'-marker.pdf');marked_fields={**fields,description:marker}
        steps=[{'op':'advance','ms':4100},{'op':'eval','code':state_assert},
               {'op':'edit','field':'Attack.1.Weapon Selection','value':'Quarterstaff'},{'op':'advance','ms':1000},
               {'op':'eval','code':"if(/2[×x]1d10/.test(getField('Attack.1.Damage').valueAsString))throw Error('Weapon edit did not change damage');getField('Attack.1.Damage').valueAsString"},
               {'op':'edit','field':'Attack.1.Weapon Selection','value':'Eldritch Blast'},{'op':'advance','ms':1000},
               {'op':'assert','values':fields},{'op':'edit','field':description,'value':marker},
               {'op':'assert','values':marked_fields},{'op':'eval','code':state_assert},{'op':'save','path':str(marked)}]
        marked_probe=execute(label+'-marker',pdf,steps,marked,marked_fields)
        # Reopen the genuinely changed saved value. Restoring within one runtime
        # can legitimately reuse the unchanged input AP and would hide failures.
        steps=[{'op':'advance','ms':4100},{'op':'assert','values':marked_fields},{'op':'eval','code':state_assert},
               {'op':'edit','field':description,'value':fields[description]},
               {'op':'assert','values':fields},{'op':'eval','code':state_assert},{'op':'save','path':str(out)}]
        evidence=execute(label,marked,steps,out,fields)
        report[label]={'pdf':str(out),'probe':evidence,'marker_pdf':str(marked),'marker_probe':marked_probe}
        return out

    try:
        first=native_edit('native-from-reader',Path(reference['selected_pdf']))
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            remote=c.remote_path('runs/warlock-selected-roundtrip-'+str(time.time_ns())+'.pdf');report['reader_path']=remote
            subprocess.run(c.SCP+[str(first),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True)
            opened=True;c.ensure_document(remote)
            assert c.script('read',path=remote,fields=list(fields))['fields']==fields
            for weapon in ['Quarterstaff','Eldritch Blast']:
                c.script('focus',path=remote,field='Attack.1.Weapon Selection');typed=c.command('paste',value=weapon);assert typed['verified']
                values=c.script('read',path=remote,fields=['Attack.1.Damage'])['fields']
                if weapon=='Quarterstaff':
                    assert '1d10' not in values['Attack.1.Damage'];report['reader_intermediate_damage']=values['Attack.1.Damage']
            assert c.script('read',path=remote,fields=list(fields))['fields']==fields
            observed=c.script('read',path=remote,fields=[description])['fields'][description]
            for text in [marker,observed]:
                c.script('focus',path=remote,field=description);typed=c.command('paste',value=text);assert typed['verified']
                assert c.script('read',path=remote,fields=[description])['fields'][description]==text
                if text==marker:
                    marker_remote=remote[:-4]+'-marker.pdf';c.script('save',path=remote,output=marker_remote);remote=marker_remote;report['reader_marker_path']=marker_remote
            assert c.script('read',path=remote,fields=list(fields))['fields']==fields
            observer="var iFileName='Selected Warlock persistence observer.js';(function(d){var w=CurrentSpells.warlock,k=classes.known.warlock,r={identity:{level:k.level,subclass:k.subclass},selectedCantrips:w.selectCa,selectedSpells:w.selectSp,invocations:GetFeatureChoice('classes','warlock','eldritch invocations',true),excludedSources:CurrentSources.globalExcl,fields:{},sentinel:'\\u00a0\\u2028\\ud83d\\ude00'};"+json.dumps(list(fields))+".forEach(function(n){r.fields[n]=d.getField(n).valueAsString});Value('PC Name',JSON.stringify(r).replace(/[\\u007f-\\uffff]/g,function(c){return '\\\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"
            c.script('set',path=remote,values={'User Script':observer})
            pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);c.script_result(pending,timeout=90);pending=None
            summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['reader_summary']=summary
            c.script('set',path=remote,values={'User Script':''})
            saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);remote=saved
            report['reader_close']=c.script('close',path=remote);opened=False
            local=c.fetch(remote,folder/'reader-edited.pdf');captured=style.saved_capture(local,summary,source);report['reader_capture']=captured
            assert captured['identity']==expected['identity'] and captured['fields']==fields
            for key in ['selectedCantrips','selectedSpells','invocations','excludedSources']:assert sorted(captured[key])==sorted(expected[key]), key+' changed in Reader'
            assert inspect(local,fields)['passed']
            local_marker=c.fetch(marker_remote,folder/'reader-marker.pdf');assert inspect(local_marker,{**fields,description:marker})['passed'];assert script_hashes(local_marker)==script_hashes(source)
        last=native_edit('native-after-reader',local)
        measures={name:baseline(path,description) for name,path in [('reference',Path(reference['selected_pdf'])),('native-from-reader',first),('reader-edited',local),('native-after-reader',last),('reader-marker',local_marker),('native-from-reader-marker',Path(report['native-from-reader']['marker_pdf'])),('native-after-reader-marker',Path(report['native-after-reader']['marker_pdf']))]}
        report['description_baselines']={'field':description,'tolerance_points':0.001,'measurements':measures,'scope':'First untransformed text baseline only, after actual editable description changes/restoration. Pixel, horizontal advance and full appearance equality remain unqualified.'}
        assert all(abs(value['baseline']-measures['reference']['baseline'])<0.001 for value in measures.values()), 'Description baseline did not survive edit/reopen'
        if args.check_origin:
            report['horizontal_origins_checked']=True
            assert all(abs(value['horizontal_origin']-measures['reference']['horizontal_origin'])<0.001 for value in measures.values()), 'Horizontal origin did not survive edit/reopen'
        for name in ['native-from-reader','native-after-reader','native-from-reader-marker','native-after-reader-marker']:
            assert any(font.startswith('/MPMB') for font in measures[name]['font_names']), 'Expected a newly projected native appearance, not retained Reader AP'
        report['passed']=True
    except Exception as error:
        report['error']=str(error)
        if opened:
            try:
                shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
            except Exception as diagnostic:report['diagnostic_error']=str(diagnostic)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    if pending:
                        try:report['cleanup_result']=c.script_result(pending,timeout=90)
                        except Exception as error:report['cleanup_result_error']=str(error)
                    retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
            except Exception as error:report['cleanup_error']=str(error)
        (folder/'roundtrip.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'roundtrip.json',flush=True)


if __name__=='__main__':main()
