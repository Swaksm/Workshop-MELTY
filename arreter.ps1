$ErrorActionPreference = "Continue"
$racine = $PSScriptRoot

$processus = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -like "*vision*app.py*") -or
    ($_.CommandLine -like "*frontend*" -and $_.CommandLine -like "*run dev*") -or
    ($_.CommandLine -like "*vite*" -and $_.CommandLine -like "*frontend*")
}
foreach ($p in $processus) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "Arrêté : $($p.Name) ($($p.ProcessId))"
}

Set-Location $racine
cmd /c "docker compose down"
Write-Host "Stack Docker arrêtée (les données sont conservées)."
