[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $git = Get-Command git -ErrorAction Stop
    & $git.Source rev-parse --show-toplevel *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Run this check from inside the Context Studio Git repository.' }

    $tracked = @(& $git.Source ls-files)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect tracked Git files.' }
    $staged = @(& $git.Source diff --cached --name-only --diff-filter=ACMR)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect staged Git files.' }
    $paths = @($tracked + $staged | Sort-Object -Unique)

    $blockedPath = '(?i)(^|/)(data|\.venv|venv|node_modules|dist|source_blobs|uploads|exports|artifacts|logs|private|user-data|test-results|playwright-report)(/|$)'
    $blockedFile = '(?i)(^|/)(\.env($|\.(?!example$|template$))|id_rsa|id_ed25519|credentials\.json|secrets?\.(json|ya?ml|toml))|\.(sqlite3?|db|db-wal|db-shm|pem|key|p12|pfx|log)$'
    $unsafe = @($paths | Where-Object { $_ -match $blockedPath -or $_ -match $blockedFile })

    if ($unsafe.Count -gt 0) {
        Write-Host 'BLOCKED: Git contains paths that should remain local/private:' -ForegroundColor Red
        $unsafe | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        throw 'Remove these files from Git tracking/staging and review .gitignore before pushing.'
    }

    Write-Host ("Git safety path check passed: {0} tracked/staged paths inspected." -f $paths.Count) -ForegroundColor Green
    Write-Host 'This checks filenames and locations only; inspect staged content for secrets and private data before every push.' -ForegroundColor Yellow
}
finally {
    Pop-Location
}
