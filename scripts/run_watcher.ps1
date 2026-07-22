# Wrapper the scheduled task runs. Executes one watcher cycle and appends
# output to watcher.log next to this script.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -Path $root
& "$root\.venv\Scripts\python.exe" -m bcwatcher.watcher *>> "$root\watcher.log"
