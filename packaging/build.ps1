$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --no-build-isolation -e ".[dev]"
& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean packaging\quietcaption.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Portable = "dist\QuietCaption-Studio-portable.zip"
if (Test-Path $Portable) { Remove-Item -LiteralPath $Portable -Force }
Compress-Archive -Path "dist\QuietCaption Studio\*" -DestinationPath $Portable -CompressionLevel Optimal
Write-Host "Portable build: $Portable"

$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (Test-Path $Iscc) {
    & $Iscc "packaging\installer.iss"
} else {
    Write-Host "Inno Setup 6 not found; portable build is complete and the installer step was skipped."
}
