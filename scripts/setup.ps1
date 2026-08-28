<#
.SYNOPSIS
    One-time setup on Windows.

.DESCRIPTION
    Creates a virtual environment in .venv, installs the project into it, and checks
    that everything a build needs is present. Run it once after cloning; build.ps1 and
    serve.ps1 find .venv on their own afterwards.

    A virtual environment rather than your system Python, because this installs an
    HTML parser and a browser-fingerprint HTTP client, and a personal tool has no
    business changing what your other Python projects see. It is also why a bare
    "pip install <something>" in an un-activated shell appears to do nothing: it
    lands in whichever Python is on PATH, not in the one the build runs.

.EXAMPLE
    .\scripts\setup.ps1
    Everything: the pipeline plus the inkdecks source and its cloudscraper fallback.

.EXAMPLE
    .\scripts\setup.ps1 -Python 3.12
    Build the venv on a specific interpreter. Worth being explicit when you have
    several installed.

.EXAMPLE
    .\scripts\setup.ps1 -Minimal
    No HTML parsing. Local decklists only - the inkdecks source will refuse to run.
#>
[CmdletBinding()]
param(
    [switch]$Minimal,
    [switch]$Recreate,
    # "3.12", or a full path to a python.exe. Without it, the interpreter already in
    # use is reused, which keeps a working setup on the version it was built for.
    [string]$Python = ""
)

# Deliberately NOT "Stop". In Windows PowerShell, anything a native command writes to
# stderr becomes a NativeCommandError, so `pip` printing a notice would abort the
# script even though it exited 0. Native failures are checked explicitly below.
$ErrorActionPreference = "Continue"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root
$venv = Join-Path $root ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

function Fail($message) {
    Write-Host ""
    Write-Host $message -ForegroundColor Red
    exit 1
}

# Ask an interpreter about itself, and judge it by what it says rather than by
# $LASTEXITCODE. That variable can be stale from an earlier native call, and trusting
# it here once made this script fall back to the very venv it was about to delete -
# leaving no venv at all when creation then failed.
function Get-PythonAnswer($exe, $expression) {
    if (-not $exe) { return $null }
    $answer = (& $exe -c "import sys; print($expression)" 2>$null | Select-Object -First 1)
    if ($answer) { return "$answer".Trim() }
    return $null
}

# -- pick an interpreter -------------------------------------------------------

function Get-BasePython {
    # An explicit choice always wins.
    if ($Python) {
        if (Test-Path $Python) { return (Resolve-Path $Python).Path }
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $found = (& py "-$Python" -c "import sys; print(sys.executable)" 2>$null |
                Select-Object -First 1)
            if ($found -and (Test-Path $found.Trim())) { return $found.Trim() }
        }
        $installed = if (Get-Command py -ErrorAction SilentlyContinue) { (& py -0p) -join "; " } else { "none" }
        Fail "No interpreter matches -Python '$Python'. Installed: $installed"
    }

    # Otherwise reuse the interpreter already in play. A venv python reports its real
    # base, so this keeps an existing setup on the version it was built for.
    $onPath = Get-Command python -ErrorAction SilentlyContinue
    if ($onPath) {
        $base = Get-PythonAnswer $onPath.Source "sys.base_prefix"
        if ($base) {
            $exe = Join-Path $base "python.exe"
            if ((Test-Path $exe) -and -not $exe.StartsWith($venv, [StringComparison]::OrdinalIgnoreCase)) {
                return $exe
            }
        }
    }

    # Last resort: the launcher. `py -3` hands back the NEWEST installation, which is
    # not necessarily this project's - it silently moved a working 3.12 venv to 3.14
    # once. Acceptable when there is nothing else, wrong as a first choice.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $found = (& py -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
        if ($found -and (Test-Path $found.Trim())) { return $found.Trim() }
    }

    if ($onPath) { return $onPath.Source }
    return $null
}

$basePython = Get-BasePython
if (-not $basePython -or -not (Test-Path $basePython)) {
    Fail "Python is not on PATH. Install 3.10+ from https://python.org and tick 'Add python.exe to PATH'."
}

$version = Get-PythonAnswer $basePython "'%d.%d' % sys.version_info[:2]"
if (-not $version) { Fail "Could not run $basePython." }
Write-Host "Python $version at $basePython"

$parts = "$version".Split(".")
if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) {
    Fail "Python 3.10 or newer is required (found $version)."
}

# -- virtual environment -------------------------------------------------------

# Only now, with a verified interpreter in hand. Removing the venv first and finding
# out afterwards that nothing can build a new one leaves the project unusable.
if ($Recreate -and (Test-Path $venv)) {
    Write-Host "Removing the existing .venv..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venv
}

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating .venv..." -ForegroundColor Cyan
    & $basePython -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Fail "Could not create the virtual environment with $basePython."
    }
}

$target = if ($Minimal) { "." } else { ".[inkdecks]" }
Write-Host "Installing $target ..." -ForegroundColor Cyan

# No pip self-upgrade here. On Windows, pip replacing its own files mid-run leaves a
# half-installed pip ("No module named 'pip._internal.cli'"), and the venv ships with
# a working one anyway.
# --disable-pip-version-check keeps pip off stderr; without it PowerShell wraps its
# "a new release is available" notice in a NativeCommandError that reads like a
# failure right after we print "Ready".
& $venvPython -m pip install -e $target --quiet --disable-pip-version-check --no-warn-script-location
if ($LASTEXITCODE -ne 0) { Fail "pip install failed. Re-run with -Verbose to see why." }

# -- verify --------------------------------------------------------------------

Write-Host ""
Write-Host "Checking the install:" -ForegroundColor Cyan
Write-Host "  interpreter   $venvPython"

& $venvPython -c "import lorcana_meta; print('  package       ' + lorcana_meta.__version__)"
if ($LASTEXITCODE -ne 0) { Fail "The package did not import." }

if (-not $Minimal) {
    & $venvPython -c "import bs4; print('  beautifulsoup ' + bs4.__version__)"
    if ($LASTEXITCODE -ne 0) { Fail "beautifulsoup4 did not import." }

    # Checked here rather than discovered hours into a build, when the fallback
    # actually fires. It ships with the inkdecks extra precisely so that cannot
    # happen mid-run.
    & $venvPython -c "import curl_cffi; print('  curl_cffi     ' + curl_cffi.__version__)"
    if ($LASTEXITCODE -ne 0) { Fail "curl_cffi did not import." }
}

# The card database is the one network call every build makes. Fetch it now rather
# than discovering a proxy problem at 6am inside a scheduled task.
& $venvPython -c "from lorcana_meta.cards import CardIndex; print('  card data     ' + str(len(CardIndex.load())) + ' printings cached')"
if ($LASTEXITCODE -ne 0) {
    Fail "Could not reach lorcana-api.com for the card database. Check your connection or proxy."
}

Write-Host ""
Write-Host "Ready." -ForegroundColor Green
Write-Host ""
Write-Host "  .\scripts\build.ps1 -Sample -Bundle           try it on sample data"
Write-Host "  .\scripts\build.ps1 -Source inkdecks -Bundle  build from inkdecks"
Write-Host "  .\scripts\schedule.ps1                        refresh it automatically"
