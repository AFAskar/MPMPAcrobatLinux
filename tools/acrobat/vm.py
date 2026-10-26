#!/usr/bin/env python3
"""Cold VM checkpoints including disk, firmware and TPM. Refuses a running VM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import control as c
NAME='mpmb-windows11'
STORE=Path.home()/'VirtualMachines'/NAME/'checkpoints'
def virsh(*args):return subprocess.check_output(['virsh','-c','qemu:///session',*args],text=True).strip()
def cold():
    if virsh('domstate',NAME)!='shut off':raise RuntimeError('VM must be shut off cleanly first')
def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    if src.is_dir():shutil.copytree(src,dst,copy_function=lambda a,b:subprocess.run(['cp','--reflink=auto','--sparse=always','--preserve=mode,timestamps',a,b],check=True))
    else:subprocess.run(['cp','--reflink=auto','--sparse=always','--preserve=mode,timestamps',str(src),str(dst)],check=True)
def checksums(path):
    files=sorted(path.rglob('*')) if path.is_dir() else [path]
    out={}
    for file in files:
        if not file.is_file():continue
        digest=hashlib.sha256()
        with file.open('rb') as stream:
            for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
        out[str(file.relative_to(path)) if path.is_dir() else '.']=digest.hexdigest()
    return out

def create(label):
    cold();folder=STORE/label
    if folder.exists():raise RuntimeError('Checkpoint already exists')
    folder.mkdir(parents=True,mode=0o700)
    xml=virsh('dumpxml',NAME,'--inactive');(folder/'domain.xml').write_text(xml);root=ET.fromstring(xml)
    paths=[Path(root.find("./devices/disk[@device='disk']/source").get('file')),Path(root.find('./os/nvram').text),Path.home()/'.config/libvirt/qemu/swtpm'/root.find('uuid').text]
    entries=[]
    for index,path in enumerate(paths):
        if not path.exists():raise RuntimeError('Missing VM state: '+str(path))
        dest=folder/str(index);copy(path,dest);entries.append(dict(source=str(path),backup=str(index),directory=path.is_dir(),sha256=checksums(dest)))
    subprocess.run(['qemu-img','check','-q','-f','qcow2',str(folder/'0')],check=True)
    (folder/'manifest.json').write_text(json.dumps(dict(name=NAME,entries=entries,xml_sha256=hashlib.sha256(xml.encode()).hexdigest()),indent=2))
    return folder

def restore(label):
    cold();folder=STORE/label;manifest=json.loads((folder/'manifest.json').read_text())
    if manifest['name']!=NAME:raise RuntimeError('Wrong domain')
    if hashlib.sha256((folder/'domain.xml').read_bytes()).hexdigest()!=manifest['xml_sha256']:raise RuntimeError('Domain metadata changed')
    for entry in manifest['entries']:
        if checksums(folder/entry['backup'])!=entry['sha256']:raise RuntimeError('Checkpoint content hash mismatch: '+entry['backup'])
    # Keep a recoverable copy of all current state before replacement.
    import time
    recovery=create('before-restore-'+str(int(time.time())))
    for entry in manifest['entries']:
        target=Path(entry['source']);staged=target.with_name(target.name+'.mpmb-restore')
        if staged.exists():raise RuntimeError('Previous restore staging exists')
        copy(folder/entry['backup'],staged)
        if target.is_dir():shutil.rmtree(target)
        os.replace(staged,target)
    virsh('define',str(folder/'domain.xml'))
    return dict(restored=str(folder),recovery=str(recovery))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['create','restore','list']);p.add_argument('label',nargs='?');a=p.parse_args()
    with c.desktop_lock():
        if a.action=='list':print('\n'.join(str(p) for p in STORE.glob('*/manifest.json')))
        else:
            if not a.label or not all(x.isalnum() or x in '-_' for x in a.label):p.error('A simple checkpoint label is required')
            print(create(a.label) if a.action=='create' else restore(a.label))
