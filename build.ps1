# Build ClipDeck.exe (single file, no console window).
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "Regenerating icon..." -ForegroundColor Cyan
& $py make_icon.py

Write-Host "Building exe with PyInstaller..." -ForegroundColor Cyan
& $py -m PyInstaller `
    --noconfirm --clean --onefile --windowed `
    --uac-admin `
    --name ClipDeck `
    --icon "assets\icon.ico" `
    --add-data "assets;assets" `
    --collect-all customtkinter `
    --hidden-import pyaudiowpatch `
    clipdeck.py

Write-Host ""
Write-Host "Done -> dist\ClipDeck.exe" -ForegroundColor Green
Write-Host "(ffmpeg is downloaded automatically on first run.)" -ForegroundColor DarkGray
