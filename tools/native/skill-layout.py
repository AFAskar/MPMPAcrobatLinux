#!/usr/bin/env python3
"""Compare rich skill-label baselines with preserved original Reader appearances.

Original reference bytes are read only. Native copies are generated, rendered,
and checked for every skill-label widget, including companion templates/pages.
"""
import hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
from pypdf import PdfReader
from pypdf.generic import ContentStream
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields,script_hashes


def appearances(reader,name):
    field=reader.get_object(canonical_fields(reader)[name]['reference'])
    return [obj.get_object() for obj in field.get('/Kids',[field.indirect_reference]) if obj.get_object().get('/Subtype')=='/Widget']


def label_lines(reader,widget):
    appearance=widget['/AP']['/N'].get_object();fonts=appearance['/Resources']['/Font'];groups={};x=y=0.;font=None;leading=0.
    def decoded(value):
        raw=value.original_bytes if hasattr(value,'original_bytes') else bytes(value)
        return raw.decode('utf-16-be') if fonts[font].get('/Encoding')=='/Identity-H' else raw.decode('cp1252')
    for args,op in ContentStream(appearance,reader).operations:
        if op==b'BT':x=y=0.
        elif op==b'Tf':font=args[0]
        elif op==b'Tm':x,y=float(args[4]),float(args[5])
        elif op in [b'Td',b'TD']:
            x+=float(args[0]);y+=float(args[1])
            if op==b'TD':leading=-float(args[1])
        elif op==b'TL':leading=float(args[0])
        elif op==b'T*':y-=leading
        elif op in [b'Tj',b'TJ']:
            text=decoded(args[0]) if op==b'Tj' else ''.join(decoded(v) for v in args[0] if hasattr(v,'original_bytes') or isinstance(v,bytes))
            groups.setdefault(round(y,3),[]).append((x,text))
    return [{'y':y,'text':''.join(t for _,t in sorted(parts)).strip()} for y,parts in sorted(groups.items(),reverse=True) if ''.join(t for _,t in parts).strip()]



def face_bytes(reader,widget):
    appearance=widget['/AP']['/N'].get_object()
    name=next(args[0] for args,op in ContentStream(appearance,reader).operations if op==b'Tf')
    font=appearance['/Resources']['/Font'][name]
    if font['/Subtype']=='/Type0':font=font['/DescendantFonts'][0].get_object()
    return font['/FontDescriptor']['/FontFile2'].get_data()


def main():
    folder=ROOT/'output/testing'/('native-skill-layout-'+str(time.time_ns()));folder.mkdir();binary=folder/'mpmb-reader';shutil.copy2(ROOT/'target/debug/mpmb-reader',binary)
    report={'passed':False,'scope':__doc__,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':[]};print(folder,flush=True)
    try:
        for fixture,pattern in [('2014','*_2014_*.pdf'),('2024','*_2024_*.pdf'),('ashnar','Ashnar*.pdf')]:
            source=next((ROOT/'Testing').glob(pattern));original_hash=hashlib.sha256(source.read_bytes()).hexdigest();output=folder/(fixture+'-saved.pdf');scenario=folder/(fixture+'-scenario.json');evidence=folder/(fixture+'-report.json')
            steps=[{'op':'advance','ms':4100},{'op':'eval','code':"var skillPrefix=DoTemplate('AScomp','Add',null,true);ApplyCompRace('wolf',skillPrefix)"},{'op':'advance','ms':1000},{'op':'save','path':str(output)}]
            scenario.write_text(json.dumps({'dialogs':[{'result':'ok'}]*30,'alerts':[1]*30,'steps':steps}))
            with (folder/(fixture+'.log')).open('w') as log:proc=subprocess.run([str(binary),str(source),'--probe',str(scenario),str(evidence)],stdout=log,stderr=log,timeout=300)
            data=json.loads(evidence.read_text());assert proc.returncode==0 and data['passed'],data.get('error')
            reference=PdfReader(source);reference_widget=appearances(reference,'Text.SkillsNames')[0];expected=label_lines(reference,reference_widget);assert len(expected)==18,expected
            original_face=hashlib.sha256(face_bytes(reference,reference_widget)).hexdigest()
            saved=PdfReader(output);fields=canonical_fields(saved);checks=[]
            active_widgets={a.idnum for page in saved.pages for a in page.get('/Annots',[])}
            for name in [n for n in fields if n.endswith('Text.SkillsNames')]:
                for index,widget in enumerate(appearances(saved,name)):
                    # Inactive template appearances are preserved, not regenerated.
                    if widget.indirect_reference.idnum not in active_widgets:continue
                    actual=label_lines(saved,widget)
                    assert hashlib.sha256(face_bytes(saved,widget)).hexdigest()==original_face, 'Original skill-label font was substituted'
                    normalized=lambda t:' '.join(t.split())
                    assert len(actual)==18,{'field':name,'lines':actual}
                    for got,want in zip(actual,expected):
                        assert normalized(got['text'])==normalized(want['text']),{'field':name,'native':got,'reference':want}
                        assert abs(got['y']-want['y'])<.25,{'field':name,'native':got,'reference':want}
                    checks.append({'field':name,'widget':index,'max_baseline_delta':max(abs(a['y']-b['y']) for a,b in zip(actual,expected))})
            assert len(checks)>=2,checks
            assert script_hashes(output)==script_hashes(source)
            # Render the actual generated companion page through independent Poppler.
            # Template insertion can precede hidden/reference pages; locate its field.
            generated=next(n for n in fields if n.endswith('Comp.Race') and n.startswith('P') and str(fields[n].get('/V','')).lower()=='wolf')
            prefix=generated[:-len('Comp.Race')]
            if fixture=='2024':
                ac=prefix+'Comp.Use.AC';assert str(fields[ac].get('/V',''))=='10+Dex'
                assert [line['text'] for line in label_lines(saved,appearances(saved,ac)[0])]==['12'], 'Numeric Format result must appear while preserving the canonical AC formula'
            target=appearances(saved,generated)[0];target_page=target.get('/P')
            page_index=next(i for i,p in enumerate(saved.pages) if p.indirect_reference==target_page)
            subprocess.run(['pdftoppm','-f',str(page_index+1),'-l',str(page_index+1),'-singlefile','-scale-to','1400','-png',str(output),str(folder/(fixture+'-companion'))],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
            report['cases'].append({'fixture':fixture,'passed':True,'output':str(output),'original_baselines':expected,'widgets':checks,'companion_page':page_index+1})
            (folder/'skill-layout.json').write_text(json.dumps(report,indent=2));print(fixture,'Reader-reference skill labels/baselines PASS',flush=True)
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:(folder/'skill-layout.json').write_text(json.dumps(report,indent=2));print(folder/'skill-layout.json',flush=True)

if __name__=='__main__':main()
