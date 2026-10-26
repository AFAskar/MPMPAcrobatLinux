#!/usr/bin/env python3
"""Check transport, immutable fixtures, clock, desktop, Reader and boot policy."""
import hashlib
import json
import shutil
import subprocess
import time
import sys
import pypdf
import PIL
import control as c


def main():
    checks = {}
    lock=json.loads((c.REPO/'docs/environment-lock.json').read_text())
    for entry in json.loads((c.REPO / 'docs/fixtures.json').read_text()):
        path = c.REPO / 'Testing' / entry['file']
        checks['fixture:' + entry['file']] = path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
    for binary in ['ssh', 'scp', 'virsh', 'cargo', 'rustc', 'clang', 'cmake', 'pkg-config', 'pdftoppm']:
        checks['binary:' + binary] = shutil.which(binary) is not None
    state = subprocess.check_output(['virsh', '-c', 'qemu:///session', 'domstate', 'mpmb-windows11'], text=True).strip()
    checks['vm-running'] = state == 'running'
    remote = json.loads(c.powershell(r"""
        $logon=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
        $updates=Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
        @{
          epoch=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
          timezone=(Get-TimeZone).Id
          autoLogon=$logon.AutoAdminLogon
          updateMode=$updates.AUOptions
          pendingRestart=((Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') -or (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'))
          reader=(Get-Item 'C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe').VersionInfo.FileVersion
          windowsVersion=(Get-CimInstance Win32_OperatingSystem).Version
          desktopHash=(Get-FileHash "$env:USERPROFILE\MPMB-Testing\desktop.ps1" -Algorithm SHA256).Hash
          adapterHash=(Get-FileHash 'C:\Program Files\Adobe\Acrobat DC\Acrobat\Javascripts\mpmb-testing.js' -Algorithm SHA256).Hash
          trustedRoots=@(foreach($cab in @('cJavaScript','cCrossdomain','cScriptInjection')){[string](Get-ItemProperty "HKCU:\Software\Adobe\Adobe Acrobat\DC\TrustManager\cTrustedFolders\$cab" -ErrorAction SilentlyContinue).t9000})
          protectedMode=(Get-ItemProperty 'HKCU:\Software\Adobe\Adobe Acrobat\DC\Privileged' -ErrorAction SilentlyContinue).bProtectedMode
        } | ConvertTo-Json
    """))
    checks['automatic-login'] = remote['autoLogon'] == '1'
    checks['updates-notify-only'] = remote['updateMode'] == 2
    checks['no-pending-windows-restart'] = not remote['pendingRestart']
    checks['clock-within-10-seconds'] = abs(remote['epoch'] - time.time()) < 10
    checks['reader-build-matches-baseline'] = remote['reader']==lock['reader_file_version']
    checks['test-directory-trust-configured']=len(remote['trustedRoots'])==3 and all(p.lower().rstrip('\\')==c.WIN.lower() for p in remote['trustedRoots'])
    checks['reader-protected-mode-enabled']=remote['protectedMode']==1
    for kind,name in [('desktop','desktop.ps1'),('adapter','mpmb-testing.js')]:
        checks[kind+'-deployment-matches-source']=remote[kind+'Hash'].lower()==hashlib.sha256((c.REPO/'tools/acrobat/windows'/name).read_bytes()).hexdigest()
    with c.desktop_lock():
        bridge = c.script('ping')
        health = c.command('health')
        dialogs = c.command('inspect')
        checks['no-blocking-dialogs'] = not any(x.get('class') == '#32770' for x in dialogs)
        checks['interactive-session'] = health['session'] > 0
        checks['desktop-protocol'] = health.get('version') == lock['desktop_protocol']
        checks['acrobat-reader'] = bridge['type'] == 'Reader'
        checks['adapter-protocol'] = bridge.get('protocol') == lock['adapter_protocol']
    result = dict(passed=all(checks.values()), checks=checks, guest=remote, desktop=health, bridge=bridge,
                  tooling=dict(python=sys.version.split()[0],pypdf=pypdf.__version__,Pillow=PIL.__version__))
    c.STATE.mkdir(parents=True, exist_ok=True)
    (c.STATE / 'preflight.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
