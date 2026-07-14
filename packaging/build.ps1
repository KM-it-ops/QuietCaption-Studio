$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
& .\.venv\Scripts\python.exe -m pip install --no-build-isolation -e ".[dev,inference]"
$TestBase = ".pytest-runs\$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $TestBase -Force | Out-Null
& .\.venv\Scripts\python.exe -m pytest -q --basetemp $TestBase -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean packaging\quietcaption.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Portable = "dist\QuietCaption-Studio-portable.zip"
if (Test-Path $Portable) { Remove-Item -LiteralPath $Portable -Force }
Compress-Archive -Path "dist\QuietCaption Studio\*" -DestinationPath $Portable -CompressionLevel Optimal
Write-Host "Portable build: $Portable"

$IsccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($Iscc) {
    & $Iscc "packaging\installer.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed" }
} else {
    Write-Host "Inno Setup 6 not found; portable build is complete and the installer step was skipped."
}
