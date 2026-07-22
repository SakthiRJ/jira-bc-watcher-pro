# Starts the dashboard + scheduler. Keep this process running: it serves the
# web dashboard AND drives the automatic scanning and end-of-day digest email.
# Output is appended to dashboard.log next to this script.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -Path $root
& "$root\.venv\Scripts\python.exe" -m bcwatcher.app *>> "$root\dashboard.log"
