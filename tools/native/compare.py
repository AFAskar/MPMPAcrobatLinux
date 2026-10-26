#!/usr/bin/env python3
"""Read-only, complete field/widget/script comparison of native and Reader-saved PDFs."""
import argparse,hashlib,json,sys,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'acrobat'))
from pypdf import PdfReader
from verify import canonical_fields,script_hashes

def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def widgets(reader):
 out={}
 for page_index,page in enumerate(reader.pages):
  for ref in page.get('/Annots',[]):
   obj=ref.get_object()
   if obj.get('/Subtype')!='/Widget':continue
   chain=[obj];parent=obj.get('/Parent')
   while parent:
    node=parent.get_object();chain.append(node);parent=node.get('/Parent')
   name='.'.join(str(n['/T']) for n in reversed(chain) if n.get('/T'))
   ap=obj.get('/AP',{}).get('/N');ap=ap.get_object() if ap is not None else None
   key=f'{page_index}:{name}:{ref.idnum}'
   out[key]={'name':name,'page':page_index+1,'rect':[float(x) for x in obj.get('/Rect',[])],'flags':obj.get('/F',0),'appearance':hashlib.sha256(ap.get_data()).hexdigest() if hasattr(ap,'get_data') else ({str(k):hashlib.sha256(v.get_object().get_data()).hexdigest() for k,v in ap.items()} if hasattr(ap,'items') else None),'value_state':str(obj.get('/AS',''))}
 return out

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('native');p.add_argument('reader');p.add_argument('report');p.add_argument('--render-page',type=int);args=p.parse_args()
 a,b=PdfReader(args.native),PdfReader(args.reader);fa,fb=canonical_fields(a),canonical_fields(b);wa,wb=widgets(a),widgets(b)
 normalize=lambda s:s.replace('\r\n','\n').replace('\r','\n')
 differences=[]
 for k in sorted(set(fa)|set(fb)):
  va=normalize(str(fa.get(k,{}).get('/V','')));vb=normalize(str(fb.get(k,{}).get('/V','')))
  if k not in fa or k not in fb or va!=vb:differences.append({'field':k,'native_length':len(va),'reader_length':len(vb),'native_sha256':digest(va),'reader_sha256':digest(vb)})
 # Object IDs are not stable across writers: compare ordered widgets by page/name/rect.
 simplify=lambda items:sorted((v['page'],v['name'],v['rect'],v['flags'],v['value_state']) for v in items.values())
 out={'native':str(Path(args.native).resolve()),'reader':str(Path(args.reader).resolve()),'pages_equal':len(a.pages)==len(b.pages),'field_counts':[len(fa),len(fb)],'field_values_equal':not differences,'value_differences':differences,'widget_counts':[len(wa),len(wb)],'widget_geometry_flags_states_equal':simplify(wa)==simplify(wb),'appearance_streams':[sum(bool(x['appearance']) for x in w.values()) for w in [wa,wb]],'original_document_scripts_equal':script_hashes(args.native)==script_hashes(args.reader)}
 ordered=lambda w:sorted(w.values(),key=lambda v:(v['page'],v['name'],v['rect']))
 pairs=list(zip(ordered(wa),ordered(wb)))
 out['appearance_comparison']={'scope':'Decoded normal appearance content, including named checkbox states. Resource semantics and rendering require separate checks.','same_content':sum(x['appearance'] is not None and x['appearance']==y['appearance'] for x,y in pairs),'both_missing':sum(x['appearance'] is None and y['appearance'] is None for x,y in pairs),'different_content':sum(x['appearance']!=y['appearance'] for x,y in pairs),'missing_native':sum(x['appearance'] is None for x in wa.values()),'missing_reader':sum(x['appearance'] is None for x in wb.values())}
 out['widget_flag_differences']=[{'name':x['name'],'page':x['page'],'native':x['flags'],'reader':y['flags']} for x,y in pairs if (x['page'],x['name'],x['rect'])==(y['page'],y['name'],y['rect']) and x['flags']!=y['flags']]
 if args.render_page:
  from PIL import Image,ImageChops
  images=[]
  for label,path in [('native',args.native),('reader',args.reader)]:
   prefix=Path(args.report).with_suffix('');prefix=prefix.with_name(prefix.name+'-'+label)
   subprocess.run(['pdftoppm','-r','72','-f',str(args.render_page),'-l',str(args.render_page),'-singlefile','-png',path,str(prefix)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   images.append(Image.open(prefix.with_suffix('.png')).convert('RGB'))
  render={'page':args.render_page,'sizes':[list(i.size) for i in images],'same_size':images[0].size==images[1].size}
  if render['same_size']:
   rgb=ImageChops.difference(*images);channels=rgb.split();mask=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2]);hist=rgb.convert('L').histogram();total=images[0].width*images[0].height
   render.update(changed_pixel_fraction=1-mask.histogram()[0]/total,mean_absolute_luminance_difference=sum(i*n for i,n in enumerate(hist))/total)
  out['render_comparison']=render
 Path(args.report).write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k not in ['native','reader','value_differences']}));print('Field differences:',len(differences))
if __name__=='__main__':main()
