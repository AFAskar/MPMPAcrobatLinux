param(
    [string]$Version = "",
    [string]$StageDir = "",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")

if (-not $Version) {
    $toml = Get-Content (Join-Path $Root "Cargo.toml") -Raw
    if ($toml -match 'version\s*=\s*"([^"]+)"') { $Version = $Matches[1] } else { $Version = "0.1.0" }
}
if (-not $OutDir) { $OutDir = Join-Path $Root "output\dist" }
if (-not $StageDir) { $StageDir = Join-Path $OutDir "windows-stage" }

if (-not (Test-Path (Join-Path $StageDir "mpmb-reader.exe"))) {
    throw "Windows stage directory missing at $StageDir. Run packaging\windows\build-portable.ps1 first."
}

$IsccPath = $null
$IsccCmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($IsccCmd) {
    $IsccPath = $IsccCmd.Source
}
if (-not $IsccPath) {
    foreach ($candidate in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "C:\ProgramData\chocolatey\bin\ISCC.exe"
    )) {
        if (Test-Path $candidate) { $IsccPath = $candidate; break }
    }
}
if (-not $IsccPath) {
    throw "Inno Setup 6 (ISCC.exe) not found. Install via: choco install innosetup -y"
}

$IssPath = Join-Path $PSScriptRoot "mpmb-reader.iss"
Write-Host "Running Inno Setup compiler: $IsccPath"
& $IsccPath "/DAppVersion=$Version" "/DStageDir=$StageDir" "/DOutDir=$OutDir" $IssPath
if ($LASTEXITCODE -ne 0) { throw "ISCC.exe exited with code $LASTEXITCODE" }

$SetupPath = Join-Path $OutDir "MPMB-Reader-$Version-windows-x64-setup.exe"
if (-not (Test-Path $SetupPath)) { throw "Expected installer not found at $SetupPath" }
Write-Host "Built Windows Installer: $SetupPath"
