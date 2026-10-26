#!/usr/bin/env python3
"""Start the reference VM and wait for its automatic interactive desktop."""
import json
import subprocess
import time
import control as c
import preflight

def main():
    base=['virsh','-c','qemu:///session']
    state=subprocess.check_output(base+['domstate','mpmb-windows11'],text=True).strip()
    if state=='shut off':subprocess.run(base+['start','mpmb-windows11'],check=True)
    elif state!='running':raise RuntimeError('Unexpected VM state: '+state)
    deadline=time.monotonic()+150;last=None
    while time.monotonic()<deadline:
        try:
            with c.desktop_lock():
                c.powershell("$t=Get-ScheduledTask 'MPMB-Testing-Desktop';if($t.State -ne 'Running'){Start-ScheduledTask $t};'ready'",timeout=12)
                clock=json.dumps({'execute':'guest-set-time','arguments':{'time':time.time_ns()}})
                synced=subprocess.run(base+['qemu-agent-command','mpmb-windows11',clock],capture_output=True,text=True)
                if synced.returncode:
                    epoch=int(time.time()*1000)
                    c.powershell("if([Math]::Abs([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()-"+str(epoch)+") -gt 10000){Set-Date -Date ([DateTimeOffset]::FromUnixTimeMilliseconds("+str(epoch)+").LocalDateTime)|Out-Null}")
                health=c.command('health',wait_seconds=5)
            if health['session']>0:break
        except Exception as error:last=str(error)
        time.sleep(1)
    else:raise RuntimeError('Windows interactive helper did not become ready: '+str(last))
    return preflight.main()
if __name__=='__main__':raise SystemExit(main())
