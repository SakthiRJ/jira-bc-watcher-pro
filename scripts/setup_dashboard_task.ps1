# Registers a Windows Scheduled Task that keeps the dashboard running.
#
# The dashboard app has its OWN built-in scheduler, so this task does NOT need
# an interval; it just launches the app at logon (and restarts it if it stops).
# All timing (scan interval + end-of-day digest time) is then configured live
# from the dashboard UI - no restart needed.
#
# Usage (from this folder):
#   powershell -ExecutionPolicy Bypass -File .\setup_dashboard_task.ps1
# Remove it later with:
#   Unregister-ScheduledTask -TaskName "JiraBCDashboard" -Confirm:$false
param(
    [string]$TaskName = "JiraBCDashboard"
)

$dir = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot "run_dashboard.ps1"

if (-not (Test-Path (Join-Path $dir ".venv\Scripts\python.exe"))) {
    Write-Error "Virtual environment not found. Create it first: C:\python.exe -m venv .venv"
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`"" `
    -WorkingDirectory $dir

# Start at logon and again every day (in case it was stopped), keep it alive.
$trigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -RestartCount 3 `
    -ExecutionTimeLimit (New-TimeSpan -Days 0)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Jira business-critical dashboard (auto-scan + end-of-day digest)" `
    -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' to start the dashboard at logon."
Write-Host "Dashboard: http://127.0.0.1:5000"
Write-Host "Logs: $(Join-Path $dir 'dashboard.log')"
Write-Host "Start it now:  Start-ScheduledTask -TaskName '$TaskName'"
