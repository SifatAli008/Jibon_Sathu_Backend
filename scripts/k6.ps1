# Run k6 without relying on PATH (common on Windows after winget install).
# Usage (from repo root): .\scripts\k6.ps1 run k6/health.js
# Optional: $env:K6_EXE = "D:\tools\k6.exe"

$ErrorActionPreference = "Stop"
# Build as array of strings (pipeline of one string would make [0] = first char!)
$paths = @(
    $env:K6_EXE
    "${env:ProgramFiles}\k6\k6.exe"
    "${env:ProgramFiles(x86)}\k6\k6.exe"
    "$env:LOCALAPPDATA\Programs\k6\k6.exe"
)
$candidates = [System.Collections.ArrayList]@()
foreach ($p in $paths) {
    if ($p -and (Test-Path -LiteralPath $p)) {
        [void]$candidates.Add($p)
    }
}

if ($candidates.Count -eq 0) {
    Write-Error @"
k6 executable not found. Install with:
  winget install --id GrafanaLabs.k6 -e

Then close and reopen this terminal (PATH update), or set:
  `$env:K6_EXE = 'C:\Path\To\k6.exe'
"@
    exit 1
}

$exe = [string]$candidates[0]
& $exe @args
exit $LASTEXITCODE
exit $LASTEXITCODE
