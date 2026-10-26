#!/usr/bin/env python3
"""Deploy versioned helpers to the existing Windows reference VM."""
import subprocess
import hashlib
import json
from pathlib import Path
import control as c
with c.desktop_lock():
    c.powershell("New-Item -ItemType Directory -Force '"+c.WIN+"' | Out-Null")
    c.powershell("if(Get-ScheduledTask -TaskName 'MPMB-Testing-Desktop' -ErrorAction SilentlyContinue){Stop-ScheduledTask -TaskName 'MPMB-Testing-Desktop'}")
    for name in ['desktop.ps1','mpmb-testing.js','install.ps1']:
        subprocess.run(c.SCP+[str(Path(__file__).parent/'windows'/name),'mpmb-test@127.0.0.1:MPMB-Testing/'+name],check=True)
    print(c.powershell("& '"+c.WIN+"\\install.ps1'"))
    for entry in json.loads((c.REPO/'docs/fixtures.json').read_text()):
        source=c.REPO/'Testing'/entry['file']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=entry['sha256']:raise RuntimeError('Local fixture hash changed: '+str(source))
        name='ashnar.pdf' if 'Ashnar' in source.name else ('blank-2014.pdf' if '_2014_' in source.name else 'blank-2024.pdf')
        target=c.remote_path('fixtures/'+name)
        actual=c.powershell('if(Test-Path '+c.literal(target)+'){(Get-FileHash '+c.literal(target)+').Hash}')
        if actual and actual.lower()!=entry['sha256']:raise RuntimeError('Guest fixture differs: '+target)
        if not actual:subprocess.run(c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/fixtures/'+name],check=True)
        c.powershell('(Get-Item '+c.literal(target)+').IsReadOnly=$true')
    print('Deployed. Restart Reader gracefully before testing an updated adapter.')
