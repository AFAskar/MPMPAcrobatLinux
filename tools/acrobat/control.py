#!/usr/bin/env python3
"""Scoped, serialized control of the Windows Acrobat reference environment."""
import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / 'output' / 'testing'
WIN = r'C:\Users\mpmb-test\MPMB-Testing'
KEY = Path.home() / '.ssh' / 'mpmb_win_vm'
MUX = Path.home() / '.cache' / 'mpmb-testing'
MUX.mkdir(parents=True, exist_ok=True, mode=0o700)
SSH = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=8',
       '-o', 'ControlMaster=auto', '-o', 'ControlPersist=300', '-o', f'ControlPath={MUX}/ssh',
       '-i', str(KEY), '-p', '2222', 'mpmb-test@127.0.0.1']
SCP = ['scp', '-q', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
       '-o', f'ControlPath={MUX}/ssh', '-i', str(KEY), '-P', '2222']


def literal(s):
    return "'" + str(s).replace("'", "''") + "'"


def harness_fingerprint():
    files=[p for p in (REPO/'tools/acrobat').rglob('*') if p.suffix in ['.py','.ps1','.js']]
    files += [REPO/'tools/acrobat/run', REPO/'tools/acrobat/requirements.txt', REPO/'docs/fixtures.json', REPO/'docs/environment-lock.json', REPO/'Testing/addons/readiness-sentinel.js']
    return {str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def powershell(script, timeout=45):
    script = "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';" + script
    cmd = 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand ' + base64.b64encode(script.encode('utf-16le')).decode()
    result = subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'SSH command failed')
    return result.stdout.strip().lstrip('\ufeff')


@contextlib.contextmanager
def desktop_lock():
    STATE.mkdir(parents=True, exist_ok=True)
    with (MUX / 'desktop.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def command(action, wait_seconds=35, **kwargs):
    ident = uuid.uuid4().hex
    payload = dict(id=ident, action=action, expires=int((time.time() + wait_seconds + 10) * 1000), **kwargs)
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=True).encode()).decode()
    script = f"""
    $root={literal(WIN)};$id={literal(ident)}
    $text=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))
    [IO.File]::WriteAllText("$root\\queue\\$id.tmp",$text)
    Move-Item "$root\\queue\\$id.tmp" "$root\\queue\\$id.json"
    $clock=[Diagnostics.Stopwatch]::StartNew()
    while($clock.Elapsed.TotalSeconds -lt {wait_seconds}){{
      if(Test-Path "$root\\responses\\$id.json"){{try{{$reply=[Convert]::ToBase64String([IO.File]::ReadAllBytes("$root\\responses\\$id.json"));$reply;exit 0}}catch [IO.IOException]{{}}}}
      Start-Sleep -Milliseconds 50
    }}
    throw 'Desktop command timed out: {ident}'
    """
    started = time.monotonic()
    # Windows console code pages can map Unicode captions (for example bullets)
    # to ASCII control characters. Transfer the exact UTF-8 response bytes.
    data = json.loads(base64.b64decode(powershell(script, timeout=wait_seconds+10)).decode('utf-8-sig'))
    data['host_seconds'] = round(time.monotonic()-started, 3)
    (STATE / (ident + '.json')).write_text(json.dumps(data, indent=2))
    if not data['ok']:
        raise RuntimeError(json.dumps(data))
    return data['result']


def remote_path(path):
    if ':' in path:
        return path
    return WIN + '\\' + path.replace('/', '\\')


def fetch(path, destination=None):
    rel = str(path).replace('\\', '/')
    prefix = WIN.replace('\\', '/') + '/'
    if rel.lower().startswith(prefix.lower()):
        rel = rel[len(prefix):]
    if '..' in Path(rel).parts or ':' in rel:
        raise ValueError('Remote path outside testing workspace')
    destination = Path(destination) if destination else STATE / Path(rel).name
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(SCP + ['mpmb-test@127.0.0.1:MPMB-Testing/' + rel, str(destination)], check=True, capture_output=True)
    return destination


def script_submit(op, **params):
    if op=='close':raise ValueError('Document closing uses the synchronous native close operation')
    session_file=STATE/'reader-session.json'
    if op!='ping' and not session_file.exists():script('ping')
    ident=uuid.uuid4().hex
    req=dict(id=ident,op=op,expires=int((time.time()+300)*1000),**params)
    if op!='ping':req['session']=json.loads(session_file.read_text())['session']
    local=STATE/'commands'/(ident+'.json');local.parent.mkdir(parents=True,exist_ok=True)
    local.write_text(json.dumps(req,ensure_ascii=True,indent=2))
    subprocess.run(SCP+[str(local),'mpmb-test@127.0.0.1:MPMB-Testing/runs/commands/'+ident+'.json'],check=True,capture_output=True)
    command('dispatch',request_id=ident,path=params.get('path'))
    return ident


def script_result(ident, timeout=45):
    result=command('script_result',request_id=ident,wait_seconds=timeout+5,timeout=timeout)
    (STATE/(ident+'-reader.json')).write_text(json.dumps(result,indent=2))
    if not result['ok']:raise RuntimeError(json.dumps(result))
    (STATE/'reader-session.json').write_text(json.dumps({'session':result['session']}))
    return result['result']


def raw_script(op, **params):
    if op=='close':
        state=ensure_document(params['path'])
        if len(state.get('openDocuments',[]))!=1:
            raise RuntimeError('Isolated Reader close requires exactly one open document: '+json.dumps(state.get('openDocuments')))
        result=command('close_document',path=params['path'])
        if result.get('process_terminated'):(STATE/'reader-session.json').unlink(missing_ok=True)
        return result
    try:
        return script_result(script_submit(op,**params))
    except RuntimeError as error:
        # This rejection happens before any document operation. Refresh once.
        if op!='ping' and 'Stale or absent bridge session' in str(error):
            script_result(script_submit('ping'))
            return script_result(script_submit(op,**params))
        raise


def ensure_document(path):
    command('open',path=path)
    deadline=time.monotonic()+35
    while True:
        state=raw_script('functions',path=path,names=['InitializeEverything','CalcMod'])
        calculation=state.get('calculation',{})
        if (all(v=='function' for v in state['functions'].values())
                and calculation.get('app') and calculation.get('doc') and not calculation.get('delay')):
            return state
        if time.monotonic()>deadline:
            raise RuntimeError('MPMB initialization or calculations not ready: '+json.dumps(state))
        time.sleep(0.25)


def script(op, **params):
    if op not in ['ping','functions','close']:
        ensure_document(params['path'])
    return raw_script(op,**params)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('health');sub.add_parser('inspect');sub.add_parser('inspect_full');sub.add_parser('inspect_uia');sub.add_parser('inspect-focused');sub.add_parser('ping')
    menu=sub.add_parser('inspect-menu');menu.add_argument('owner',type=int)
    menu=sub.add_parser('activate-menu');menu.add_argument('owner',type=int);menu.add_argument('position',type=int);menu.add_argument('name')
    picker=sub.add_parser('select-file');picker.add_argument('request_id');picker.add_argument('path')
    for action in ['dialog-control','focus-control']:
        s=sub.add_parser(action);s.add_argument('owner',type=int);s.add_argument('handle',type=int)
    s=sub.add_parser('click-dialog-control');s.add_argument('owner',type=int);s.add_argument('handle',type=int);s.add_argument('name')
    for action in ['open','ready','screenshot','invoke','keys','paste','result','fetch']:
        s=sub.add_parser(action);s.add_argument('value',nargs='?' if action=='screenshot' else None)
        if action=='invoke':s.add_argument('--owner',type=int)
    js=sub.add_parser('js');js.add_argument('operation');js.add_argument('--params',default='{}');js.add_argument('--async',dest='asynchronous',action='store_true')
    args=p.parse_args()
    with desktop_lock():
        if args.action=='health':result=command('health')
        elif args.action in ['inspect','inspect_full','inspect_uia']:result=command(args.action)
        elif args.action=='inspect-focused':result=command('inspect_focused')
        elif args.action=='inspect-menu':result=command('inspect_menu',owner=args.owner)
        elif args.action=='activate-menu':result=command('activate_menu',owner=args.owner,position=args.position,name=args.name)
        elif args.action=='ping':result=script('ping')
        elif args.action=='select-file':result=command('select_file',request_id=args.request_id,path=remote_path(args.path))
        elif args.action in ['dialog-control','focus-control']:result=command(args.action.replace('-','_'),owner=args.owner,handle=args.handle)
        elif args.action=='click-dialog-control':result=command('click_dialog_control',owner=args.owner,handle=args.handle,name=args.name)
        elif args.action=='ready':result=ensure_document(remote_path(args.value))
        elif args.action=='open':result=command('open',path=remote_path(args.value))
        elif args.action=='invoke':result=command('invoke',name=args.value,**({'owner':args.owner} if args.owner is not None else {}))
        elif args.action=='keys':result=command('keys',keys=args.value)
        elif args.action=='paste':result=command('paste',value=args.value)
        elif args.action=='screenshot':
            result=command('screenshot');result['local_path']=str(fetch(result['path'],args.value))
        elif args.action=='fetch':result={'local_path':str(fetch(args.value))}
        elif args.action=='result':result=script_result(args.value)
        elif args.action=='js':
            params=json.loads(args.params)
            if 'path' in params:params['path']=remote_path(params['path'])
            if 'output' in params:params['output']=remote_path(params['output'])
            if 'import_file' in params:params['import_file']=remote_path(params['import_file'])
            if args.asynchronous:
                if args.operation not in ['ping','functions']:ensure_document(params['path'])
                result={'request_id':script_submit(args.operation,**params)}
            else:result=script(args.operation,**params)
        print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
