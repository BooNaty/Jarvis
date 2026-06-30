# Emergency stop — kills JARVIS and clears lock files
$ErrorActionPreference = "SilentlyContinue"
$JarvisDir = Split-Path -Parent $PSScriptRoot
$LockFile = Join-Path $JarvisDir "config\.jarvis.lock"

$killed = 0
Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -like '*\jarvis\main.py*' -or
            $_.CommandLine -like '*start_jarvis.vbs*' -or
            ($_.Name -eq 'wscript.exe' -and $_.CommandLine -like '*jarvis*')
        )
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        $killed++
    }

if (Test-Path $LockFile) { Remove-Item $LockFile -Force }

if ($killed -gt 0) {
    Write-Host "Stopped $killed process(es). JARVIS is off." -ForegroundColor Green
} else {
    Write-Host "No JARVIS processes found. Lock cleared." -ForegroundColor Yellow
}
