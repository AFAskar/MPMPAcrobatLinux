#!/usr/bin/env python3
"""Render saved readiness evidence with Poppler for visual review."""
import json
from pathlib import Path
import subprocess
import sys
from PIL import Image,ImageDraw
from pypdf import PdfReader
import control as c

def main(report):
    report=Path(report);data=json.loads(report.read_text());folder=c.STATE/('render-'+report.stem);folder.mkdir(exist_ok=True)
    panels=[]
    for case in data['cases']:
        pdf=case.get('detail',{}).get('pdf')
        if not pdf:continue
        pages={1:'front'}
        for widget in pdf['widgets']:
            if '.Comp.' in widget['name'] or '.Wildshape.' in widget['name']:pages[widget['page']]='generated'
        if case['name'].startswith('ashnar') or 'spell-generation' in case['name']:
            reader=PdfReader(pdf['path'])
            for index,page in enumerate(reader.pages,1):
                for ref in page.get('/Annots',[]):
                    obj=ref.get_object();parts=[]
                    while obj:
                        if obj.get('/T'):parts.insert(0,str(obj['/T']))
                        parent=obj.get('/Parent');obj=parent.get_object() if parent else None
                    if '.spells.name.' in '.'.join(parts):pages[index]='spells';break
        for page,label in sorted(pages.items()):
            prefix=folder/(case['name']+'-'+label)
            subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-scale-to','1100','-singlefile','-png',pdf['path'],str(prefix)],check=True,capture_output=True)
            im=Image.open(str(prefix)+'.png').convert('RGB');im=im.crop((0,0,im.width,min(650,im.height)))
            tile=Image.new('RGB',(820,700),'white');tile.paste(im,(0,35));ImageDraw.Draw(tile).text((8,8),case['name']+' / '+label,fill='black');panels.append(tile)
    canvas=Image.new('RGB',(1640,700*((len(panels)+1)//2)),(225,225,225))
    for i,panel in enumerate(panels):canvas.paste(panel,((i%2)*820,(i//2)*700))
    output=folder/'contact.png';canvas.save(output);print(output)
if __name__=='__main__':main(sys.argv[1])
