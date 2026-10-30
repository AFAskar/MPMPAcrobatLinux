#!/usr/bin/env python3
"""Measure first rich baselines in six isolated original text fields.

Field K/V/F actions are cleared deliberately to isolate host layout. This is
not an original class workflow or complete appearance qualification. Reader
outputs are authored by Reader and inspected read-only on Linux.
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
from pypdf import PdfReader
from pypdf.generic import ContentStream
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import canonical_fields, script_hashes
spec = importlib.util.spec_from_file_location('styles', ROOT / 'tools/native/default-style-persistence.py')
style = importlib.util.module_from_spec(spec)
spec.loader.exec_module(style)
CASES = [
    {'field':'Extra.Notes','size':7,'spacing':11},
    {'field':'Class Features','size':7,'spacing':14},
    {'field':'Background Feature Description','size':9,'spacing':11},
    {'field':'Background_Appearance','size':9,'spacing':14},
    {'field':'Bond','size':7,'spacing':None},
    {'field':'Racial Traits','size':9,'spacing':None},
]
ADDON = "var iFileName='Rich baseline measurement.js';(function(d){var cases=" + json.dumps(CASES) + r""";var rows=[];
 function read(f,k){try{var v=f[k];return v===undefined?{undefined_value:true}:JSON.parse(JSON.stringify(v))}catch(e){return {getter_error:String(e)}}}
 cases.forEach(function(item,i){var f=d.getField(item.field);f.setAction('Keystroke','');f.setAction('Validate','');f.setAction('Format','');f.richText=true;f.multiline=true;
  var span={text:'Baseline '+i,fontFamily:['Segoe UI'],fontWeight:400,fontStyle:'normal',textColor:['RGB',0,0,0],textSize:item.size,alignment:'left'};if(item.spacing!==null)span.linespacing=item.spacing;f.richValue=[span];
  rows.push({field:item.field,value:read(f,'valueAsString'),spans:read(f,'richValue')});
 });var result={rows:rows,sentinel:'\u00a0\u2028\ud83d\ude00'};
 Value('PC Name',JSON.stringify(result).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""


def baselines(path, captured, cases):
    reader = PdfReader(path)
    fields = canonical_fields(reader)
    pages = {ref.idnum:number for number,page in enumerate(reader.pages) for ref in page.get('/Annots',[])}
    rows = []
    expected = {row["field"]:row["value"] for row in captured["rows"]}
    for case in cases:
        assert fields[case["field"]]["/V"] == expected[case["field"]], "Saved canonical text changed"
        field = reader.get_object(fields[case['field']]['reference'])
        widgets = [ref.get_object() for ref in field.get('/Kids',[field]) if ref.get_object().indirect_reference.idnum in pages]
        assert widgets, case
        for widget in widgets:
            ap = widget['/AP']['/N'].get_object()
            x, y, font_size = 0., 0., None
            first = None
            positions = []
            drawing = []
            leading = 0.
            for args, op in ContentStream(ap, reader).operations:
                if op in [b'w',b'm',b'l',b'S',b's',b'f',b'f*']:
                    drawing.append({'operator':op.decode(),'operands':[str(value) for value in args]})
                if op == b'Tf':
                    font_size = float(args[1])
                elif op == b'Tm':
                    assert list(map(float,args[:4])) == [1.,0.,0.,1.], 'Unsupported diagnostic text transform'
                    x,y = map(float,args[4:])
                elif op in [b'Td',b'TD']:
                    x += float(args[0]); y += float(args[1])
                    if op == b'TD':leading=-float(args[1])
                elif op == b'TL':
                    leading = float(args[0])
                elif op == b'T*':
                    y -= leading
                elif op in [b'Tj',b'TJ']:
                    position = {'x':x,'y':y,'size':font_size}
                    if first is None:first = position
                    if not positions or abs(positions[-1]['y']-y)>.001:positions.append(position)
                elif op == b'cm':
                    assert list(map(float,args)) == [1.,0.,0.,1.,0.,0.], 'Unsupported diagnostic graphics transform'
            assert first, case
            height = float(ap['/BBox'][3]) - float(ap['/BBox'][1])
            rows.append(dict(case, page=pages[widget.indirect_reference.idnum], height=height, baseline=first, top_offset=height-first['y'], positions=positions, line_offsets=[height-position['y'] for position in positions], drawing=drawing, fonts={key:str(value.get_object().get('/BaseFont')) for key,value in ap['/Resources']['/Font'].items()}))
    return rows


def verified_reference(path, source, cases, addon_sha):
    reference=json.loads(path.read_text())
    assert reference['execution_completed'] and reference.get('reader_request')
    assert reference['addon_sha256']==addon_sha
    readiness=json.loads(Path(reference['readiness']).read_text())
    assert readiness['passed'] and len(readiness['cases'])==24
    pdf=Path(reference['pdf']);assert pdf.resolve().is_relative_to(ROOT/'output/testing')
    before=hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert script_hashes(pdf)==script_hashes(source)
    raw=canonical_fields(PdfReader(pdf))['PC Name']['/V'];assert raw.isascii()
    a,b=1,0
    for ch in raw:a=(a+ord(ch))%65521;b=(b+a)%65521
    assert reference['reader_summary']=={'code_units':len(raw),'adler32_utf16':str((b*65536+a)&0xffffffff)}
    captured=json.loads(raw)
    assert captured==reference['captured']
    assert [ord(ch) for ch in captured['sentinel']]==[160,8232,128512]
    actual=baselines(pdf,captured,cases)
    assert len(actual)==len(reference['baselines'])
    # Early diagnostics recorded only the first baseline. Independently derive
    # all positions from the PDF; every previously recorded key remains strict.
    for decoded,reported in zip(actual,reference['baselines']):
        assert all(decoded.get(key)==value for key,value in reported.items()), 'Reference baseline JSON differs from saved Reader PDF'
    assert hashlib.sha256(pdf.read_bytes()).hexdigest()==before
    return reference,actual,before


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-only',action='store_true')
    parser.add_argument('--readiness',type=Path)
    parser.add_argument('--reference',type=Path)
    parser.add_argument('--two-lines',action='store_true')
    parser.add_argument('--mixed-sizes',action='store_true',help='Use size7/9 on successive lines')
    parser.add_argument('--font-profile',action='store_true',help='Use six bundled faces with default line spacing')
    parser.add_argument('--fractional-sizes',action='store_true',help='Measure fractional span sizes and short leading')
    parser.add_argument('--decorations',action='store_true',help='Measure underline and strike at three sizes and four font faces')
    parser.add_argument('--inline-sizes',action='store_true',help='Measure two different sizes within the first rich line')
    parser.add_argument('--leading-threshold',action='store_true',help='With inline sizes, measure leading around the largest run size')
    parser.add_argument('--fixture',choices=['2014','2024','ashnar'],default='2024')
    args = parser.parse_args()
    assert not (args.decorations and args.reference), 'Decoration profiles are measurements; baseline-only comparison cannot qualify their drawing paths'
    assert not args.leading_threshold or args.inline_sizes, 'Leading-threshold measurement requires inline sizes'
    if not args.native_only:
        assert args.readiness
        ready = json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases']) == 24
    folder = ROOT/'output/testing'/('rich-baseline-'+str(time.time_ns()));folder.mkdir()
    source = next((ROOT/'Testing').glob({'2014':'*_2014_*.pdf','2024':'*_2024_*.pdf','ashnar':'Ashnar*.pdf'}[args.fixture]))
    cases = [dict(case) for case in CASES]
    if args.fixture == 'ashnar':
        # This character has no active background page; Flaw offers an active
        # multiline rich field for the same size/spacing case.
        cases[3]['field'] = 'Flaw'
    if args.fractional_sizes:
        cases = [dict(case,size=size,spacing=spacing) for case,size,spacing in zip(cases,[7.25,7.9,8.05,8.5,8.9,9.5],[7.25,7.25,7.25,11.5,14.75,None])]
    if args.decorations:
        cases = [dict(case,size=size,weight=weight,style=font_style) for case,size,weight,font_style in zip(cases,[7,9,12,7,9,12],[400,400,400,700,400,700],['normal','normal','normal','normal','italic','italic'])]
    if args.inline_sizes:
        cases = [dict(case,size=size,next_size=next_size,spacing=spacing) for case,size,next_size,spacing in zip(cases,[7,7,7,9,9,9],[8,8,8,7,7,7],[7.25,11,None,7.25,14,None])]
    if args.leading_threshold:
        cases = [dict(case,size=7,next_size=8,spacing=spacing) for case,spacing in zip(cases,[7.9,8,8.1,8.9,9,9.1])]
    if args.font_profile:
        cases = [dict(case,font=font,spacing=None) for case,font in zip(cases,['Segoe UI','ScalaSans','SegoePrint','SegoeScript','Pterra','RavennaJW'])]
    addon = ADDON.replace(json.dumps(CASES),json.dumps(cases))
    if args.font_profile:
        addon = addon.replace("fontFamily:['Segoe UI']", "fontFamily:[item.font]")
    if args.decorations:
        addon = addon.replace("fontWeight:400,fontStyle:'normal'", "fontWeight:item.weight,fontStyle:item.style,underline:true,strikethrough:true")
    if args.two_lines:
        addon = addon.replace("text:'Baseline '+i,", "text:'Baseline '+i+String.fromCharCode(13)+'Next',")
    if args.mixed_sizes:
        addon = addon.replace("f.richValue=[span];", "span.text='Baseline '+i+String.fromCharCode(13);var next=JSON.parse(JSON.stringify(span));next.text='Next';next.textSize=item.size===7?9:7;f.richValue=[span,next];")
    if args.inline_sizes:
        addon = addon.replace("f.richValue=[span];", "var next=JSON.parse(JSON.stringify(span));next.text=' Next';next.textSize=item.next_size;f.richValue=[span,next];")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    binary = folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
    report = {'passed':None,'scope':__doc__,'readiness':str(args.readiness),'addon_sha256':hashlib.sha256(addon.encode()).hexdigest(),'fixture':args.fixture,'two_lines':args.two_lines,'mixed_sizes':args.mixed_sizes,'font_profile':args.font_profile,'fractional_sizes':args.fractional_sizes,'decorations':args.decorations,'inline_sizes':args.inline_sizes,'leading_threshold':args.leading_threshold,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    print(folder,flush=True)
    try:
        reference=None
        if args.reference:
            reference,reference_baselines,reference_pdf_hash=verified_reference(args.reference,source,cases,report['addon_sha256'])
            report['reference']=str(args.reference.resolve())
            report['reader_pdf_sha256']=reference_pdf_hash
        if args.native_only:
            local = folder/'native.pdf'
            data = style.p.probe(binary,source,folder,'native',[
                {'op':'eval','code':"getField('User Script').value="+json.dumps(addon)},
                {'op':'eval','code':"__host.command('RunUserScript(false)')"},
                {'op':'eval','code':"JSON.parse(What('PC Name'))"},
                {'op':'save','path':str(local)}])
            captured = data['stages'][-2]['result']
        else:
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
                remote=c.remote_path('runs/rich-baseline-'+str(time.time_ns())+'.pdf');report['reader_path']=remote
                fixture = 'ashnar.pdf' if args.fixture=='ashnar' else 'blank-'+args.fixture+'.pdf'
                c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/'+fixture))+' '+c.literal(remote)+' -Force;(Get-Item '+c.literal(remote)+').IsReadOnly=$false')
                c.script('set',path=remote,values={'User Script':addon})
                request=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);report['reader_request']=request
                c.script_result(request,timeout=180)
                summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];report['reader_summary']=summary
                c.script('set',path=remote,values={'User Script':''})
                saved=remote[:-4]+'-saved.pdf';c.script('save',path=remote,output=saved);c.script('close',path=saved)
                local=c.fetch(saved,folder/'reader.pdf')
                captured=style.saved_capture(local,summary,source)
                # saved_capture validates/removes the sentinel.
                captured['sentinel']='\u00a0\u2028\U0001f600'
        report['captured']=captured
        assert [ord(ch) for ch in captured['sentinel']]==[160,8232,128512]
        assert script_hashes(local)==script_hashes(source)
        report['pdf']=str(local);report['baselines']=baselines(local,captured,cases)
        assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
        if args.reference:
            assert reference is not None
            report['api_equal']=captured==reference['captured']
            assert report['api_equal']
            assert len(report['baselines'])==len(reference_baselines)
            report['differences']=[]
            for native, reader in zip(report['baselines'],reference_baselines):
                assert native['field']==reader['field'] and native['page']==reader['page']
                expected_offsets=reader.get('line_offsets',[reader['top_offset']])
                actual_offsets=native['line_offsets']
                if len(actual_offsets)!=len(expected_offsets) or any(abs(a-b)>.002 for a,b in zip(actual_offsets,expected_offsets)):
                    report['differences'].append({'field':native['field'],'native_line_offsets':actual_offsets,'reader_line_offsets':expected_offsets})
            report['passed']=not report['differences']
        report['execution_completed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:
        (folder/'baselines.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'baselines.json',flush=True)
    return 0 if report['passed'] is not False else 1


if __name__=='__main__':
    raise SystemExit(main())
