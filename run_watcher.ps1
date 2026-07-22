# Wrapper the scheduled task runs. Executes one watcher cycle and appends
# output to watcher.log next to this script.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\watcher.py" *>> "$PSScriptRoot\watcher.log"
