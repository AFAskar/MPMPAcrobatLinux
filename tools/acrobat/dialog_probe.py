#!/usr/bin/env python3
"""Inspect a real MPMB class-selection dialog, then cancel without creating a character."""
import json
import time
import control as c

def probe(path):
    c.ensure_document(path)
    before=c.script('read',path=path,fields=['Class and Levels'])
    ident=c.script_submit('call',path=path,name='SelectClass',args=[])
    deadline=time.monotonic()+20
    while True:
        elements=c.command('inspect')
        names=[e['name'] for e in elements if e['name']]
        if any('CLASS SELECTION' in n.upper() for n in names):break
        if time.monotonic()>deadline:raise RuntimeError('Class dialog did not appear: '+json.dumps(names))
    c.command('invoke',name='Cancel')
    result=c.script_result(ident)
    after=c.script('read',path=path,fields=['Class and Levels'])
    assert before['fields']==after['fields'],'Cancel changed character class'
    return dict(dialog_names=names,result=result,cancel_preserved_class=True)

if __name__=='__main__':
    import sys
    with c.desktop_lock():
        result=probe(c.remote_path(sys.argv[1]));(c.STATE/'class-dialog.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
