#!/usr/bin/env python3
"""Read-only PDF evidence. Never use this module to write reference PDFs."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from pypdf import PdfReader,PageObject
from pypdf.generic import NameObject,create_string_object

def field_text(value):
    """Acrobat can store large text-field values in compressed indirect streams."""
    value=value.get_object() if hasattr(value,'get_object') else value
    if hasattr(value,'get_data'):
        data=value.get_data()
        if data.startswith((b'\xfe\xff',b'\xff\xfe')):return data.decode('utf-16')
        try:return data.decode('utf-8-sig')
        except UnicodeDecodeError:return str(create_string_object(data))
    return str(value)

def canonical_fields(reader):
    """Use PDF /T hierarchy. pypdf get_fields prefers /TM export mapping names."""
    found={};seen=set()
    def walk(ref,prefix='',inherited=None):
        obj=ref.get_object();identity=(getattr(ref,'idnum',None),getattr(ref,'generation',None))
        if identity[0] is not None:
            if identity in seen:return
            seen.add(identity)
        inherited=inherited or {};partial=str(obj.get('/T',''))
        name=prefix+('.' if prefix and partial else '')+partial
        effective={**inherited,**{k:obj[k] for k in ['/FT','/V'] if k in obj}}
        kids=obj.get('/Kids',[]);named_kids=[x for x in kids if x.get_object().get('/T') is not None]
        if name and partial and not named_kids:
            value={'/V':field_text(effective.get('/V','')),'/FT':effective.get('/FT'),'reference':identity[0]}
            if name in found and str(found[name].get('/V',''))!=str(value['/V']):
                raise ValueError('Conflicting canonical fields: '+name)
            found[name]=value
        for child in named_kids:walk(child,name,effective)
    form=reader.trailer['/Root'].get('/AcroForm')
    if form:
        for ref in form.get_object().get('/Fields',[]):walk(ref)
    return found

def script_hashes(path):
    r=PdfReader(path);tree=r.trailer['/Root'].get('/Names',{}).get('/JavaScript');out={}
    def walk(ref):
        node=ref.get_object();names=node.get('/Names',[])
        for i in range(0,len(names),2):
            js=names[i+1].get_object().get('/JS','');js=js.get_object() if hasattr(js,'get_object') else js
            data=js.get_data() if hasattr(js,'get_data') else str(js).encode('utf8')
            out[str(names[i])]=hashlib.sha256(data).hexdigest()
        for child in node.get('/Kids',[]):walk(child)
    if tree:walk(tree)
    return out

def inspect(path, expected=None):
    path=Path(path);reader=PdfReader(path);fields=canonical_fields(reader);expected=expected or {}
    actual={k:str(fields[k].get('/V','')) if k in fields else None for k in expected}
    widgets=[]
    for page_index,page in enumerate(reader.pages):
        for ref in page.get('/Annots',[]):
            obj=ref.get_object()
            if obj.get('/Subtype')!='/Widget':continue
            chain=[obj];parent=obj.get('/Parent')
            while parent:
                node=parent.get_object();chain.append(node);parent=node.get('/Parent')
            name='.'.join(str(n['/T']) for n in reversed(chain) if n.get('/T'))
            if name not in expected:continue
            value=field_text(next((n.get('/V') for n in chain if '/V' in n),''))
            normal=obj.get('/AP',{}).get('/N')
            visible=not (int(obj.get('/F',0)) & (2|32))
            appearance_text=None;appearance_matches=None
            if normal is not None and hasattr(normal.get_object(),'get_data'):
                stream=normal.get_object();temporary=PageObject.create_blank_page(width=500,height=500)
                temporary[NameObject('/Resources')]=stream.get('/Resources',page.get('/Resources'))
                temporary[NameObject('/Contents')]=stream
                appearance_text=temporary.extract_text().strip()
                canonical=lambda v:' '.join(unicodedata.normalize('NFKC',str(v)).split())
                shown=canonical(appearance_text);wanted=canonical(expected[name])
                appearance_matches=shown==wanted
                if re.fullmatch(r'[+-]?\d+',shown) and re.fullmatch(r'[+-]?\d+',wanted):appearance_matches=int(shown)==int(wanted)
                if chain[-1].get('/FT',obj.get('/FT'))=='/Ch':appearance_matches=shown.casefold()==wanted.casefold()
                if name=='Class and Levels':appearance_matches=re.sub(r'[^A-Za-z]','',shown)==re.sub(r'[^A-Za-z]','',wanted)
            widgets.append(dict(name=name,page=page_index+1,value=str(value),matches=str(value)==str(expected[name]),appearance=normal is not None,visible=visible,appearance_text=appearance_text,appearance_matches=appearance_matches))
    represented={w['name'] for w in widgets}
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pages=len(reader.pages),field_count=len(fields),expected=expected,actual=actual,widgets=widgets,passed=all(actual[k]==str(v) for k,v in expected.items()) and represented==set(expected) and all(w['matches'] and (not w['visible'] or str(expected[w['name']])=='' or (w['appearance'] and w['appearance_matches'])) for w in widgets))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('pdf');p.add_argument('--expected',default='{}');a=p.parse_args()
    r=inspect(a.pdf,json.loads(a.expected));print(json.dumps(r,indent=2));raise SystemExit(0 if r['passed'] else 1)
