<#
.SYNOPSIS
    Refresh the report automatically with Windows Task Scheduler.

.DESCRIPTION
    Registers a scheduled task that rebuilds the report and writes report.html.
    This is the private alternative to the GitHub Pages workflow: nothing is
    published, nothing leaves the machine, and report.html is simply up to date the
    next time you open it.

    The task runs as you, only when you are logged on, and does not wake the machine.
    A missed run is retried once the machine is back - a meta report is not worth
    waking a laptop for.

    Requires .\scripts\setup.ps1 to have been run: the task calls .venv's Python by
    absolute path, so it does not depend on PATH inside the scheduler's environment.

.EXAMPLE
    .\scripts\schedule.ps1 -Source inkdecks -At 06:30
    Rebuild from inkdecks every day at 06:30.

.EXAMPLE
    .\scripts\schedule.ps1 -Source inkdecks -Weekly Monday -At 07:00 -Days 30
    Once a week instead - kinder to the source, and the meta does not move daily.

.EXAMPLE
    .\scripts\schedule.ps1 -Remove
#>
[CmdletBinding()]
param(
    [ValidateSet("topdeck", "inkdecks", "local")]
    [string]$Source = "inkdecks",
    [string]$At = "06:30",
    [ValidateSet("", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")]
    [string]$Weekly = "",
    [int]$Days = 30,
    [int]$Top = 32,
    [string]$TaskName = "LorcanaMetaReport",
    [switch]$Remove
)

# Not "Stop": in Windows PowerShell anything a native command writes to stderr
# becomes a NativeCommandError, which would abort the script over a pip notice.
# Native failures are caught by $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed the scheduled task '$TaskName'." -ForegroundColor Green
    }
    else {
        Write-Host "No scheduled task named '$TaskName'."
    }
    exit 0
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "No .venv found. Run .\scripts\setup.ps1 first," -ForegroundColor Yellow
    Write-Host "so the task can call Python by absolute path instead of trusting PATH."
    exit 1
}

if ($Source -eq "inkdecks" -and [string]::IsNullOrWhiteSpace($env:INKDECKS_CONSENT)) {
    Write-Host ""
    Write-Host "INKDECKS_CONSENT is not set for your user account." -ForegroundColor Yellow
    Write-Host "  The task inherits your user environment, so set it permanently:"
    Write-Host '    [Environment]::SetEnvironmentVariable("INKDECKS_CONSENT", "1", "User")'
    Write-Host "  Then run this script again."
    Write-Host ""
    exit 1
}

# One PowerShell invocation that builds, then bundles. -Bundle already does both, and
# keeping the task to a single command means one exit code to read in the history.
$buildScript = Join-Path $root "scripts\build.ps1"
$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$buildScript`"",
    "-Source", $Source,
    "-Days", $Days,
    "-Top", $Top,
    "-Bundle"
)

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ($arguments -join " ") `
    -WorkingDirectory $root

$trigger = if ($Weekly) {
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekly -At $At
}
else {
    New-ScheduledTaskTrigger -Daily -At $At
}

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -MultipleInstances IgnoreNew

# Runs as you, interactively, so it inherits INKDECKS_CONSENT from your user
# environment and never needs a stored password.
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Rebuilds the private Lorcana meta report and writes report.html." `
    -Force | Out-Null

$when = if ($Weekly) { "every $Weekly at $At" } else { "daily at $At" }
Write-Host ""
Write-Host "Registered '$TaskName' - $when, source: $Source, last $Days days, top $Top." -ForegroundColor Green
Write-Host ""
Write-Host "  Run it now:      Start-ScheduledTask -TaskName $TaskName"
Write-Host "  See the result:  Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "  Remove it:       .\scripts\schedule.ps1 -Remove"
Write-Host ""
Write-Host "The report lands at $root\report.html - make a shortcut to it."
if ($Source -eq "inkdecks") {
    Write-Host "A full inkdecks build is slow on purpose; the first one may take ~30 min." -ForegroundColor DarkGray
}
