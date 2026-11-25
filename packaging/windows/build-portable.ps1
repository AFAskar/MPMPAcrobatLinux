param(
    [string]$Version = "",
    [string]$Binary = "",
    [string]$DepsDir = "",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")

if (-not $Version) {
    $toml = Get-Content (Join-Path $Root "Cargo.toml") -Raw
    if ($toml -match 'version\s*=\s*"([^"]+)"') { $Version = $Matches[1] } else { $Version = "0.1.0" }
}
if (-not $Binary) { $Binary = Join-Path $Root "target\release\mpmb-reader.exe" }
if (-not $DepsDir) { $DepsDir = Join-Path $Root "output\deps" }
if (-not $OutDir) { $OutDir = Join-Path $Root "output\dist" }

$PdfiumDll = Join-Path $DepsDir "bin\pdfium.dll"
$FontRegular = Join-Path $DepsDir "fonts\DejaVuSans.ttf"
$LicenseFile = Join-Path $DepsDir "LICENSE"

if (-not (Test-Path $Binary)) { throw "Release binary not found at $Binary" }
if (-not (Test-Path $PdfiumDll)) { throw "PDFium DLL not found at $PdfiumDll. Run packaging\windows\setup-deps.ps1 first." }
if (-not (Test-Path $FontRegular)) { throw "DejaVuSans.ttf not found at $FontRegular. Run packaging\windows\setup-deps.ps1 first." }

$StageDir = Join-Path $OutDir "windows-stage"
if (Test-Path $StageDir) { Remove-Item -Recurse -Force $StageDir }
New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "fonts") | Out-Null

Copy-Item $Binary (Join-Path $StageDir "mpmb-reader.exe")
Copy-Item $PdfiumDll (Join-Path $StageDir "pdfium.dll")
Copy-Item $FontRegular (Join-Path $StageDir "fonts\DejaVuSans.ttf")
$FontBold = Join-Path $DepsDir "fonts\DejaVuSans-Bold.ttf"
if (Test-Path $FontBold) { Copy-Item $FontBold (Join-Path $StageDir "fonts\DejaVuSans-Bold.ttf") }

Copy-Item (Join-Path $Root "packaging\assets\LICENSE-DEJAVU.txt") (Join-Path $StageDir "LICENSE-DEJAVU.txt")
if (Test-Path $LicenseFile) {
    Copy-Item $LicenseFile (Join-Path $StageDir "LICENSE-PDFIUM.txt")
} else {
    Set-Content (Join-Path $StageDir "LICENSE-PDFIUM.txt") "PDFium (Chromium BSD-3-Clause)"
}
$LicensesDir = Join-Path $DepsDir "licenses"
$StageLicenses = Join-Path $StageDir "licenses"
New-Item -ItemType Directory -Force -Path $StageLicenses | Out-Null
if (Test-Path $LicensesDir) {
    Copy-Item -Recurse -Force (Join-Path $LicensesDir "*") $StageLicenses
}

@"
MPMB Reader $Version (Windows x64 Portable)
===========================================

Run mpmb-reader.exe to open the file picker and select an MPMB Character Record Sheet PDF,
or drag-and-drop / pass a PDF path on the command line:

    mpmb-reader.exe "path\to\character-sheet.pdf"

Environment variables (optional):
  MPMB_THEME=dark|light   Choose startup theme (default: dark; toggleable in toolbar)
  MPMB_PDFIUM=<path>      Override bundled pdfium.dll
  MPMB_FONT=<path>        Override bundled DejaVuSans.ttf

Keep pdfium.dll and the fonts\ directory beside mpmb-reader.exe.
Existing PDFs are never overwritten when saving a copy.
"@ | Set-Content -Encoding UTF8 (Join-Path $StageDir "README.txt")

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$ZipPath = Join-Path $OutDir "MPMB-Reader-$Version-windows-x64-portable.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Built Windows Portable ZIP: $ZipPath"
