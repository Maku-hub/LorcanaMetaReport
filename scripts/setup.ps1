<#
.SYNOPSIS
    One-time setup on Windows.

.DESCRIPTION
    Creates a virtual environment in .venv, installs the project into it, and checks
    that everything a build needs is present. Run it once after cloning; build.ps1 and
    serve.ps1 find .venv on their own afterwards.

    A virtual environment rather than your system Python, because this installs
    beautifulsoup4 and optionally cloudscraper, and a personal tool has no business
    changing what your other Python projects see.

.EXAMPLE
    .\scripts\setup.ps1
    Core install plus the inkdecks source.

.EXAMPLE
    .\scripts\setup.ps1 -WithCloudscraper
    Also install cloudscraper. Only worth it if inkdecks starts returning 403 - a 429
    is a rate limit and cloudscraper does not help with those.

.EXAMPLE
    .\scripts\setup.ps1 -Minimal
    No HTML parsing. TopDeck and local decklists only.
#>
[CmdletBinding()]
param(
    [switch]$Minimal,
    [switch]$WithCloudscraper,
    [switch]$Recreate
)

# Deliberately NOT "Stop". In Windows PowerShell, anything a native command writes to
# stderr becomes a NativeCommandError, so `pip` printing a notice would abort the
# script even though it exited 0. Native failures are caught by $LASTEXITCODE below.
$ErrorActionPreference = "Continue"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root
$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"

function Fail($message) {
    Write-Host ""
    Write-Host $message -ForegroundColor Red
    exit 1
}

# -- Python ------------------------------------------------------------------

$system = Get-Command python -ErrorAction SilentlyContinue
if (-not $system) {
    Fail "Python is not on PATH. Install 3.10+ from https://python.org and tick 'Add python.exe to PATH'."
}

$version = (& python -c "import sys; print('%d.%d' % sys.version_info[:2])")
if ($LASTEXITCODE -ne 0) { Fail "Could not run python." }
Write-Host "Python $version at $($system.Source)"

$parts = "$version".Split(".")
if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) {
    Fail "Python 3.10 or newer is required (found $version)."
}

# -- virtual environment -----------------------------------------------------

if ($Recreate -and (Test-Path $venv)) {
    Write-Host "Removing the existing .venv..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venv
}

if (-not (Test-Path $python)) {
    Write-Host "Creating .venv..." -ForegroundColor Cyan
    & python -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $python)) {
        Fail "Could not create the virtual environment."
    }
}

$target = if ($Minimal) { "." } elseif ($WithCloudscraper) { ".[cloudscraper]" } else { ".[inkdecks]" }
Write-Host "Installing $target ..." -ForegroundColor Cyan

# No pip self-upgrade here. On Windows, pip replacing its own files mid-run leaves a
# half-installed pip ("No module named 'pip._internal.cli'"), and the venv ships with
# a working one anyway. Not worth breaking setup for a version bump.
# --disable-pip-version-check keeps pip off stderr; without it PowerShell wraps its
# "a new release is available" notice in a NativeCommandError that reads like a
# failure right after we print "Ready".
& $python -m pip install -e $target --quiet --disable-pip-version-check --no-warn-script-location
if ($LASTEXITCODE -ne 0) { Fail "pip install failed. Re-run with -Verbose to see why." }

# -- verify ------------------------------------------------------------------

Write-Host ""
Write-Host "Checking the install:" -ForegroundColor Cyan

& $python -c "import lorcana_meta; print('  package       ' + lorcana_meta.__version__)"
if ($LASTEXITCODE -ne 0) { Fail "The package did not import." }

if (-not $Minimal) {
    & $python -c "import bs4; print('  beautifulsoup ' + bs4.__version__)"
    if ($LASTEXITCODE -ne 0) { Fail "beautifulsoup4 did not import." }
}
if ($WithCloudscraper) {
    & $python -c "import cloudscraper; print('  cloudscraper  installed')"
    if ($LASTEXITCODE -ne 0) { Fail "cloudscraper did not import." }
}

# The card database is the one network call every build makes. Fetch it now rather
# than discovering a proxy problem at 6am inside a scheduled task.
& $python -c "from lorcana_meta.cards import CardIndex; print('  card data     ' + str(len(CardIndex.load())) + ' printings cached')"
if ($LASTEXITCODE -ne 0) {
    Fail "Could not reach lorcana-api.com for the card database. Check your connection or proxy."
}

Write-Host ""
Write-Host "Ready." -ForegroundColor Green
Write-Host ""
Write-Host "  .\scripts\build.ps1 -Sample -Bundle           try it on sample data"
Write-Host "  .\scripts\build.ps1 -Source inkdecks -Bundle  build from inkdecks"
Write-Host "  .\scripts\schedule.ps1                        refresh it automatically"
