# Registers a Windows Scheduled Task that runs the watcher every N minutes.
# Usage (from this folder):
#   powershell -ExecutionPolicy Bypass -File .\setup_task.ps1 -IntervalMinutes 5
# Remove it later with:
#   Unregister-ScheduledTask -TaskName "JiraBCWatcher" -Confirm:$false
param(
    [int]$IntervalMinutes = 5,
    [string]$TaskName = "JiraBCWatcher"
)

$dir = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot "run_watcher.ps1"

if (-not (Test-Path (Join-Path $dir ".venv\Scripts\python.exe"))) {
    Write-Error "Virtual environment not found. Create it first: C:\python.exe -m venv .venv"
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`"" `
    -WorkingDirectory $dir

# Fire once now, then repeat every N minutes for ~10 years.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Jira business-critical ticket watcher (progress updates + RCA emails)" `
    -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' to run every $IntervalMinutes minute(s)."
Write-Host "Logs: $(Join-Path $dir 'watcher.log')"
Write-Host "Run now for a test:  Start-ScheduledTask -TaskName '$TaskName'"
