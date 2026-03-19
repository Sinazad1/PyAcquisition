param(
    [string]$IonInPath = "C:\conductivirty analysis\Dialin stuff\ionin-v1",
    [string]$SpecFile = "alyPyAcquisition_ionin.spec"
)

$ErrorActionPreference = "Stop"

Write-Host "Installing IonIn package (editable)..." -ForegroundColor Cyan
python -m pip install -e "$IonInPath"

Write-Host "Building one-folder EXE from $SpecFile ..." -ForegroundColor Cyan
python -m PyInstaller -y "$SpecFile"

$distFolder = Join-Path (Get-Location) "dist\alyPyAcquisition_ionin"
if (-not (Test-Path $distFolder)) {
    throw "Build did not produce expected folder: $distFolder"
}

# Ensure editable config exists next to EXE (preferred runtime location).
$internalConfig = Join-Path $distFolder "_internal\config.ini"
$rootConfig = Join-Path $distFolder "config.ini"
if ((Test-Path $internalConfig) -and (-not (Test-Path $rootConfig))) {
    Copy-Item -Path $internalConfig -Destination $rootConfig -Force
}

$zipFile = Join-Path (Get-Location) "dist\alyPyAcquisition_ionin_bundle.zip"
if (Test-Path $zipFile) {
    Remove-Item -Path $zipFile -Force
}

Write-Host "Creating deploy ZIP..." -ForegroundColor Cyan
Compress-Archive -Path "$distFolder\*" -DestinationPath $zipFile -Force

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Copy this folder to calibration PC: $distFolder"
Write-Host "Or copy this zip: $zipFile"
Write-Host ""
Write-Host "On calibration PC, set in config.ini:"
Write-Host "[IonIn]"
Write-Host "enabled = true"
