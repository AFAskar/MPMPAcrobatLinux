$ErrorActionPreference='Stop'
$root="$env:USERPROFILE\MPMB-Testing"
New-Item -ItemType Directory -Force "$root\queue","$root\responses","$root\screenshots","$root\runs\commands","$root\fixtures" | Out-Null
$reader='C:\Program Files\Adobe\Acrobat DC\Acrobat'
if(-not(Test-Path "$reader\Acrobat.exe")){throw 'Adobe Acrobat Reader is not installed'}
Copy-Item "$root\mpmb-testing.js" "$reader\Javascripts\mpmb-testing.js" -Force
# Trust only the disposable test workspace, never all PDFs or the system drive.
$base='HKCU:\Software\Adobe\Adobe Acrobat\DC\TrustManager\cTrustedFolders'
foreach($cab in @('cJavaScript','cCrossdomain','cScriptInjection')) {
 $key=New-Item -Path "$base\$cab" -Force
 # Adobe documents privileged-location IDs as t followed by an integer.
 $properties=(Get-ItemProperty -Path $key.PSPath).PSObject.Properties
 $existing=$properties['t9000']
 if($existing -and $existing.Value -ne $root){throw 'Trusted location t9000 is already assigned to another path'}
 New-ItemProperty -Path $key.PSPath -Name t9000 -Value $root -PropertyType String -Force | Out-Null
 $old=$properties['tMPMBTesting']
 if($old -and $old.Value -eq $root){Remove-ItemProperty -Path $key.PSPath -Name tMPMBTesting}
}
$principal=New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"& '$root\desktop.ps1' *> '$root\desktop.log'`""
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'MPMB-Testing-Desktop' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask 'MPMB-Testing-Desktop'
# Use the classic UI so application menu commands have stable document context.
$av=New-Item 'HKCU:\Software\Adobe\Adobe Acrobat\DC\AVGeneral' -Force
New-ItemProperty $av.PSPath -Name bEnableAv2 -Value 0 -PropertyType DWord -Force | Out-Null
$policy=New-Item 'HKLM:\SOFTWARE\Policies\Adobe\Adobe Acrobat\DC\FeatureLockDown' -Force
New-ItemProperty $policy.PSPath -Name bToggleFTE -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty $policy.PSPath -Name bAcroSuppressUpsell -Value 1 -PropertyType DWord -Force | Out-Null
# This dedicated, passwordless reference account must reach an interactive desktop on boot.
$logon='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
New-ItemProperty $logon -Name AutoAdminLogon -Value '1' -PropertyType String -Force | Out-Null
New-ItemProperty $logon -Name DefaultUserName -Value $env:USERNAME -PropertyType String -Force | Out-Null
New-ItemProperty $logon -Name DefaultDomainName -Value $env:COMPUTERNAME -PropertyType String -Force | Out-Null
New-ItemProperty $logon -Name DefaultPassword -Value '' -PropertyType String -Force | Out-Null
$desktop=New-Item 'HKCU:\Control Panel\Desktop' -Force
New-ItemProperty $desktop.PSPath -Name ScreenSaveActive -Value '0' -PropertyType String -Force | Out-Null
powercfg.exe /change standby-timeout-ac 0
powercfg.exe /change monitor-timeout-ac 0
# Freeze update installation until the reference baseline is deliberately refreshed.
$updates=New-Item 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' -Force
New-ItemProperty $updates.PSPath -Name NoAutoUpdate -Value 0 -PropertyType DWord -Force | Out-Null
New-ItemProperty $updates.PSPath -Name AUOptions -Value 2 -PropertyType DWord -Force | Out-Null
