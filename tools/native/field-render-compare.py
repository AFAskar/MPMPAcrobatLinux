#!/usr/bin/env python3
"""Read-only Poppler comparison of a bounded visible field region.

Inputs must have equal canonical text and matching widget/page geometry. This
checks one cropped region, not whole documents or complete form compatibility.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from PIL import Image, ImageChops
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import canonical_fields


def region(path, field):
    reader=PdfReader(path);fields=canonical_fields(reader)
    node=reader.get_object(fields[field]['reference'])
    widgets={ref.get_object().indirect_reference.idnum:ref.get_object() for ref in node.get('/Kids',[node])}
    for number,page in enumerate(reader.pages,1):
        for ref in page.get('/Annots',[]):
            if ref.idnum in widgets:
                return fields[field]['/V'],number,list(map(float,widgets[ref.idnum]['/Rect'])),float(page.mediabox.top)
    raise AssertionError('No active widget for '+field)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native',type=Path);parser.add_argument('reader',type=Path)
    parser.add_argument('--field',required=True);parser.add_argument('--dpi',type=int,default=144)
    parser.add_argument('--height',type=float,default=45,help='Cropped height in PDF points, including padding')
    args=parser.parse_args();assert args.dpi>0 and args.height>0
    folder=ROOT/'output/testing'/('field-render-'+str(time.time_ns()));folder.mkdir()
    report={'passed':False,'scope':__doc__,'field':args.field,'dpi':args.dpi,'crop_height_points':args.height,'inputs':[]}
    try:
        results=[region(path,args.field) for path in [args.native,args.reader]]
        assert results[0][0]==results[1][0],'Canonical field text differs'
        assert results[0][1]==results[1][1],'Widget page differs'
        assert all(abs(a-b)<.01 for a,b in zip(results[0][2],results[1][2])),'Widget geometry differs'
        report['geometry_tolerance_points']=.01
        images=[]
        for label,path,data in zip(['native','reader'],[args.native,args.reader],results):
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            _,number,rect,page_top=data;left,bottom,right,top=rect;scale=args.dpi/72
            prefix=folder/label
            subprocess.run(['pdftoppm','-f',str(number),'-l',str(number),'-r',str(args.dpi),'-x',str(max(0,int((left-3)*scale))),'-y',str(max(0,int((page_top-top-3)*scale))),'-W',str(int((right-left+6)*scale)),'-H',str(int(min(args.height,top-bottom+6)*scale)),'-singlefile','-png',str(path),str(prefix)],capture_output=True,check=True)
            image=prefix.with_suffix('.png');images.append(Image.open(image).convert('RGB'))
            assert hashlib.sha256(path.read_bytes()).hexdigest()==before
            report['inputs'].append({'path':str(path.resolve()),'sha256':before,'page':number,'rect':rect,'render':str(image)})
        assert images[0].size==images[1].size
        delta=ImageChops.difference(*images)
        pixels=delta.get_flattened_data() if hasattr(delta,'get_flattened_data') else delta.getdata()
        changed=sum(1 for pixel in pixels if pixel!=(0,0,0));total=delta.width*delta.height
        report.update(passed=changed==0,changed_pixels=changed,total_pixels=total,changed_fraction=changed/total)
        delta.save(folder/'difference.png')
    except Exception as error:report['error']=str(error)
    (folder/'render.json').write_text(json.dumps(report,indent=2)+'\n')
    print(folder/'render.json',flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
