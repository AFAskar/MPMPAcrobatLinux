#!/usr/bin/env python3
"""Compare selected API values with raw PDF values using explicit field types.

Only checkbox/radio export-name representation and empty/absent Off have a
logical conversion. Text fields remain exact. Raw expectations are never written.
"""
from pypdf import PdfReader
from pypdf.generic import NameObject
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'acrobat'))
from verify import canonical_fields,inspect

def compare(path,api):
 reader=PdfReader(path);fields=canonical_fields(reader);raw={};rules=[]
 for name,expected in api.items():
  item=fields[name];value=item['/V'];node=reader.get_object(item['reference']);flags=int(node.get('/Ff',0));literal=node.get('/V');logical=value
  if item['/FT']=='/Btn' and not flags&65536:
   if isinstance(literal,NameObject):logical=str(literal)[1:]
   elif value=='':logical='Off'
   if logical!=value:rules.append({'field':name,'api':expected,'raw':value,'logical':logical,'V_present':'/V' in node,'rule':'button export name or empty/absent Off'})
  assert logical==expected,('API/raw field mismatch',name,expected,logical)
  raw[name]=value
 checked=inspect(path,raw);assert checked['actual']==raw and checked['widgets'] and all(w['matches'] for w in checked['widgets'])
 return {'logical_api_equal':True,'raw_expected':raw,'representation_rules':rules,'independent':checked}
