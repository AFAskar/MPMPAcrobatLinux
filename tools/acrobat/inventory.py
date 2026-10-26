#!/usr/bin/env python3
"""Extract embedded document JavaScript and field inventory without modifying PDFs."""
import hashlib
import json
import re
from pathlib import Path
from pypdf import PdfReader
import control as c
from verify import canonical_fields

def walk_names(node):
    node=node.get_object()
    names=node.get('/Names',[])
    for i in range(0,len(names),2):yield str(names[i]),names[i+1].get_object()
    for child in node.get('/Kids',[]):yield from walk_names(child)

def main():
    out=c.STATE/'inventory';out.mkdir(parents=True,exist_ok=True);manifest=[]
    for item in json.loads((c.REPO/'docs/fixtures.json').read_text()):
        source=c.REPO/'Testing'/item['file'];r=PdfReader(source);fields=canonical_fields(r);stem='ashnar' if 'Ashnar' in source.name else ('2014' if '_2014_' in source.name else '2024');folder=out/stem;folder.mkdir(exist_ok=True)
        scripts=[];tree=r.trailer['/Root'].get('/Names',{}).get('/JavaScript')
        if tree:
            for index,(name,action) in enumerate(walk_names(tree)):
                js=action.get('/JS','');js=js.get_object() if hasattr(js,'get_object') else js
                data=js.get_data() if hasattr(js,'get_data') else str(js).encode()
                filename=f'{index:03d}-'+re.sub(r'[^a-zA-Z0-9_.-]','_',name)+'.js'
                if data[:2] in [b'\xff\xfe',b'\xfe\xff']:text=data.decode('utf-16')
                else:
                    try:text=data.decode('utf8')
                    except UnicodeDecodeError:text=data.decode('cp1252')
                (folder/filename).write_text(text,encoding='utf8')
                scripts.append(dict(name=name,file=filename,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        (folder/'fields.json').write_text(json.dumps({k:dict(type=str(v.get('/FT','')),value=str(v.get('/V',''))) for k,v in fields.items()},indent=2))
        manifest.append(dict(fixture=stem,pdf_sha256=item['sha256'],pages=len(r.pages),fields=len(fields),scripts=scripts))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2));print(out/'manifest.json')
if __name__=='__main__':main()
