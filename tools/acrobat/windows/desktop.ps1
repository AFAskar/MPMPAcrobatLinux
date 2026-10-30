param([string]$Root = "$env:USERPROFILE\MPMB-Testing",[switch]$UiAutomationChild,[string]$ChildAction,[string]$ChildValue,[string]$ChildOutput)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Windows.Forms,System.Drawing
Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class DesktopNative {
 public delegate bool EnumProc(IntPtr h, IntPtr p);
 [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc callback, IntPtr p);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
 [DllImport("user32.dll",EntryPoint="SendMessageTimeoutW",CharSet=CharSet.Unicode)] static extern IntPtr MessageText(IntPtr h,uint m,UIntPtr w,string text,uint flags,uint timeout,out UIntPtr result);
 [DllImport("user32.dll",EntryPoint="SendMessageTimeoutW",CharSet=CharSet.Unicode)] static extern IntPtr MessageRead(IntPtr h,uint m,UIntPtr w,StringBuilder text,uint flags,uint timeout,out UIntPtr result);
 [DllImport("user32.dll",EntryPoint="SendMessageTimeoutW")] static extern IntPtr MessageValue(IntPtr h,uint m,UIntPtr w,IntPtr l,uint flags,uint timeout,out UIntPtr result);
 [DllImport("user32.dll")] public static extern bool IsChild(IntPtr parent,IntPtr child);
 [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr h);
 [DllImport("user32.dll")] static extern IntPtr SetFocus(IntPtr h);
 [DllImport("user32.dll",EntryPoint="GetWindowLongPtrW")] static extern IntPtr WindowStyle(IntPtr h,int index);
 static long NumberMessage(IntPtr h,uint message){UIntPtr result;if(MessageValue(h,message,UIntPtr.Zero,IntPtr.Zero,2,1000,out result)==IntPtr.Zero)throw new Exception("Control query timed out");return unchecked((long)result.ToUInt64());}
 public static bool ReadOnlyEdit(IntPtr h){return (WindowStyle(h,-16).ToInt64()&0x800)!=0;}
 public static string ControlText(IntPtr h){long length=NumberMessage(h,0xE);if(length<0||length>1048576)throw new Exception("Unsupported control text length");var text=new StringBuilder((int)length+1);UIntPtr result;if(MessageRead(h,0xD,(UIntPtr)(length+1),text,2,1000,out result)==IntPtr.Zero)throw new Exception("Control text read timed out");if(result.ToUInt64()!=(ulong)text.Length)throw new Exception("Control text read length differs");return text.ToString();}
 public static int ComboIndex(IntPtr h){return checked((int)NumberMessage(h,0x147));}
 public static int ComboCount(IntPtr h){long count=NumberMessage(h,0x146);if(count<0||count>4096)throw new Exception("Unsupported combo item count");return (int)count;}
 public static void FocusControl(IntPtr h,IntPtr owner){uint pid;uint target=GetWindowThreadProcessId(h,out pid),own=GetCurrentThreadId();if(!AttachThreadInput(own,target,true))throw new Exception("Cannot attach control input focus");try{SetForegroundWindow(owner);SetFocus(h);}finally{AttachThreadInput(own,target,false);}if(GetForegroundWindow()!=owner||FocusedControl()!=h)throw new Exception("Input focus differs from requested editable control");}
 public static void SetTextVerified(IntPtr h,string text){
  if(text.Length>65535)throw new Exception("Request exceeds native transport limit");
  UIntPtr result;
  if(MessageText(h,0x000C,UIntPtr.Zero,text,2,2000,out result)==IntPtr.Zero || result==UIntPtr.Zero)throw new Exception("Native request text write failed");
  var read=new StringBuilder(text.Length+1);
  if(MessageRead(h,0x000D,(UIntPtr)(text.Length+1),read,2,2000,out result)==IntPtr.Zero || read.ToString()!=text)throw new Exception("Native request read-back differs");
 }
 [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a,uint b,bool attach);
 [StructLayout(LayoutKind.Sequential)] public struct GUIINFO {public int size;public uint flags;public IntPtr active,focus,capture,menuOwner,moveSize,caret;public RECT caretRect;}
 [DllImport("user32.dll")] static extern bool GetGUIThreadInfo(uint thread,ref GUIINFO info);
 public static bool MenuOpen(){var info=new GUIINFO();info.size=Marshal.SizeOf(info);return GetGUIThreadInfo(0,ref info)&&(info.flags&20)!=0;}
 public static IntPtr FocusedControl(){var info=new GUIINFO();info.size=Marshal.SizeOf(info);return GetGUIThreadInfo(0,ref info)?info.focus:IntPtr.Zero;}
 [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint x,uint y,uint d,UIntPtr extra);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,StringBuilder s,int count);
 [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr parent,EnumProc callback,IntPtr p);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetWindowTextLength(IntPtr h);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h,StringBuilder text,int count);
 [StructLayout(LayoutKind.Sequential)] public struct RECT {public int Left;public int Top;public int Right;public int Bottom;}
 [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h,out RECT rect);
 public static string Text(IntPtr h){int n=Math.Min(1048576,GetWindowTextLength(h));var b=new StringBuilder(n+1);GetWindowText(h,b,b.Capacity);return b.ToString();}
 public static string Class(IntPtr h){var b=new StringBuilder(256);GetClassName(h,b,256);return b.ToString();}
 public static int[] Bounds(IntPtr h){RECT r;GetWindowRect(h,out r);return new int[]{r.Left,r.Top,r.Right-r.Left,r.Bottom-r.Top};}
 public static IntPtr[] Children(IntPtr h){var a=new List<IntPtr>();EnumChildWindows(h,delegate(IntPtr c,IntPtr p){if(IsWindowVisible(c))a.Add(c);return true;},IntPtr.Zero);return a.ToArray();}
 [StructLayout(LayoutKind.Sequential)] public struct POINT {public int X;public int Y;public POINT(int x,int y){X=x;Y=y;}}
 [DllImport("user32.dll")] static extern IntPtr WindowFromPoint(POINT p);
 public static uint PidAt(int x,int y){uint pid;GetWindowThreadProcessId(WindowFromPoint(new POINT(x,y)),out pid);return pid;}
 public static IntPtr HandleAt(int x,int y){return WindowFromPoint(new POINT(x,y));}
 [DllImport("user32.dll")] static extern void keybd_event(byte key,byte scan,uint flags,UIntPtr extra);
 public static void Chord(byte modifier,byte key){keybd_event(modifier,0,0,UIntPtr.Zero);keybd_event(key,0,0,UIntPtr.Zero);keybd_event(key,0,2,UIntPtr.Zero);keybd_event(modifier,0,2,UIntPtr.Zero);}
 public static void Key(byte key){keybd_event(key,0,0,UIntPtr.Zero);keybd_event(key,0,2,UIntPtr.Zero);}
 public static IntPtr[] Windows(int[] pids) {
  var list=new List<IntPtr>();
  EnumWindows(delegate(IntPtr h,IntPtr p) {uint pid;GetWindowThreadProcessId(h,out pid);if(IsWindowVisible(h)&&Array.IndexOf(pids,(int)pid)>=0)list.Add(h);return true;},IntPtr.Zero);
  return list.ToArray();
 }
}
'@
[DesktopNative]::SetProcessDPIAware() | Out-Null
$mutex=$null
if(-not $UiAutomationChild){
 $mutex = New-Object Threading.Mutex($false,'Local\MPMB-Testing-Desktop')
 if (-not $mutex.WaitOne(0)) { exit 0 }
}
New-Item -ItemType Directory -Force "$Root\queue","$Root\responses","$Root\screenshots","$Root\runs","$Root\processed" | Out-Null

function Reader-Processes {
 @(Get-Process Acrobat,AcroRd32,AcroCEF,RdrCEF -ErrorAction SilentlyContinue | Where-Object {$_.SessionId -eq (Get-Process -Id $PID).SessionId})
}
function Reader-Windows {
 $ids = [int[]]@((Reader-Processes).Id)
 if ($ids.Count -eq 0) { return @() }
 @([DesktopNative]::Windows($ids))
}
function Focus-Reader {
 [uint32]$foregroundPid=0
 [DesktopNative]::GetWindowThreadProcessId([DesktopNative]::GetForegroundWindow(),[ref]$foregroundPid) | Out-Null
 if($foregroundPid -in @((Reader-Processes).Id)){return}
 $target=Reader-Windows | Where-Object {$title=New-Object Text.StringBuilder(512);[DesktopNative]::GetWindowText($_,$title,512)|Out-Null;$title.Length -gt 0} | Select-Object -First 1
 if (-not $target) {throw 'No interactive Acrobat window'}
 $shell = New-Object -ComObject WScript.Shell
 $shell.AppActivate("Adobe Acrobat") | Out-Null
 [uint32]$otherPid=0
 $foregroundThread=[DesktopNative]::GetWindowThreadProcessId([DesktopNative]::GetForegroundWindow(),[ref]$otherPid)
 $ownThread=[DesktopNative]::GetCurrentThreadId()
 try {
  [DesktopNative]::AttachThreadInput($ownThread,$foregroundThread,$true) | Out-Null
  [DesktopNative]::SetForegroundWindow($target) | Out-Null
 } finally {[DesktopNative]::AttachThreadInput($ownThread,$foregroundThread,$false) | Out-Null}
 Start-Sleep -Milliseconds 150
 [uint32]$check=0;[DesktopNative]::GetWindowThreadProcessId([DesktopNative]::GetForegroundWindow(),[ref]$check)|Out-Null
 if($check -notin @((Reader-Processes).Id)){
  $b=[DesktopNative]::Bounds($target)
  $x=[int]($b[0]+$b[2]/2);$y=[int]([Math]::Max(0,$b[1])+12)
  if([DesktopNative]::PidAt($x,$y) -notin @((Reader-Processes).Id)){throw 'Another application covers the Acrobat title bar; focus refused'}
  [DesktopNative]::SetCursorPos($x,$y)|Out-Null;[DesktopNative]::mouse_event(2,0,0,0,[UIntPtr]::Zero);[DesktopNative]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
  Start-Sleep -Milliseconds 100
 }
}
function Assert-Reader {
 [uint32]$foregroundPid=0
 [DesktopNative]::GetWindowThreadProcessId([DesktopNative]::GetForegroundWindow(),[ref]$foregroundPid) | Out-Null
 if ($foregroundPid -notin @((Reader-Processes).Id)) {throw 'Foreground window is not Acrobat; input refused'}
}
function Elements([bool]$includeDocument=$false) {
 $all = @()
 foreach ($hwnd in Reader-Windows) {
  try {
   $window=[System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
   $all += $window
   if(-not $includeDocument -and $window.Current.ClassName -eq 'AcrobatSDIWindow'){continue}
   $all += @($window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition))
  } catch {}
 }
 @($all | Where-Object {-not $_.Current.IsOffscreen})
}
function Describe($element) {
 $c=$element.Current;$value=$null;$pattern=$null
 if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$pattern)) {$value=$pattern.Current.Value}
 @{name=$c.Name;class=$c.ClassName;type=$c.ControlType.ProgrammaticName;id=$c.AutomationId;value=$value;rect=@($c.BoundingRectangle.X,$c.BoundingRectangle.Y,$c.BoundingRectangle.Width,$c.BoundingRectangle.Height)}
}
function Find-Element($name,$regex=$false,$timeout=10) {
 $clock=[Diagnostics.Stopwatch]::StartNew()
 do {
  $found=@(Elements | Where-Object {if($regex){$_.Current.Name -match $name}else{$_.Current.Name -eq $name}} | Where-Object {$_.Current.BoundingRectangle.Width -gt 0})
  if($found.Count -gt 0){return ($found | Sort-Object { $_.Current.BoundingRectangle.Width * $_.Current.BoundingRectangle.Height } | Select-Object -First 1)}
  Start-Sleep -Milliseconds 100
 }while($clock.Elapsed.TotalSeconds -lt $timeout)
 throw "Control not found: $name"
}
function Invoke-Element($element) {
 $pattern=$null
 if($element.Current.ClassName -eq 'Button' -and $element.Current.NativeWindowHandle -ne 0){
  [DesktopNative]::PostMessage([IntPtr]$element.Current.NativeWindowHandle,0x00F5,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
  Start-Sleep -Milliseconds 150;return
 }
 if($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)) {$pattern.Invoke()}
 else {
  Focus-Reader;Assert-Reader
  $b=$element.Current.BoundingRectangle
  if($b.Width -lt 1 -or $b.Height -lt 1){throw 'Control has no visible bounds'}
  [DesktopNative]::SetCursorPos([int]($b.X+$b.Width/2),[int]($b.Y+$b.Height/2)) | Out-Null
  [DesktopNative]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
  [DesktopNative]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
 }
 Start-Sleep -Milliseconds 150
}
function Screenshot($name) {
 $bounds=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds
 $bitmap=New-Object Drawing.Bitmap($bounds.Width,$bounds.Height)
 $graphics=[Drawing.Graphics]::FromImage($bitmap)
 try {$graphics.CopyFromScreen($bounds.Location,[Drawing.Point]::Empty,$bounds.Size);$bitmap.Save("$Root\screenshots\$name.png",[Drawing.Imaging.ImageFormat]::Png)}
 finally {$graphics.Dispose();$bitmap.Dispose()}
 "$Root\screenshots\$name.png"
}
function Paste-Checked($text) {
 Focus-Reader;Assert-Reader
 [Windows.Forms.Clipboard]::SetText([string]$text)
 [Windows.Forms.SendKeys]::SendWait('^a');Start-Sleep -Milliseconds 100
 [Windows.Forms.SendKeys]::SendWait('^v');Start-Sleep -Milliseconds 300
 $sentinel='MPMB-copy-sentinel-'+[guid]::NewGuid().ToString('N')
 [Windows.Forms.Clipboard]::SetText($sentinel)
 [Windows.Forms.SendKeys]::SendWait('^a');[Windows.Forms.SendKeys]::SendWait('^c')
 $clock=[Diagnostics.Stopwatch]::StartNew();$actual=$sentinel
 while($clock.ElapsedMilliseconds -lt 2000){
  Start-Sleep -Milliseconds 50;$actual=[Windows.Forms.Clipboard]::GetText()
  if($actual -ne $sentinel){break}
 }
 if($actual -ne [string]$text){throw "Input read-back mismatch. Expected '$text', received '$actual'"}
 [Windows.Forms.SendKeys]::SendWait('{TAB}');Start-Sleep -Milliseconds 200
 @{value=$actual;verified=$true}
}
function Native-Elements {
 foreach($h in Reader-Windows){
  $handles=@($h)
  if([DesktopNative]::Class($h) -ne 'AcrobatSDIWindow'){$handles+=@([DesktopNative]::Children($h))}
  foreach($handle in $handles){
   $name=[DesktopNative]::Text($handle);$class=[DesktopNative]::Class($handle);$textError=$null;$readOnly=$null
   if($class -match '^(Edit|RICHEDIT[0-9]+W)$'){try{$name=[DesktopNative]::ControlText($handle)}catch{$textError=$_.Exception.Message};$readOnly=[DesktopNative]::ReadOnlyEdit($handle)}
   if(-not $name -and $class -notmatch 'Edit|ComboBox'){continue}
   if($class -eq 'Button'){$name=$name.Replace('&','')}
   $parent=[DesktopNative]::GetParent($handle)
   @{name=$name;class=$class;owner=$h;handle=$handle;rect=[DesktopNative]::Bounds($handle);parent=$parent;parent_class=[DesktopNative]::Class($parent);enabled=[DesktopNative]::IsWindowEnabled($handle);read_only=$readOnly;text_error=$textError}
  }
 }
}
function Find-Native($name,$timeout=5,[IntPtr]$parent=[IntPtr]::Zero){
 $watch=[Diagnostics.Stopwatch]::StartNew()
 do {
  $found=@(Native-Elements | Where-Object {$_.name -eq $name -and $_.rect[2] -gt 0 -and $_.rect[3] -gt 0 -and ($parent -eq [IntPtr]::Zero -or $_.owner -eq $parent)})
  if($found.Count){return ($found | Sort-Object {$_.rect[2]*$_.rect[3]} | Select-Object -First 1)}
  Start-Sleep -Milliseconds 50
 }while($watch.Elapsed.TotalSeconds -lt $timeout)
 throw "Native control not found: $name"
}
function Invoke-Native($element){
 if($element.class -eq 'Button'){
  [DesktopNative]::PostMessage([IntPtr]$element.handle,0x00F5,[IntPtr]::Zero,[IntPtr]::Zero)|Out-Null
 }else{
  Focus-Reader;Assert-Reader;$b=$element.rect;$x=[int]($b[0]+$b[2]/2);$y=[int]($b[1]+$b[3]/2)
  if([DesktopNative]::PidAt($x,$y) -notin @((Reader-Processes).Id)){throw 'Control is covered by another application'}
  [DesktopNative]::SetCursorPos($x,$y)|Out-Null;[DesktopNative]::mouse_event(2,0,0,0,[UIntPtr]::Zero);[DesktopNative]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
 }
 Start-Sleep -Milliseconds 100
}
function Dialog-Control($q){
 if(-not $q.owner -or -not $q.handle){throw 'Dialog control operations require observed owner and control handles'}
 $owner=[IntPtr]([long]$q.owner);$handle=[IntPtr]([long]$q.handle)
 if($owner -notin @(Reader-Windows) -or [DesktopNative]::Class($owner) -ne '#32770'){throw 'Control owner is not a visible Reader dialog'}
 if(-not [DesktopNative]::IsChild($owner,$handle) -or -not [DesktopNative]::IsWindowVisible($handle)){throw 'Control is not a visible child of the requested dialog'}
 $class=[DesktopNative]::Class($handle)
 if($class -match '^(Edit|RICHEDIT[0-9]+W)$'){
  if($q.action -eq 'focus_control'){
   if(-not [DesktopNative]::IsWindowEnabled($handle) -or [DesktopNative]::ReadOnlyEdit($handle)){throw 'Editable control is disabled or read-only'}
   Focus-Reader;Assert-Reader;[DesktopNative]::FocusControl($handle,$owner)
  }
  return @{owner=$q.owner;handle=$q.handle;class=$class;text=[DesktopNative]::ControlText($handle);focused=([DesktopNative]::FocusedControl() -eq $handle);read_only=[DesktopNative]::ReadOnlyEdit($handle)}
 }
 if($q.action -eq 'dialog_control' -and $class -eq 'ComboBox'){return @{owner=$q.owner;handle=$q.handle;class=$class;selected_index=[DesktopNative]::ComboIndex($handle);item_count=[DesktopNative]::ComboCount($handle);full_labels_qualified=$false}}
 throw 'Unsupported dialog control type'
}
function Resolve-Known-Dialog($elements){
  $reading=@($elements | Where-Object {$_.name -eq 'Preparing document for reading'})
  if($reading.Count -gt 0){Invoke-Native (Find-Native 'Cancel' 1 ([IntPtr]$reading[0].handle));return $true}
  $changes=@($elements | Where-Object {$_.name -eq 'CHANGES ALERT DIALOG'})
  if($changes.Count -gt 0){Invoke-Native (Find-Native 'Close' 1 ([IntPtr]$changes[0].handle));return $true}
  $openError=@($elements | Where-Object {$_.name -like 'There was an error opening this document*'})
  if($openError.Count -gt 0){$message=$openError[0].name;Invoke-Native (Find-Native 'Cancel');throw $message}
  $sources=@($elements | Where-Object {$_.name -eq 'SOURCE SELECTION DIALOG'})
  if($sources.Count -gt 0){Invoke-Native (Find-Native 'Apply' 1 ([IntPtr]$sources[0].handle));return $true}
  $welcome=@($elements | Where-Object {$_.name -like "Before you get started with MPMB*"})
  if($welcome.Count -gt 0){Invoke-Native (Find-Native 'OK' 1 ([IntPtr]$welcome[0].handle));return $true}
  $permission=@($elements | Where-Object {$_.name -like 'This document is trying to access:*'})
  if($permission.Count -gt 0){
   $message=$permission[0].name
   $allowedPath=$Root+'\'
   if($message.Contains($allowedPath) -and -not $message.Contains('..')){Invoke-Native (Find-Native 'Allow' 1 ([IntPtr]$permission[0].owner));return $true}
   throw 'Unexpected document access permission; refused'
  }
  $savePermission=@($elements | Where-Object {$_.name -like 'Adobe Acrobat needs write access at *'})
  if($savePermission.Count -gt 0){
   $message=$savePermission[0].name
   if($message.Contains($Root+'\runs\') -and -not $message.Contains('..')){Invoke-Native (Find-Native 'Yes' 1 ([IntPtr]$savePermission[0].owner));return $true}
   throw 'Unexpected save permission; refused'
  }
 return $false
}
function Acknowledge-Reader-Result($element) {
 # Activate this exact result dialog and verify its native OK control.
 # Every acknowledgement path must be followed by verified closure.
 $owner=[IntPtr]$element.owner
 if(-not [DesktopNative]::IsWindowVisible($owner)){return}
 Focus-Reader
 try{$button=Find-Native 'OK' 1 $owner}catch{if(-not [DesktopNative]::IsWindowVisible($owner)){return};throw}
 [uint32]$ownerPid=0
 $ownerThread=[DesktopNative]::GetWindowThreadProcessId($owner,[ref]$ownerPid)
 if($ownerPid -notin @((Reader-Processes).Id)){throw 'Result dialog no longer belongs to Reader'}
 $ownThread=[DesktopNative]::GetCurrentThreadId()
 try {
  [DesktopNative]::AttachThreadInput($ownThread,$ownerThread,$true)|Out-Null
  [DesktopNative]::SetForegroundWindow($owner)|Out-Null
 }finally{[DesktopNative]::AttachThreadInput($ownThread,$ownerThread,$false)|Out-Null}
 if([DesktopNative]::GetForegroundWindow() -ne $owner){throw 'Reader result dialog could not receive focus'}
 # Keep keyboard acknowledgement when OK already owns focus. If Acrobat
 # filters it during startup, try the currently observed button position only
 # after the exact same receipt is still present. Posted BM_CLICK can disturb
 # subsequent PDF-field focus, so it is not used here.
 $spaceSent=$false;$pointerSent=$false
 $watch=[Diagnostics.Stopwatch]::StartNew()
 do {
  if(-not [DesktopNative]::IsWindowVisible($owner)){return}
  $remaining=@(Native-Elements | Where-Object {$_.owner -eq $owner -and $_.name.StartsWith('MPMB_RESULT')})
  if(-not $remaining.Count){return}
  if($remaining.Count -ne 1 -or $remaining[0].name -ne $element.name){throw 'Reader result receipt changed before acknowledgement completed'}
  if($watch.Elapsed.TotalMilliseconds -ge 250){
   if([DesktopNative]::GetForegroundWindow() -ne $owner){throw 'Reader result dialog lost foreground before acknowledgement'}
   if(-not $spaceSent -and [DesktopNative]::FocusedControl() -eq [IntPtr]$button.handle){
    [DesktopNative]::Key(0x20);$spaceSent=$true
   }elseif(-not $pointerSent -and (-not $spaceSent -or $watch.Elapsed.TotalMilliseconds -ge 1000)){
    $bounds=[DesktopNative]::Bounds([IntPtr]$button.handle)
    $x=[int]($bounds[0]+$bounds[2]/2);$y=[int]($bounds[1]+$bounds[3]/2)
    if([DesktopNative]::HandleAt($x,$y) -eq [IntPtr]$button.handle){
     [DesktopNative]::SetCursorPos($x,$y)|Out-Null
     [DesktopNative]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
     [DesktopNative]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
     $pointerSent=$true
    }
   }
  }
  Start-Sleep -Milliseconds 50
 }while($watch.Elapsed.TotalSeconds -lt 10)
 throw 'Reader result dialog did not close after acknowledgement'
}
function Script-Result($id,$timeout=25) {
 $cached="$Root\responses\reader-$id.json"
 if(Test-Path $cached){return (Get-Content $cached -Raw|ConvertFrom-Json)}
 $clock=[Diagnostics.Stopwatch]::StartNew()
 do {
  $elements=@(Native-Elements)
  if(Resolve-Known-Dialog $elements){continue}
  foreach($e in $elements) {
   $text=$e.name
   if($text -and $text.StartsWith('MPMB_RESULT')) {
    $result=$text.Substring(11).Trim() | ConvertFrom-Json
    if($result.id -notmatch '^[a-f0-9]{32}$'){throw ("Invalid Reader response id: "+$text)}
    $result|ConvertTo-Json -Depth 12 -Compress|Set-Content "$Root\responses\reader-$($result.id).json" -Encoding UTF8
    if($result.id -ne $id){
     $result | ConvertTo-Json -Depth 12 | Set-Content "$Root\responses\orphan-$($result.id).json" -Encoding UTF8
     Acknowledge-Reader-Result $e
     break
    }
    Acknowledge-Reader-Result $e
    return $result
   }
  }
  Start-Sleep -Milliseconds 100
 }while($clock.Elapsed.TotalSeconds -lt $timeout)
 throw "Timed out awaiting Reader script result: $id"
}
function Scope-Path($path) {
 $full=[IO.Path]::GetFullPath($path)
 if(-not $full.StartsWith($Root+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Path outside testing workspace'}
 $full
}
function Reader-Main($path='',$timeout=20){
 $watch=[Diagnostics.Stopwatch]::StartNew();$filename=if($path){[IO.Path]::GetFileName($path)}else{''}
 do {
  foreach($h in Reader-Windows){
   if([DesktopNative]::Class($h) -ne 'AcrobatSDIWindow'){continue}
   if(-not $filename -or [DesktopNative]::Text($h).IndexOf($filename,[StringComparison]::OrdinalIgnoreCase) -ge 0){return $h}
  }
  Start-Sleep -Milliseconds 100
 }while($watch.Elapsed.TotalSeconds -lt $timeout)
 throw "Requested Reader window is not active: $filename"
}
function Focus-Main($h){
 [DesktopNative]::SetForegroundWindow($h)|Out-Null;Start-Sleep -Milliseconds 100
 if([DesktopNative]::GetForegroundWindow() -ne $h){
  $b=[DesktopNative]::Bounds($h);$x=[int]($b[0]+$b[2]/2);$y=[int]([Math]::Max(0,$b[1])+12)
  [uint32]$expected=0;[DesktopNative]::GetWindowThreadProcessId($h,[ref]$expected)|Out-Null
  if([DesktopNative]::PidAt($x,$y) -ne $expected){throw 'Another window covers the requested Reader title bar'}
  [DesktopNative]::SetCursorPos($x,$y)|Out-Null;[DesktopNative]::mouse_event(2,0,0,0,[UIntPtr]::Zero);[DesktopNative]::mouse_event(4,0,0,0,[UIntPtr]::Zero);Start-Sleep -Milliseconds 100
 }
 if([DesktopNative]::GetForegroundWindow() -ne $h){throw 'Reader main window could not receive focus'}
}
function Settle-Dialogs {
 $watch=[Diagnostics.Stopwatch]::StartNew()
 do {
  $elements=@(Native-Elements)
  if(Resolve-Known-Dialog $elements){continue}
  $reply=@($elements | Where-Object {$_.name.StartsWith('MPMB_RESULT')})
  if($reply.Count){
   $result=$reply[0].name.Substring(11).Trim()|ConvertFrom-Json
   if($result.id -notmatch '^[a-f0-9]{32}$'){throw 'Invalid pending Reader response'}
   $result|ConvertTo-Json -Depth 12 -Compress|Set-Content "$Root\responses\reader-$($result.id).json" -Encoding UTF8
   Acknowledge-Reader-Result $reply[0];continue
  }
  if(@($elements|Where-Object {$_.class -eq '#32770'}).Count){throw 'An unexpected dialog blocks the Reader menu'}
  return
 }while($watch.Elapsed.TotalSeconds -lt 15)
 throw 'Reader dialogs did not settle'
}
function Check-Invocation {
 $file="$Root\active-command.json"
 if(Test-Path $file){
  $active=Get-Content $file -Raw|ConvertFrom-Json
  if(-not(Test-Path "$Root\responses\reader-$($active.id).json") -and (Get-Process -Id $active.driver_pid -ErrorAction SilentlyContinue)){
   throw "A Reader invocation is still outstanding: $($active.id); collect its result before sending another command"
  }
 }
}
function Dispatch-Reader($q){
 if($q.request_id -notmatch '^[a-f0-9]{32}$'){throw 'Invalid request id'}
 if(Test-Path "$Root\responses\reader-$($q.request_id).json"){return @{already_completed=$true}}
 Check-Invocation
 $request=Get-Content "$Root\runs\commands\$($q.request_id).json" -Raw|ConvertFrom-Json
 if($request.id -ne $q.request_id -or $request.expires -lt [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()){throw 'Invalid or expired Reader command'}
 if($request.path){$path=Scope-Path $request.path}else{$path=''}
 if(-not @(Get-Process Acrobat,AcroRd32 -ErrorAction SilentlyContinue|Where-Object {$_.SessionId -eq (Get-Process -Id $PID).SessionId}).Count){Start-Process 'C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe'}
 Settle-Dialogs
 $main=Reader-Main $path
 [uint32]$driver=0;[DesktopNative]::GetWindowThreadProcessId($main,[ref]$driver)|Out-Null
 $request|Add-Member -NotePropertyName driver_pid -NotePropertyValue $driver -Force
 $request|ConvertTo-Json -Depth 15 -Compress|Set-Content "$Root\active-command.tmp" -Encoding UTF8
 Move-Item "$Root\active-command.tmp" "$Root\active-command.json" -Force
 $submitted=$false
 try {
  $watch=[Diagnostics.Stopwatch]::StartNew()
  do {
   $elements=@(Native-Elements)
   $dialog=@($elements|Where-Object {$_.class -eq '#32770' -and $_.name -eq 'MPMB Automation Request'})
   if($dialog.Count -eq 1){
    $edits=@($elements|Where-Object {$_.owner -eq $dialog[0].handle -and $_.class -match '^(Edit|RICHEDIT[0-9]+W)$'})
    $wire=$request|ConvertTo-Json -Depth 15 -Compress
    if($edits.Count -ne 1){throw 'Native request dialog has ambiguous edit controls'}
    [DesktopNative]::SetTextVerified([IntPtr]$edits[0].handle,$wire)
    $submitted=$true
    Invoke-Native (Find-Native 'OK' 1 ([IntPtr]$dialog[0].handle))
    return @{requested=$request.id;driver_pid=$driver;transport='native-dialog';verified_characters=$wire.Length}
   }
   if(Resolve-Known-Dialog $elements){continue}
   if(@($elements|Where-Object {$_.class -eq '#32770'}).Count){throw 'An unexpected dialog blocks request submission'}
   if([DesktopNative]::MenuOpen()){
    [Windows.Forms.SendKeys]::SendWait('m')
   }else{
    try{Focus-Main $main}catch{
     $pending=@(Native-Elements)
     if(@($pending|Where-Object {$_.class -eq '#32770' -and $_.name -eq 'MPMB Automation Request'}).Count -eq 1){continue}
     if(Resolve-Known-Dialog $pending){continue}
     throw
    }
    [Windows.Forms.SendKeys]::SendWait('%f')
   }
   Start-Sleep -Milliseconds 150
  }while($watch.Elapsed.TotalSeconds -lt 25)
  throw 'Native request dialog did not appear'
 }catch{
  if(-not $submitted){
   @{id=$request.id;ok=$false;error=[string]$_;stage='transport-before-submission'}|ConvertTo-Json -Compress|Set-Content "$Root\responses\reader-$($request.id).json" -Encoding UTF8
  }
  throw
 }

}
function Close-ReaderDocument($path){
 $path=Scope-Path $path;Check-Invocation;Settle-Dialogs
 $main=Reader-Main $path;Focus-Main $main
 $other=@(Reader-Windows|Where-Object {[DesktopNative]::Class($_) -eq 'AcrobatSDIWindow' -and $_ -ne $main -and [DesktopNative]::Text($_) -match '\.pdf'})
 if($other.Count){throw 'Process isolation requires one document; another PDF is open'}
 # Exit the application instead of retaining a process with closed-document state.
 [Windows.Forms.SendKeys]::SendWait('^q')
 $filename=[IO.Path]::GetFileName($path);$watch=[Diagnostics.Stopwatch]::StartNew()
 do {
  $elements=@(Native-Elements)
  $save=@($elements|Where-Object {$_.name -like 'Do you want to save changes*' -and $_.name.Contains($filename)})
  if($save.Count){Invoke-Native (Find-Native 'No' 1 ([IntPtr]$save[0].owner));continue}
  if(Resolve-Known-Dialog $elements){continue}
  $still=@(Reader-Processes|Where-Object {$_.ProcessName -in @('Acrobat','AcroRd32')})
  if(-not $still.Count){return @{path=$path;closed=$true;process_terminated=$true}}
  Start-Sleep -Milliseconds 100
 }while($watch.Elapsed.TotalSeconds -lt 20)
 throw 'Reader did not exit cleanly after closing the requested document'
}
function Select-ImportFile($q){
 $path=Scope-Path $q.path
 if(-not(Test-Path $path -PathType Leaf)){throw 'Import file does not exist'}
 $active=Get-Content "$Root\active-command.json" -Raw|ConvertFrom-Json
 if($active.id -ne $q.request_id -or $active.name -ne 'ImportUserScriptFile' -or -not $active.file_picker){throw 'No matching file-picker import is outstanding'}
 if((Scope-Path $active.import_file) -ne $path){throw 'File picker path differs from the authorized request'}
 $watch=[Diagnostics.Stopwatch]::StartNew()
 do {
  $elements=@(Native-Elements)
  $dialog=@($elements|Where-Object {$_.class -eq '#32770' -and $_.name -eq 'Open'})
  if($dialog.Count -eq 1){
   $owner=$dialog[0].handle
   $label=@($elements|Where-Object {$_.owner -eq $owner -and $_.class -eq 'Static' -and $_.name.Replace('&','') -eq 'File name:'})
   $edit=@($elements|Where-Object {$_.owner -eq $owner -and $_.class -eq 'Edit' -and $_.rect[2] -gt 0 -and $_.rect[3] -gt 0})
   $open=@($elements|Where-Object {$_.owner -eq $owner -and $_.class -eq 'Button' -and $_.name -eq 'Open'})
   if($label.Count -ne 1 -or $edit.Count -ne 1 -or $open.Count -ne 1){throw 'Import file dialog controls are ambiguous'}
   [DesktopNative]::SetTextVerified([IntPtr]$edit[0].handle,$path)
   Invoke-Native $open[0]
   return @{path=$path;request_id=$q.request_id;verified=$true}
  }
  Start-Sleep -Milliseconds 100
 }while($watch.Elapsed.TotalSeconds -lt 12)
 throw 'Import file dialog did not appear'
}
function Save-PrintOutput($q){
 $path=Scope-Path $q.path
 if(-not $path.StartsWith($Root+'\runs\',[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($path) -ine '.pdf'){throw 'Print output must be a new runs PDF'}
 if(Test-Path $path){throw 'Print output already exists'}
 $active=Get-Content "$Root\active-command.json" -Raw|ConvertFrom-Json
 if($active.id -ne $q.request_id -or $active.name -notin @('PrintTheSheet','PrintButton')){throw 'No matching original MPMB print operation is outstanding'}
 $elements=@(Native-Elements)
 $dialog=@($elements|Where-Object {$_.class -eq '#32770' -and $_.name -eq 'Save Print Output As'})
 if($dialog.Count -ne 1){throw 'Virtual printer output dialog is absent or ambiguous'}
 $owner=$dialog[0].handle
 $edit=@($elements|Where-Object {$_.owner -eq $owner -and $_.class -eq 'Edit' -and $_.rect[2] -gt 0 -and $_.rect[3] -gt 0})
 $save=@($elements|Where-Object {$_.owner -eq $owner -and $_.class -eq 'Button' -and $_.name -eq 'Save'})
 if($edit.Count -ne 1 -or $save.Count -ne 1){throw 'Virtual printer output controls are ambiguous'}
 [DesktopNative]::SetTextVerified([IntPtr]$edit[0].handle,$path)
 Invoke-Native $save[0]
 return @{path=$path;request_id=$q.request_id;verified=$true}
}
function Uia-Child($action,$value='') {
 $file="$Root\responses\uia-"+[guid]::NewGuid().ToString('N')+'.json'
 $quote={param($v) "'"+([string]$v).Replace("'","''")+"'"}
 $code="& "+(& $quote "$Root\desktop.ps1")+" -Root "+(& $quote $Root)+" -UiAutomationChild -ChildAction "+(& $quote $action)+" -ChildValue "+(& $quote $value)+" -ChildOutput "+(& $quote $file)
 $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($code))
 $child=Start-Process powershell.exe -ArgumentList "-NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -EncodedCommand $encoded" -PassThru
 if(-not $child.WaitForExit(15000)){$child.Kill();throw 'UI Automation child timed out after 15 seconds; desktop worker remains available'}
 if(-not(Test-Path $file)){throw 'UI Automation child exited without a response'}
 $response=Get-Content $file -Raw|ConvertFrom-Json
 if(-not $response.ok){throw $response.error}
 $response.result
}
function Execute($q) {
 switch($q.action){
  'health' {[uint32]$fp=0;$fh=[DesktopNative]::GetForegroundWindow();$ft=[DesktopNative]::GetWindowThreadProcessId($fh,[ref]$fp);@{version=3;capabilities=@('dialog_control','focus_control');foreground_handle=$fh.ToInt64();foreground_pid=$fp;foreground_thread=$ft;session=(Get-Process -Id $PID).SessionId;readers=@(Reader-Processes | Select-Object Id,SessionId);windows=@(Reader-Windows | ForEach-Object {$b=New-Object Text.StringBuilder(512);[DesktopNative]::GetWindowText($_,$b,512) | Out-Null;$b.ToString()})}}
  'dismiss_pin' {
   [uint32]$fp=0;$fh=[DesktopNative]::GetForegroundWindow();[DesktopNative]::GetWindowThreadProcessId($fh,[ref]$fp)|Out-Null
   if((Get-Process -Id $fp).ProcessName -ne 'ShellExperienceHost'){throw 'Foreground is not Windows notification host'}
   $window=[Windows.Automation.AutomationElement]::FromHandle($fh)
   $button=$window.FindFirst([Windows.Automation.TreeScope]::Descendants,(New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::NameProperty,'No, thanks')))
   if(-not $button){throw 'Expected taskbar pin notification is absent'}
   $pattern=$null
   if($button.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)){$pattern.Invoke()}
   else{$b=$button.Current.BoundingRectangle;[DesktopNative]::SetCursorPos([int]($b.X+$b.Width/2),[int]($b.Y+$b.Height/2))|Out-Null;[DesktopNative]::mouse_event(2,0,0,0,[UIntPtr]::Zero);[DesktopNative]::mouse_event(4,0,0,0,[UIntPtr]::Zero)}
   @{dismissed='No, thanks'}
  }
  'inspect' {,@(Native-Elements)}
  'dialog_control' {Dialog-Control $q}
  'focus_control' {Dialog-Control $q}
  'inspect_uia' {,@(Uia-Child 'inspect_uia')}
  'inspect_full' {,@(Uia-Child 'inspect_full')}
  'invoke' {$parent=[IntPtr]::Zero;if($q.owner){$parent=[IntPtr]([long]$q.owner)};$element=$null;try{$element=Find-Native $q.name 0.3 $parent}catch{};if($element){Invoke-Native $element}elseif($q.owner){throw 'Named control is absent from the requested dialog'}else{Uia-Child 'invoke' $q.name|Out-Null};@{invoked=$q.name}}
  'keys' {Focus-Reader;Assert-Reader;[Windows.Forms.SendKeys]::SendWait($q.keys);Start-Sleep -Milliseconds 150;@{sent=$q.keys}}
  'paste' {Paste-Checked $q.value}
  'dispatch' {Dispatch-Reader $q}
  'close_document' {Close-ReaderDocument $q.path}
  'select_file' {Select-ImportFile $q}
  'save_print_output' {Save-PrintOutput $q}
  'open' {Check-Invocation;$path=Scope-Path $q.path;if(-not(Test-Path $path)){throw 'PDF not found'};$filename=[IO.Path]::GetFileName($path);$existing=@(Reader-Windows|Where-Object {[DesktopNative]::Class($_) -eq 'AcrobatSDIWindow' -and [DesktopNative]::Text($_).IndexOf($filename,[StringComparison]::OrdinalIgnoreCase) -ge 0});if(-not $existing.Count){Start-Process 'C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe' -ArgumentList ('"'+$path+'"')};@{requested=$path;already_open=($existing.Count -gt 0)}}
  'screenshot' {@{path=(Screenshot $q.id)}}
  'script_result' {Script-Result $q.request_id $(if($q.timeout){$q.timeout}else{25})}
  'quit' {foreach($p in Reader-Processes | Where-Object {$_.ProcessName -in @('Acrobat','AcroRd32')}){$p.CloseMainWindow()|Out-Null};@{requested=$true}}
  default {throw "Unknown action: $($q.action)"}
 }
}

if($UiAutomationChild){
 try {
  $result=switch($ChildAction){
   'inspect_uia' {@(Elements | ForEach-Object {Describe $_})}
   'inspect_full' {@(Elements $true | ForEach-Object {Describe $_})}
   'invoke' {Invoke-Element (Find-Element $ChildValue);@{invoked=$ChildValue}}
   default {throw 'Unsupported UI Automation child action'}
  }
  $response=@{ok=$true;result=$result}
 }catch{$response=@{ok=$false;error=$_.Exception.Message}}
 $response|ConvertTo-Json -Depth 12 -Compress|Set-Content $ChildOutput -Encoding UTF8
 exit 0
}
@{pid=$PID;session=(Get-Process -Id $PID).SessionId;version=3;started=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content "$Root\desktop-ready.json" -Encoding UTF8
try {
 while(-not(Test-Path "$Root\stop-desktop")){
  foreach($file in Get-ChildItem "$Root\queue\*.json" | Sort-Object LastWriteTime){
   $output="$Root\responses\$($file.BaseName).json"
   if(Test-Path $output){Move-Item $file.FullName (Join-Path "$Root\processed" $file.Name) -Force;continue}
   @{id=$file.BaseName;pid=$PID;started=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content "$Root\desktop-current.json" -Encoding UTF8
   $watch=[Diagnostics.Stopwatch]::StartNew()
   try {
    $q=Get-Content $file.FullName -Raw | ConvertFrom-Json
    if($q.id -ne $file.BaseName -or $q.id -notmatch '^[a-z0-9-]+$'){throw 'Invalid command id'}
    if($q.expires -lt [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()){throw 'Expired command; refused to replay'}
    $result=Execute $q
    $response=@{id=$q.id;ok=$true;result=$result;elapsed_ms=$watch.ElapsedMilliseconds}
   }catch{
    $failure=$_.Exception.Message;$snapshot=$null;$snapshotError=$null
    try{$snapshot=Screenshot ($file.BaseName+'-failure')}catch{$snapshotError=$_.Exception.Message}
    $response=@{id=$file.BaseName;ok=$false;error=$failure;elapsed_ms=$watch.ElapsedMilliseconds;screenshot=$snapshot;screenshot_error=$snapshotError}
   }
   $response | ConvertTo-Json -Depth 12 -Compress | Set-Content ($output+'.tmp') -Encoding UTF8
   Move-Item ($output+'.tmp') $output -Force
   Move-Item $file.FullName (Join-Path "$Root\processed" $file.Name) -Force
   Remove-Item "$Root\desktop-current.json" -ErrorAction SilentlyContinue
  }
  Start-Sleep -Milliseconds 150
 }
}finally{$mutex.ReleaseMutex();$mutex.Dispose()}
