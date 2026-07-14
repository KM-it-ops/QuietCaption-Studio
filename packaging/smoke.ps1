$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$PortableExe = Join-Path $Root "dist\QuietCaption Studio\QuietCaption Studio.exe"
$Installer = Join-Path $Root "dist\QuietCaption-Studio-Setup-1.0.0.exe"
$InstallDir = Join-Path ([System.IO.Path]::GetTempPath()) "QuietCaption-Smoke-$([guid]::NewGuid().ToString('N'))"

function Assert-AppStaysRunning {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @()
    )
    if ($Arguments.Count -gt 0) {
        $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -PassThru -WindowStyle Hidden
    } else {
        $process = Start-Process -FilePath $Executable -PassThru -WindowStyle Hidden
    }
    Start-Sleep -Seconds 4
    $process.Refresh()
    if ($process.HasExited) {
        throw "Application exited during startup smoke test: $Executable $($Arguments -join ' ')"
    }
    Stop-Process -Id $process.Id -Force
    $process.WaitForExit()
}

if (-not (Test-Path -LiteralPath $PortableExe)) { throw "Portable executable not found: $PortableExe" }
if (-not (Test-Path -LiteralPath $Installer)) { throw "Installer not found: $Installer" }

Assert-AppStaysRunning -Executable $PortableExe
Assert-AppStaysRunning -Executable $PortableExe -Arguments @("--demo")

$installerProcess = Start-Process -FilePath $Installer -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$InstallDir") -PassThru -Wait -WindowStyle Hidden
if ($installerProcess.ExitCode -ne 0) { throw "Silent installer failed with exit code $($installerProcess.ExitCode)" }

$InstalledExe = Join-Path $InstallDir "QuietCaption Studio.exe"
Assert-AppStaysRunning -Executable $InstalledExe

$Uninstaller = Join-Path $InstallDir "unins000.exe"
if (Test-Path -LiteralPath $Uninstaller) {
    $uninstallProcess = Start-Process -FilePath $Uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -PassThru -Wait -WindowStyle Hidden
    if ($uninstallProcess.ExitCode -ne 0) { throw "Silent uninstall failed with exit code $($uninstallProcess.ExitCode)" }
}

Write-Host "Portable and installed startup smoke tests passed."
