; Inno Setup 6 installer script for MPMB Reader (Windows x64)
; Build with: ISCC.exe /DAppVersion=0.1.0 /DStageDir=... /DOutDir=... mpmb-reader.iss

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef StageDir
  #define StageDir "..\..\output\dist\windows-stage"
#endif
#ifndef OutDir
  #define OutDir "..\..\output\dist"
#endif

[Setup]
AppId={{8D7B23A6-7C9B-4D1F-A81A-2B9E6D4E5C20}
AppName=MPMB Reader
AppVersion={#AppVersion}
AppVerName=MPMB Reader {#AppVersion}
AppPublisher=AFAskar
AppPublisherURL=https://github.com/AFAskar/MPMPAcrobatLinux
AppSupportURL=https://github.com/AFAskar/MPMPAcrobatLinux/issues
DefaultDirName={autopf}\MPMB Reader
DefaultGroupName=MPMB Reader
AllowNoIcons=yes
LicenseFile={#StageDir}\LICENSE-PDFIUM.txt
OutputDir={#OutDir}
OutputBaseFilename=MPMB-Reader-{#AppVersion}-windows-x64-setup
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
UninstallDisplayIcon={app}\mpmb-reader.exe
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "openwithpdf"; Description: "Register MPMB Reader in the Windows 'Open with' menu for PDF files"; GroupDescription: "File Integration:"

[Files]
Source: "{#StageDir}\mpmb-reader.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\pdfium.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\LICENSE-PDFIUM.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#StageDir}\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\fonts\*"; DestDir: "{app}\fonts"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MPMB Reader"; Filename: "{app}\mpmb-reader.exe"
Name: "{group}\Uninstall MPMB Reader"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MPMB Reader"; Filename: "{app}\mpmb-reader.exe"; Tasks: desktopicon

[Registry]
; Register in "Open with" for .pdf without hijacking the default PDF viewer
Root: HKA; Subkey: "Software\Classes\Applications\mpmb-reader.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "MPMB Reader"; Flags: uninsdeletekey; Tasks: openwithpdf
Root: HKA; Subkey: "Software\Classes\Applications\mpmb-reader.exe\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey; Tasks: openwithpdf
Root: HKA; Subkey: "Software\Classes\Applications\mpmb-reader.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\mpmb-reader.exe"" ""%1"""; Flags: uninsdeletekey; Tasks: openwithpdf
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithList\mpmb-reader.exe"; ValueType: string; ValueName: ""; ValueData: ""; Flags: uninsdeletekey; Tasks: openwithpdf

[Run]
Filename: "{app}\mpmb-reader.exe"; Description: "{cm:LaunchProgram,MPMB Reader}"; Flags: nowait postinstall skipifsilent unchecked
