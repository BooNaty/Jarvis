# Creates JARVIS desktop shortcut (pythonw directly, no VBS)
$ErrorActionPreference = "Stop"

$JarvisDir = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $JarvisDir "venv\Scripts\pythonw.exe"
$MainPy = Join-Path $JarvisDir "main.py"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "JARVIS.lnk"
$StopShortcut = Join-Path $Desktop "JARVIS STOP.lnk"
$StopBat = Join-Path $PSScriptRoot "stop_jarvis.bat"

if (-not (Test-Path $Pythonw)) {
    Write-Host "venv not found. Run first:" -ForegroundColor Red
    Write-Host "  cd `"$JarvisDir`""
    Write-Host "  python -m venv venv"
    Write-Host "  .\venv\Scripts\activate"
    Write-Host "  pip install -r requirements.txt"
    exit 1
}

$WshShell = New-Object -ComObject WScript.Shell

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Pythonw
$Shortcut.Arguments = "`"$MainPy`" --minimized"
$Shortcut.WorkingDirectory = $JarvisDir
$Shortcut.Description = "JARVIS Voice Assistant"
$Shortcut.Save()

$Stop = $WshShell.CreateShortcut($StopShortcut)
$Stop.TargetPath = $StopBat
$Stop.WorkingDirectory = $PSScriptRoot
$Stop.Description = "Stop JARVIS"
$Stop.Save()

Write-Host "Done: $ShortcutPath" -ForegroundColor Green
Write-Host "Emergency stop: $StopShortcut" -ForegroundColor Yellow
