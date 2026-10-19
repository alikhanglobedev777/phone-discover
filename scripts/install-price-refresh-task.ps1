# One-time, opt-in installation of the two-day native Windows timer.
# Run in a regular PowerShell terminal as the account that owns the project.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$runner = Join-Path $PSScriptRoot 'run-price-refresh.cmd'
if (-not (Test-Path $python)) { throw 'Run py dev.py first to set up the Python environment.' }
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/d /c "' + $runner + '"') -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -DaysInterval 2 -At 9:00AM
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'PhoneDiscoverPriceRefresh' -Action $action -Trigger $trigger -Principal $principal -Description 'Refresh permitted PKR mobile price evidence every two days' -Force | Out-Null
Write-Host 'Scheduled: PhoneDiscoverPriceRefresh, every 2 days at 9 AM (logged-in Windows account).' -ForegroundColor Green
Write-Host 'Requires Windows login, network access, Gemini quota, and a running PostgreSQL database.'
