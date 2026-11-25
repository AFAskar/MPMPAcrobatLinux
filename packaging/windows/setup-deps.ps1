param(
    [string]$DepsDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $DepsDir) { $DepsDir = Join-Path $Root "output\deps" }

New-Item -ItemType Directory -Force -Path $DepsDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DepsDir "fonts") | Out-Null

# 1. Pinned PDFium chromium/8111 (Windows x64)
$PdfiumUrl = "https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F8111/pdfium-v8-win-x64.tgz"
$PdfiumSha = "37B6E827A0D1E6A69A4BF9E65F2A60A3BE2C2EF961CA8FD061476F7ED8C1C3D6"
$PdfiumArchive = Join-Path $DepsDir "pdfium-win-x64.tgz"

if (-not (Test-Path (Join-Path $DepsDir "bin\pdfium.dll"))) {
    Write-Host "Downloading pinned PDFium chromium/8111 (Windows x64)..."
    Invoke-WebRequest -Uri $PdfiumUrl -OutFile $PdfiumArchive
    $actual = (Get-FileHash -Path $PdfiumArchive -Algorithm SHA256).Hash
    if ($actual -ne $PdfiumSha) {
        throw "PDFium SHA-256 mismatch: expected $PdfiumSha, got $actual"
    }
    tar -xzf $PdfiumArchive -C $DepsDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to extract $PdfiumArchive" }
}

# 2. Pinned DejaVu Sans 2.37 TrueType fonts (for Unicode appearance streams & tests)
$FontUrl = "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-sans-ttf-2.37.zip"
$FontSha = "5C6E497A2F36552CB5FFB112C413A6AF39C0F3C47653662B90B4FA6499822FD7"
$FontArchive = Join-Path $DepsDir "dejavu-sans-ttf-2.37.zip"

if (-not (Test-Path (Join-Path $DepsDir "fonts\DejaVuSans.ttf")) -or -not (Test-Path (Join-Path $DepsDir "fonts\DejaVuSans-Bold.ttf"))) {
    Write-Host "Downloading pinned DejaVu Sans 2.37..."
    Invoke-WebRequest -Uri $FontUrl -OutFile $FontArchive
    $actual = (Get-FileHash -Path $FontArchive -Algorithm SHA256).Hash
    if ($actual -ne $FontSha) {
        throw "DejaVu Sans SHA-256 mismatch: expected $FontSha, got $actual"
    }
    $ExtractTmp = Join-Path $DepsDir "dejavu-tmp"
    if (Test-Path $ExtractTmp) { Remove-Item -Recurse -Force $ExtractTmp }
    Expand-Archive -Path $FontArchive -DestinationPath $ExtractTmp -Force
    Get-ChildItem -Path $ExtractTmp -Recurse -Filter "DejaVuSans*.ttf" | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $DepsDir "fonts\$($_.Name)") -Force
    }
    Remove-Item -Recurse -Force $ExtractTmp
}

Write-Host "Windows dependencies ready in $DepsDir"
