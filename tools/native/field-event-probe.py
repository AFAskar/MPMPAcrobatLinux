#!/usr/bin/env python3
"""Measure setter/event semantics through MPMB's original manual add-on workflow."""
import argparse, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import canonical_fields, field_text, script_hashes

ADDON = r'''
var iFileName = "Native field event probe.js";
(function(d, originals) {
 var output=[], f=d.getField(__FIELD__), g=d.getField('Str Mod');
 var saved={value:f.valueAsString,calculate:d.calculate,appCalculate:app.calculate,delay:d.delay,richText:f.richText};
 var log="if(tDoc.__fieldProbeEvents.length<80)tDoc.__fieldProbeEvents.push({event:event.name,type:typeof event.value,value:String(event.value),willCommit:event.willCommit===undefined?'absent':event.willCommit});";
 function run(name,fn,field){d.__fieldProbeEvents=[];try{fn();var beforeCalculate=d.__fieldProbeEvents.length;d.calculateNow();output.push({name:name,beforeCalculate:beforeCalculate,richText:field.richText,multiline:field.multiline,value:field.valueAsString,valueType:typeof field.value,events:d.__fieldProbeEvents.slice()});}catch(e){output.push({name:name,error:String(e),events:d.__fieldProbeEvents.slice()});}}
 try {
  d.calculate=true;app.calculate=true;d.delay=false;
  f.setAction('Keystroke',log);f.setAction('Validate',log);f.setAction('Format',log);
  run('script setter numeric',function(){f.value=17},f);
  run('script setter unchanged',function(){f.value=17},f);
  run('text setter plain string',function(){f.value='alpha'},f);
  run('text setter numeric string',function(){f.value='18'},f);
  run('text setter LF',function(){f.value='line1\nline2'},f);
  run('text setter CRLF',function(){f.value='line1\r\nline2'},f);
  run('text setter CR',function(){f.value='line1\rline2'},f);
  run('text setter NBSP',function(){f.value='alpha\u00a0beta\r\u00a0\u00a0indented'},f);
  run('text setter tab',function(){f.value='alpha\tbeta'},f);
  run('disable richText',function(){f.richText=false},f);
  run('disable richText unchanged',function(){f.richText=false},f);
  run('plain text NBSP',function(){f.value='alpha\u00a0beta\r\u00a0\u00a0indented'},f);
  run('enable richText',function(){f.richText=true},f);
  run('enable richText unchanged',function(){f.richText=true},f);
  run('rich text NBSP',function(){f.value='alpha\u00a0beta\r\u00a0\u00a0indented'},f);
  f.richText=saved.richText;
  run('text setter array',function(){f.value=['a','b']},f);
  run('text setter object',function(){f.value={a:1}},f);
  f.setAction('Keystroke','');f.setAction('Validate','');f.setAction('Format','');f.value='7';
  f.setAction('Keystroke',log+'event.rc=!isNaN(event.value);');f.setAction('Validate',log);f.setAction('Format',log);
  run('numeric keystroke rejects undefined',function(){f.value=undefined},f);
  f.setAction('Keystroke','');f.setAction('Validate','');f.setAction('Format','');f.value='7';
  f.setAction('Validate',log+'event.rc=false;');
  run('validate rejects setter',function(){f.value=18},f);
  f.setAction('Keystroke','');f.setAction('Validate','');f.setAction('Format','');
  g.setAction('Keystroke',log+'event.rc=false;');g.setAction('Validate',log+'event.rc=false;');g.setAction('Format',log);
  g.setAction('Calculate','event.value=42;');
  run('calculated value rejection path',function(){d.calculateNow()},g);
  g.setAction('Calculate','event.target.value=43;');
  run('calculate target setter',function(){d.calculateNow()},g);
 } finally {
  for(var name in originals){var field=d.getField(name);for(var type in originals[name])field.setAction(type,originals[name][type]);}
  f.richText=saved.richText;f.value=saved.value;d.calculateNow();d.calculate=saved.calculate;app.calculate=saved.appCalculate;d.delay=saved.delay;
 }
 output.push({name:'diagnostic transport sentinel',value:'\u00a0\u2028\ud83d\ude00'});
 Value('PC Name',JSON.stringify(output).replace(/[\u007f-\uffff]/g,function(c){return "\\u"+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc, __RESTORE__);
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--readiness',type=Path);parser.add_argument('--native-only',action='store_true');parser.add_argument('--rich-data',action='store_true',help='Inspect rich spans/default styles and persist large Reader traces for independent decoding');parser.add_argument('--style-data',action='store_true',help='Also measure defaultStyle copies and field-style coupling (requires --rich-data)');parser.add_argument('--rich-events',action='store_true',help='Also measure rich event assignments/precedence and clearing (requires --rich-data)');parser.add_argument('--field',default='Player Name');parser.add_argument('--fixture',choices=['2014','2024','ashnar'],default='2024');args=parser.parse_args()
    assert not (args.style_data or args.rich_events) or args.rich_data, 'Rich style/event probes require --rich-data'
    if not args.native_only:
        assert args.readiness and json.loads(args.readiness.read_text())['passed']
    folder=ROOT/'output/testing'/('field-events-'+str(time.time_ns()));folder.mkdir()
    pattern={'2014':'*_2014_*.pdf','2024':'*_2024_*.pdf','ashnar':'Ashnar*.pdf'}[args.fixture];source=next((ROOT/'Testing').glob(pattern));binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary);reader=PdfReader(source);fields=canonical_fields(reader)
    originals={}
    for name in [args.field,'Str Mod']:
        node=reader.get_object(fields[name]['reference']);actions={};nodes=[node]+[ref.get_object() for ref in node.get('/Kids',[])]
        for obj in nodes:
            for key,action in obj.get('/AA',{}).items():
                action=action.get_object()
                if action.get('/JS') is not None and key not in actions:actions[key]=field_text(action['/JS'])
        originals[name]={trigger:actions.get(key,'') for trigger,key in [('Keystroke','/K'),('Validate','/V'),('Format','/F'),('Calculate','/C')]}
    addon=ADDON.replace('__RESTORE__',json.dumps(originals)).replace('__FIELD__',json.dumps(args.field))
    if args.rich_data:
        addon=addon.replace('value:String(event.value),willCommit:', 'value:String(event.value),richValue:(function(){try{var v=event.richValue;return v===undefined?null:JSON.parse(JSON.stringify(v))}catch(e){return {getter_error:String(e)}}})(),willCommit:')
        addon=addon.replace(' function run(', ' function optionalValue(fn){try{var v=fn();return v===undefined?null:JSON.parse(JSON.stringify(v))}catch(e){return {getter_error:String(e)}}}\n function run(')
        addon=addon.replace('richText:field.richText,', 'richValue:optionalValue(function(){return field.richValue}),defaultStyle:optionalValue(function(){return field.defaultStyle}),richText:field.richText,')
        addon=addon.replace("  run('script setter numeric'", "  run('initial rich data',function(){},f);\n  run('script setter numeric'")
        cases = r"""
  run('rich spans NBSP',function(){f.richValue=[{text:'alpha\u00a0beta',textSize:10,fontWeight:700,textColor:['RGB',0,0,1]},{text:'\r  second',fontFamily:['Helvetica','sans-serif'],textSize:8}]},f);
  run('rich getter copy',function(){var copy=f.richValue;copy[0].text='must not commit'},f);
  run('rich getter reassigned',function(){var copy=f.richValue;copy[0].text='reassigned';f.richValue=copy},f);
  run('rich spans LF',function(){f.richValue=[{text:'line1\nline2'}]},f);
  run('rich paragraph flags',function(){f.richValue=[{text:'first',endParagraph:true},{text:'second',endParagraph:true}]},f);
  run('rich empty array',function(){f.richValue=[]},f);
  run('rich empty string',function(){f.richValue=''},f);
"""
        if args.style_data:
            addon=addon.replace('richText:field.richText,', 'fieldStyle:{textSize:field.textSize,textFont:field.textFont,textColor:field.textColor,alignment:field.alignment},richText:field.richText,')
            cases += r"""
  var styleBefore={size:f.textSize,font:f.textFont,color:f.textColor,alignment:f.alignment,defaultStyle:optionalValue(function(){return f.defaultStyle})};
  run('defaultStyle getter copy',function(){var copy=f.defaultStyle;copy.textSize=99;copy.fontFamily[0]='must not commit'},f);
  run('textSize defaultStyle coupling',function(){f.textSize=9},f);
  run('textFont defaultStyle coupling',function(){f.textFont='Helvetica'},f);
  run('textColor defaultStyle coupling',function(){f.textColor=['RGB',0.25,0.5,0.75]},f);
  run('alignment defaultStyle coupling',function(){f.alignment='right'},f);
  run('defaultStyle assignment',function(){f.defaultStyle={alignment:'center',fontFamily:['Helvetica','sans-serif'],fontStretch:'normal',fontStyle:'italic',fontWeight:700,textColor:['RGB',1,0,0],textSize:11}},f);
  run('restore field style',function(){try{f.defaultStyle=styleBefore.defaultStyle}finally{f.textSize=styleBefore.size;f.textFont=styleBefore.font;f.textColor=styleBefore.color;f.alignment=styleBefore.alignment}},f);
"""
        if args.rich_events:
            cases += r"""
  f.setAction('Validate',log+"var spans=event.richValue;if(spans){spans.forEach(function(s){s.linespacing=11});event.richValue=spans;}");
  run('value NBSP with validated rich assignment',function(){f.value='alpha\u00a0beta'},f);
  run('spans NBSP with validated rich assignment',function(){f.richValue=[{text:'alpha\u00a0beta'}]},f);
  run('adjacent identical rich spans',function(){f.richValue=[{text:'first'},{text:'second'}]},f);
  run('multiline value with validated rich assignment',function(){f.value='line1\nline2'},f);
  f.setAction('Validate',log+"var spans=event.richValue;if(spans&&spans.length)spans[0].text='must not commit';");
  run('validate rich getter copy',function(){f.value='copy original'},f);
  f.setAction('Validate',log);
  run('fractional rich span color',function(){f.richValue=[{text:'color',textColor:['RGB',0.25,0.5,0.75]}]},f);
  run('MPMB skill and fractional rich colors',function(){f.richValue=[0,0.1,0.2,0.3,0.4,0.658,0.654,0.999,1].map(function(v){return {text:String(v),textColor:['RGB',v,v,v]}})},f);
  run('copied MPMB rich colors',function(){f.richValue=f.richValue},f);
  run('explicit paragraph boundary rich spans',function(){f.richValue=[{text:'first',endParagraph:true},{text:'second'}]},f);
  run('empty text rich span',function(){f.richValue=[{text:''}]},f);

  f.setAction('Validate',log+"event.richValue=[{text:'rich override',fontWeight:700}];");
  run('validate rich override',function(){f.value='plain input'},f);
  f.setAction('Validate',log+"event.richValue=[{text:'rich first'}];event.value='plain last';");
  run('validate rich then plain',function(){f.value='input'},f);
  f.setAction('Validate',log+"event.value='plain first';event.richValue=[{text:'rich last'}];");
  run('validate plain then rich',function(){f.value='input'},f);
  f.setAction('Keystroke',log+"event.richValue=[{text:'keystroke override'}];");f.setAction('Validate',log);
  run('keystroke rich override',function(){f.value='input'},f);
  run('keystroke rich override of styled input',function(){f.richValue=[{text:'styled input',fontWeight:700}]},f);
  f.setAction('Keystroke',log);f.setAction('Format',log+"event.richValue=[{text:'formatted override',fontWeight:700}];");
  run('format rich display',function(){f.value='stored original'},f);
  f.setAction('Format',log+"event.value='formatted plain';");
  run('format plain display',function(){f.value='stored second'},f);
  f.setAction('Format',log);f.value='clear test';d.calculateNow();
  run('rich clear nonempty with string',function(){f.richValue=''},f);
  run('rich set nonempty string',function(){f.richValue='typed rich'},f);
  f.value='style content';d.calculateNow();var textStyleSize=f.textSize;
  run('existing rich content textSize coupling',function(){f.textSize=9},f);f.textSize=textStyleSize;
  run('disable styled rich content',function(){f.richText=false},f);
  run('reenable styled rich content',function(){f.richText=true},f);
  f.setAction('Keystroke',log);f.setAction('Validate',log);f.setAction('Format',log);
"""
        addon=addon.replace("  f.richText=saved.richText;\n  run('text setter array'", cases+"  f.richText=saved.richText;\n  run('text setter array'")
    (folder/'probe-addon.js').write_text(addon)
    report={'passed':False,'fixture':args.fixture,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'addon_sha256':hashlib.sha256(addon.encode()).hexdigest(),'field':args.field,'rich_data':args.rich_data,'style_data':args.style_data,'rich_events':args.rich_events,'transport':'ASCII-escaped JSON with a Unicode sentinel; Reader saved diagnostic checksum verified','readiness':str(args.readiness) if args.readiness else None};print(folder,flush=True)
    try:
        spec={'dialogs':[{'result':'ok'}]*30,'alerts':[1]*30,'steps':[{'op':'advance','ms':4100},{'op':'eval','code':"getField('User Script').value="+json.dumps(addon)},{'op':'eval','code':"__host.command('RunUserScript(false)')"},{'op':'advance','ms':1000},{'op':'eval','code':"if(/[^\x00-\x7f]/.test(What('PC Name')))throw Error('Diagnostic transport must be ASCII');JSON.parse(What('PC Name'))"}]}
        scenario,evidence=folder/'native-scenario.json',folder/'native-report.json';scenario.write_text(json.dumps(spec))
        with (folder/'native.log').open('w') as log:proc=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=240)
        data=json.loads(evidence.read_text());assert proc.returncode==0 and data['passed'],data.get('error');report['native']=data['stages'][-1]['result'];assert report['native'][-1]=={'name':'diagnostic transport sentinel','value':'\u00a0\u2028\U0001f600'}
        (folder/'events.json').write_text(json.dumps(report,indent=2))
        if not args.native_only:
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Reference suite requires no pre-existing document'
                path=c.remote_path('runs/field-events-'+str(time.time_ns())+'.pdf');c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/'+('ashnar.pdf' if args.fixture=='ashnar' else 'blank-'+args.fixture+'.pdf')))+' '+c.literal(path)+' -Force;(Get-Item '+c.literal(path)+').IsReadOnly=$false')
                c.script('set',path=path,values={'User Script':addon});ident=c.script_submit('call',path=path,name='RunUserScript',args=[False]);report['reader_request']=ident;c.script_result(ident,timeout=180)
                summary=c.script('field_summary',path=path,fields=['PC Name'])['fields']['PC Name']
                saved=path[:-4]+'-saved.pdf';c.script('save',path=path,output=saved);c.script('close',path=saved)
                local=c.fetch(saved,folder/'reader-saved.pdf');assert script_hashes(local)==script_hashes(source)
                text=canonical_fields(PdfReader(local))['PC Name']['/V'];assert text.isascii(), 'Reader diagnostic transport changed encoding';units=text.encode('utf-16-le');a,b=1,0
                for i in range(0,len(units),2):
                    a=(a+int.from_bytes(units[i:i+2],'little'))%65521;b=(b+a)%65521
                assert summary=={'code_units':len(units)//2,'adler32_utf16':str((b*65536+a)&0xffffffff)},summary
                report['reader']=json.loads(text);assert report['reader'][-1]=={'name':'diagnostic transport sentinel','value':'\u00a0\u2028\U0001f600'}, 'Reader diagnostic Unicode sentinel changed';report['reader_summary']=summary;report['reader_saved']=str(local)
            report['equal']=report['native']==report['reader']
        report['execution_completed']=True
        report['passed']=bool(report.get('equal')) if not args.native_only else None
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        (folder/'events.json').write_text(json.dumps(report,indent=2));print(folder/'events.json',flush=True)

    return 0 if args.native_only or report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
