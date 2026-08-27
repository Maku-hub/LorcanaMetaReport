<#
.SYNOPSIS
    Preview the site locally on Windows.

.DESCRIPTION
    Serves `site\` over HTTP and opens a browser. A plain file:// open will not work -
    the page fetches data/meta.json, and the browser blocks that on the file protocol.

.EXAMPLE
    .\scripts\serve.ps1

.EXAMPLE
    .\scripts\serve.ps1 -Port 9000 -NoBrowser
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$NoBrowser
)

# Not "Stop": in Windows PowerShell anything a native command writes to stderr
# becomes a NativeCommandError, which would abort the script over a pip notice.
# Native failures are caught by $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"

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
$root = Join-Path $PSScriptRoot ".."
$site = Join-Path $root "site"

if (-not (Test-Path (Join-Path $site "data\meta.json"))) {
    Write-Host "site\data\meta.json is missing - build a report first:" -ForegroundColor Yellow
    Write-Host "  .\scripts\build.ps1 -Sample"
    exit 1
}

$url = "http://127.0.0.1:$Port/"
Write-Host "Serving $site at $url  (Ctrl+C to stop)" -ForegroundColor Green

if (-not $NoBrowser) {
    # Give the server a moment to bind before the browser asks for the page.
    Start-Job -ScriptBlock {
        param($u)
        Start-Sleep -Seconds 1
        Start-Process $u
    } -ArgumentList $url | Out-Null
}

Set-Location $site
& $python -m http.server $Port --bind 127.0.0.1
