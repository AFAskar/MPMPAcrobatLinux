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

def class_and_levels_tokens(value):
    """Preserve every class word and level number while allowing formatting punctuation/spacing."""
    return re.findall(r'[A-Za-z]+|\d+', unicodedata.normalize('NFKC', str(value or '')))


def inspect(path, expected=None):
    path=Path(path);reader=PdfReader(path);fields=canonical_fields(reader);expected=expected or {}
    actual={k:str(fields[k].get('/V','')) if k in fields else None for k in expected}
    widgets=[]
    pages=[(index+1,page,None) for index,page in enumerate(reader.pages)]
    active_ids={page.indirect_reference.idnum for page in reader.pages if page.indirect_reference}
    names=reader.trailer['/Root'].get('/Names',{})
    names=names.get_object() if hasattr(names,'get_object') else names
    seen_templates=set()
    def templates(ref,depth=0):
        if depth>64:raise ValueError('Template name tree depth limit')
        node=ref.get_object();entries=node.get('/Names',[])
        for index in range(0,len(entries),2):
            ref=entries[index+1];page=ref.get_object();identity=getattr(ref,'idnum',None)
            if identity not in active_ids and identity not in seen_templates:
                seen_templates.add(identity);pages.append((None,page,str(entries[index])))
        for child in node.get('/Kids',[]):templates(child,depth+1)
    if names.get('/Templates'):templates(names['/Templates'])
    for page_number,page,template in pages:
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
            visible=template is None and not (int(obj.get('/F',0)) & (2|32))
            appearance_text=None;appearance_matches=None
            if normal is not None and hasattr(normal.get_object(),'get_data'):
                stream=normal.get_object();temporary=PageObject.create_blank_page(width=500,height=500)
                temporary[NameObject('/Resources')]=stream.get('/Resources',page.get('/Resources'))
                temporary[NameObject('/Contents')]=stream
                appearance_text=temporary.extract_text().strip()
                canonical=lambda v:' '.join(unicodedata.normalize('NFKC',str(v)).split())
                shown=canonical(appearance_text);wanted=canonical(expected[name])
                field_type=next((n['/FT'] for n in chain if '/FT' in n),None)
                if field_type=='/Ch':
                    # /V stores the export value; appearances show the /Opt
                    # label. MPMB stores "short rest" while displaying "SR".
                    options=next((n['/Opt'] for n in chain if '/Opt' in n),[])
                    options=options.get_object() if hasattr(options,'get_object') else options
                    for option in options:
                        option=option.get_object() if hasattr(option,'get_object') else option
                        if isinstance(option,list) and len(option)==2 and field_text(option[0])==str(expected[name]):
                            wanted=canonical(field_text(option[1]));break
                appearance_matches=shown==wanted
                if re.fullmatch(r'[+-]?\d+',shown) and re.fullmatch(r'[+-]?\d+',wanted):appearance_matches=int(shown)==int(wanted)
                if field_type=='/Ch':appearance_matches=shown.casefold()==wanted.casefold()
                if name=='Class and Levels':appearance_matches=class_and_levels_tokens(shown)==class_and_levels_tokens(wanted)
            widgets.append(dict(name=name,page=page_number,template=template,value=str(value),matches=str(value)==str(expected[name]),appearance=normal is not None,visible=visible,appearance_text=appearance_text,appearance_matches=appearance_matches))
    represented={w['name'] for w in widgets}
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pages=len(reader.pages),field_count=len(fields),expected=expected,actual=actual,widgets=widgets,passed=all(actual[k]==str(v) for k,v in expected.items()) and represented==set(expected) and all(w['matches'] and (not w['visible'] or str(expected[w['name']])=='' or (w['appearance'] and w['appearance_matches'])) for w in widgets))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('pdf');p.add_argument('--expected',default='{}');a=p.parse_args()
    r=inspect(a.pdf,json.loads(a.expected));print(json.dumps(r,indent=2));raise SystemExit(0 if r['passed'] else 1)
