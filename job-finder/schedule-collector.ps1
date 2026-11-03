# Registers the background collector with Windows Task Scheduler.
#
# Run it yourself in PowerShell (not through Claude):
#   powershell -ExecutionPolicy Bypass -File job-finder\schedule-collector.ps1
#   powershell -ExecutionPolicy Bypass -File job-finder\schedule-collector.ps1 -Time 06:45
#   powershell -ExecutionPolicy Bypass -File job-finder\schedule-collector.ps1 -Remove
#
# It runs daily as you, only while you're logged in, with no console window
# (pythonw). collect.py adds its own random start delay, so the real start
# time varies. If the computer was asleep or off at the trigger time, it runs
# when the computer is next available.
# Mac/Linux: add a cron line instead, e.g.
#   0 7 * * * cd /path/to/kit && python3 -I job-finder/collect.py

param(
    [string]$Time = "07:00",
    [switch]$Remove
)

$TaskName = "Job Finder Collector"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Removed '$TaskName'."
    return
}

$JobFinder = $PSScriptRoot
$Pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $Pythonw) {
    Write-Output "pythonw not found on PATH. Install Python 3.11+ from python.org and try again."
    exit 1
}

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "-I `"$JobFinder\collect.py`"" -WorkingDirectory $JobFinder
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 5) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Job finder: one human-paced collection session a day (read-only, logged out, guarded)." -Force | Out-Null

Write-Output "Registered '$TaskName': daily at $Time (plus a random start delay), using $Pythonw."
Write-Output "Watch a run with: python -I job-finder\guard\watch.py"
