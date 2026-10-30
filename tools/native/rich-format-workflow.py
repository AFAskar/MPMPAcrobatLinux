#!/usr/bin/env python3
"""Original MPMB notes formatting: bold, italic, headings and decorations.

No field actions are replaced. Saved Reader appearances and original action
hashes are inspected on Linux; this is one notes workflow, not every class.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import time
from pathlib import Path
from pypdf import PageObject, PdfReader
from pypdf.generic import ContentStream, NameObject
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
from verify import canonical_fields, field_text, script_hashes
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py')
style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
FIELD='Extra.Notes'
TEXT='Normal **bold** *italic* _under_ ~strike~ ##both## #heading# end'
ADDON="var iFileName='Original notes formatting.js';(function(d){"+style.SAFE_READ+"var f=d.getField("+json.dumps(FIELD)+");f.value="+json.dumps(TEXT)+r""";
 var result={field:{},widgets:[],inactive:{},sentinel:'\u00a0\u2028\ud83d\ude00'};
 ['valueAsString','richValue','defaultStyle','textFont','textSize','textColor','alignment','page','rect','charsPerLine'].forEach(function(key){result.field[key]=read(f,key)});
 for(var i=0;i<12;i++){var w;try{w=d.getField(f.name+'.'+i)}catch(e){result.widget_error={index:i,error:String(e)};break}if(!w)break;var row={};['page','rect','textFont','textSize','textColor','alignment'].forEach(function(key){row[key]=read(w,key)});result.widgets.push(row);}
 ['Comp.Use.Traits','Background_Appearance'].forEach(function(name){var other=d.getField(name);result.inactive[name]=other?{page:read(other,'page'),rect:read(other,'rect')}:null;});
 Value('PC Name',JSON.stringify(result).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""


def actions(path):
    reader=PdfReader(path);node=reader.get_object(canonical_fields(reader)[FIELD]['reference']);result={}
    for key,value in node.get('/AA',{}).items():
        action=value.get_object()
        if action.get('/S')=='/JavaScript':result[str(key)]=hashlib.sha256(field_text(action['/JS']).encode()).hexdigest()
    return result


def appearances(path):
    reader=PdfReader(path);node=reader.get_object(canonical_fields(reader)[FIELD]['reference'])
    active={ref.idnum for page in reader.pages for ref in page.get('/Annots',[])};rows=[]
    for ref in node.get('/Kids',[node]):
        widget=ref.get_object()
        if widget.indirect_reference.idnum not in active:continue
        ap=widget['/AP']['/N'].get_object();fonts=ap['/Resources']['/Font']
        face=lambda name:re.sub(r'^(?:MPMB|[A-Z]{6}\+)', '',str(name).lstrip('/'))
        resources={str(key):face(value.get_object().get('/BaseFont')) for key,value in fonts.items()}
        ops=ContentStream(ap,reader).operations
        used=sorted({resources[str(args[0])] for args,op in ops if op==b'Tf'})
        page=PageObject.create_blank_page(width=500,height=500);page[NameObject('/Resources')]=ap['/Resources'];page[NameObject('/Contents')]=ap
        # Keep drawing evidence separate from text operators. Reader can use
        # filled paths instead of strokes for underline/strikethrough.
        drawing=[{'operator':op.decode(),'operands':[str(value) for value in args]} for args,op in ops if op in [b'w',b'm',b'l',b'S',b's',b'f',b'f*',b're']]
        text_ops=[{'operator':op.decode(),'operands':[str(value) for value in args]} for args,op in ops if op in [b'Tf',b'Tm',b'Td',b'TD',b'Ts',b'TL',b'T*']]
        rows.append({'fonts':used,'text':page.extract_text().strip(),'drawing':drawing,'text_positions':text_ops})
    assert rows
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native-only',action='store_true');parser.add_argument('--readiness',type=Path);parser.add_argument('--reference',type=Path);parser.add_argument('--fixture',choices=['2014','2024','ashnar'],default='2024');args=parser.parse_args()
    if not args.native_only:
        assert args.readiness
        ready=json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24
    folder=ROOT/'output/testing'/('rich-format-'+str(time.time_ns()));folder.mkdir()
    source=next((ROOT/'Testing').glob({'2014':'*_2014_*.pdf','2024':'*_2024_*.pdf','ashnar':'Ashnar*.pdf'}[args.fixture]));source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
    report={'passed':None,'scope':__doc__,'fixture':args.fixture,'addon_sha256':hashlib.sha256(ADDON.encode()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'readiness':str(args.readiness)}
    print(folder,flush=True)
    try:
        if args.native_only:
            local=folder/'native.pdf'
            data=style.p.probe(binary,source,folder,'native',[
                {'op':'eval','code':"getField('User Script').value="+json.dumps(ADDON)},
                {'op':'eval','code':"__host.command('RunUserScript(false)')"},
                {'op':'eval','code':"JSON.parse(What('PC Name'))"},
                {'op':'eval','code':"JSON.parse(__host.snapshot())["+json.dumps(FIELD)+"]"},
                {'op':'save','path':str(local)}])
            captured=data['stages'][-3]['result'];report['formatted_native']=data['stages'][-2]['result']['richValue']
        else:
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()],'Pre-existing Reader document'
                remote=c.remote_path('runs/rich-format-'+str(time.time_ns())+'.pdf');report['reader_path']=remote
                fixture='ashnar.pdf' if args.fixture=='ashnar' else 'blank-'+args.fixture+'.pdf'
                c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/'+fixture))+' '+c.literal(remote)+' -Force;(Get-Item '+c.literal(remote)+').IsReadOnly=$false')
                c.script('set',path=remote,values={'User Script':ADDON})
                request=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);report['reader_request']=request;c.script_result(request,timeout=180)
                summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['reader_summary']=summary
                c.script('set',path=remote,values={'User Script':''})
                saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);c.script('close',path=saved);local=c.fetch(saved,folder/'reader.pdf')
                captured=style.saved_capture(local,summary,source);captured['sentinel']='\u00a0\u2028\U0001f600'
        report['captured']=captured;assert [ord(ch) for ch in captured['sentinel']]==[160,8232,128512]
        assert captured['field']['valueAsString']==TEXT
        assert script_hashes(local)==script_hashes(source)
        report['actions']=actions(local);assert report['actions']==actions(source),'Original field actions changed'
        report['pdf']=str(local);report['appearances']=appearances(local)
        report['markers_removed']=all('*' not in row['text'] and '#' not in row['text'] and '_' not in row['text'] and '~' not in row['text'] for row in report['appearances'])
        assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
        if args.reference:
            ref=json.loads(args.reference.read_text());assert ref['execution_completed'] and ref['reader_request'];assert ref['addon_sha256']==report['addon_sha256'] and ref['fixture']==args.fixture
            saved=Path(ref['pdf']);raw=canonical_fields(PdfReader(saved))['PC Name']['/V'];assert raw.isascii();assert json.loads(raw)==ref['captured'];assert script_hashes(saved)==script_hashes(source);assert appearances(saved)==ref['appearances']
            report['api_equal']=captured==ref['captured']
            report['font_faces_equal']=[r['fonts'] for r in report['appearances']]==[r['fonts'] for r in ref['appearances']]
            def painted_y(rows):
                result=[]
                for row in rows:
                    y=None
                    for op in row['drawing']:
                        if op['operator']=='m':y=float(op['operands'][1])
                        elif op['operator'] in ['S','s'] and y is not None:
                            if not any(abs(y-previous)<.001 for previous in result):result.append(y)
                return sorted(result)
            expected_y,actual_y=painted_y(ref['appearances']),painted_y(report['appearances'])
            report['decoration_y']={'native':actual_y,'reader':expected_y}
            report['decoration_positions_equal']=len(actual_y)==len(expected_y) and all(abs(a-b)<.01 for a,b in zip(actual_y,expected_y))
            def first_baseline(rows):
                for row in rows:
                    x,y=0.,0.
                    for op in row['text_positions']:
                        if op['operator']=='Tm':return float(op['operands'][-1])
                        if op['operator'] in ['Td','TD']:return y+float(op['operands'][1])
                raise AssertionError('No first baseline')
            report['first_baselines']={'native':first_baseline(report['appearances']),'reader':first_baseline(ref['appearances'])}
            report['first_baseline_equal']=abs(report['first_baselines']['native']-report['first_baselines']['reader'])<.002
            report['passed']=report['api_equal'] and report['font_faces_equal'] and report['decoration_positions_equal'] and report['first_baseline_equal']
        report['execution_completed']=True
    except Exception as error:report['error']=str(error);raise
    finally:
        (folder/'formatting.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'formatting.json',flush=True)
    return 0 if report['passed'] is not False else 1


if __name__=='__main__':raise SystemExit(main())
