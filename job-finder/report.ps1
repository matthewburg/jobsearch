# Opens the job report (http://127.0.0.1:8765), starting its server if needed.
#
#   powershell -ExecutionPolicy Bypass -File job-finder\report.ps1          # start if needed + open the browser
#   powershell -ExecutionPolicy Bypass -File job-finder\report.ps1 -Stop    # stop the server
#
# The server runs in the background with no window (pythonw), so you can close
# this terminal. It keeps running until you log off, restart, or use -Stop.
# Only the report page needs it: the collector, the daily review, and the MCP
# tools all work without it.
# Mac/Linux: python3 -I job-finder/app/server.py, then open the URL.

param([switch]$Stop)

$Url = "http://127.0.0.1:8765"
$Server = Join-Path $PSScriptRoot "app\server.py"

function Test-Report {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "$Url/api/runs" | Out-Null; return $true }
    catch { return $false }
}

$Running = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like "*app\server.py*" }

if ($Stop) {
    if (-not $Running) { Write-Output "The report server isn't running."; return }
    $Running | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Write-Output "Stopped the report server."
    return
}

if (-not (Test-Report)) {
    $Pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
    if (-not $Pythonw) { Write-Error "pythonw not found. Install Python 3.10+ from python.org and try again."; exit 1 }
    Start-Process -FilePath $Pythonw -ArgumentList "-I", "`"$Server`"" -WindowStyle Hidden
    foreach ($i in 1..20) {
        Start-Sleep -Milliseconds 250
        if (Test-Report) { break }
    }
    if (-not (Test-Report)) {
        Write-Error "The report server didn't start. Check today's log in job-finder\state\logs."
        exit 1
    }
    Write-Output "Started the report server."
}

Write-Output "Job report: $Url"
Start-Process $Url
