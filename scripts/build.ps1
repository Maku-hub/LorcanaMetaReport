<#
.SYNOPSIS
    Build the meta report on Windows.

.DESCRIPTION
    A thin wrapper around `lorcana-meta build` that checks the things people get
    wrong on a fresh machine: the project not installed into .venv, and consent for
    the inkdecks source not recorded. Everything it does can be done by hand - see
    the README.

.EXAMPLE
    .\scripts\build.ps1
    Last 30 days of Core Constructed, top 32.

.EXAMPLE
    .\scripts\build.ps1 -Days 60 -Top 8 -MinPlayers 32
    Last 60 days, top 8 finishes, events of 32+ players.

.EXAMPLE
    .\scripts\build.ps1 -Sample
    Build from the synthetic sample field - no permission, no network, seconds.
#>
[CmdletBinding()]
param(
    [int]$Days = 30,
    [int]$Top = 32,
    [ValidateSet("Core Constructed", "Infinity Constructed")]
    [string]$Format = "Core Constructed",
    # Ignore events smaller than this. For inkdecks it filters on the listing row,
    # so it saves the deck-page requests rather than making and discarding them.
    [int]$MinPlayers = 0,
    [double]$ClusterThreshold = 0.60,
    [ValidateSet("inkdecks", "local")]
    [string]$Source = "inkdecks",
    # Which of inkdecks' tabs to read. Ignored by the other sources.
    [ValidateSet("core", "infinity", "poorcana", "all")]
    [string]$Category = "core",
    [switch]$Sample,
    [switch]$RefreshCards,
    [switch]$Bundle
)

# Not "Stop": in Windows PowerShell anything a native command writes to stderr
# becomes a NativeCommandError, which would abort the script over a pip notice.
# Native failures are caught by $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

# Prefer the virtual environment setup.ps1 makes, so a scheduled task does not depend
# on whatever `python` happens to mean in its environment.
function Get-ProjectPython {
    $venv = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    if (Test-Path $venv) { return (Resolve-Path $venv).Path }
    $system = Get-Command python -ErrorAction SilentlyContinue
    if ($system) { return $system.Source }
    throw "No Python found. Run .\scripts\setup.ps1 first."
}

$python = Get-ProjectPython

& $python -c "import lorcana_meta" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "The project is not installed for $python." -ForegroundColor Yellow
    Write-Host "  Run .\scripts\setup.ps1 first."
    exit 1
}

$buildArgs = @(
    "build",
    "--last", $Days,
    "--top", $Top,
    "--format", $Format,
    "--cluster-threshold", $ClusterThreshold
)
if ($MinPlayers -gt 0) { $buildArgs += @("--min-players", $MinPlayers) }
if ($RefreshCards) { $buildArgs += "--refresh-cards" }

if ($Sample) {
    Write-Host "Generating the synthetic sample field..." -ForegroundColor Cyan
    & $python tools/generate_sample_decks.py
    $buildArgs += @("--source", "local")
}
elseif ($Source -eq "inkdecks") {
    if ([string]::IsNullOrWhiteSpace($env:INKDECKS_CONSENT)) {
        Write-Host ""
        Write-Host "The inkdecks source needs their written permission." -ForegroundColor Yellow
        Write-Host "  Their terms prohibit automated access without prior written consent,"
        Write-Host "  so this flag is you stating you have it."
        Write-Host ""
        Write-Host "  Have it? Set both - the first covers this window, the second every"
        Write-Host "  future one including scheduled runs:" -ForegroundColor Cyan
        Write-Host '      $env:INKDECKS_CONSENT = "1"'
        Write-Host '      [Environment]::SetEnvironmentVariable("INKDECKS_CONSENT", "1", "User")'
        Write-Host "  Then run this command again."
        Write-Host ""
        Write-Host "  Not yet? Ask them, or copy lists by hand:"
        Write-Host "      python tools/import_pasted_decks.py my-notes.txt"
        Write-Host ""
        exit 1
    }
    Write-Host "Building from inkdecks.com - deliberately slow, and cached." -ForegroundColor Cyan
    Write-Host "This report is marked private and cannot be published." -ForegroundColor Yellow
    Write-Host "Category: $Category" -ForegroundColor Cyan
    $buildArgs += @("--source", "inkdecks", "--inkdecks-consent", "--inkdecks-category", $Category)
}
elseif ($Source -eq "local") {
    $buildArgs += @("--source", "local")
}

& $python -m lorcana_meta @buildArgs
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Report written to site\data\meta.json" -ForegroundColor Green

if ($Bundle) {
    & $python tools/bundle_report.py
    if ($LASTEXITCODE -ne 0) { exit 1 }
    Write-Host ""
    Write-Host "Double-click report.html to read it - no server, nothing leaves this machine." -ForegroundColor Green
}
else {
    Write-Host "Preview it with:      .\scripts\serve.ps1"
    Write-Host "Or make one private file:  .\scripts\build.ps1 -Bundle"
}
