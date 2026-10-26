"""Read-only resource and crash evidence for serialized reference tests."""
import json
import time
import control as c


def host():
    values = {}
    for line in open('/proc/meminfo'):
        key, value = line.split(':', 1)
        values[key] = int(value.split()[0])
    data={name: round(values[key] / 1024, 1) for name, key in {
        'total_mib': 'MemTotal', 'available_mib': 'MemAvailable',
        'swap_total_mib': 'SwapTotal', 'swap_free_mib': 'SwapFree'}.items()}
    data['oom_kills']=next(int(line.split()[1]) for line in open('/proc/vmstat') if line.startswith('oom_kill '))
    return data


def snapshot(since=None):
    since = float(since or time.time())
    script = r'''
$os=Get-CimInstance Win32_OperatingSystem
$mem=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
$since=[DateTimeOffset]::FromUnixTimeSeconds(SINCE).LocalDateTime
$events=@(Get-WinEvent -FilterHashtable @{LogName='Application';Id=1000,1001;StartTime=$since} -ErrorAction SilentlyContinue | Where-Object {$_.Message -match 'Acrobat.exe|AcroRd32.exe'} | ForEach-Object {@{id=$_.Id;time=$_.TimeCreated.ToString('o');message=[string]$_.Message}})
$exhaustion=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Microsoft-Windows-Resource-Exhaustion-Detector';Id=2004;StartTime=$since} -ErrorAction SilentlyContinue | ForEach-Object {@{time=$_.TimeCreated.ToString('o');message=[string]$_.Message}})
$reader=@(Get-Process Acrobat,AcroRd32 -ErrorAction SilentlyContinue|ForEach-Object {@{pid=$_.Id;working_set_mib=[math]::Round($_.WorkingSet64/1MB,1);private_mib=[math]::Round($_.PrivateMemorySize64/1MB,1)}})
@{total_mib=[math]::Round($os.TotalVisibleMemorySize/1024);available_mib=[math]::Round($os.FreePhysicalMemory/1024);commit_percent=$mem.PercentCommittedBytesInUse;reader=$reader;reader_events=$events;resource_exhaustion=$exhaustion}|ConvertTo-Json -Depth 5 -Compress
'''.replace('SINCE', str(int(since)))
    return dict(epoch=time.time(), host=host(), guest=json.loads(c.powershell(script)))


def audit(since, host_oom_start=None):
    data=snapshot(since)
    if data['guest']['reader_events'] or data['guest']['resource_exhaustion']:
        raise RuntimeError(json.dumps(data))
    if host_oom_start is not None and data['host']['oom_kills']!=host_oom_start:
        raise RuntimeError('Host OOM counter changed: '+json.dumps(data))
    return data
