[CmdletBinding()]
param(
    [switch]$InstallDependencies
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$EnvironmentPath = Join-Path $ProjectRoot '.venv'
$PythonPath = Join-Path $EnvironmentPath 'Scripts\python.exe'
$RequirementsPath = Join-Path $ProjectRoot 'requirements.txt'
$FrontendPath = Join-Path $ProjectRoot 'frontend'

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    throw 'Python 3.11 or newer is required. Install Python, then run this script again.'
}

& $PythonCommand.Source -c "import sys; assert sys.version_info >= (3, 11), sys.version"
if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.11 or newer is required.'
}

$NodeCommand = Get-Command node -ErrorAction SilentlyContinue
$NpmCommand = Get-Command npm -ErrorAction SilentlyContinue
if (-not $NodeCommand -or -not $NpmCommand) {
    throw 'Node.js 22.12+ and npm 10+ are required. Install Node.js, then run this script again.'
}

$NodeVersion = & $NodeCommand.Source -p 'process.versions.node'
$NodeParts = $NodeVersion.Split('.') | ForEach-Object { [int]$_ }
if (($NodeParts[0] -lt 22) -or (($NodeParts[0] -eq 22) -and ($NodeParts[1] -lt 12))) {
    throw "Node.js 22.12 or newer is required. Found $NodeVersion."
}

$NpmVersion = & $NpmCommand.Source --version
$NpmParts = $NpmVersion.Split('.') | ForEach-Object { [int]$_ }
if ($NpmParts[0] -lt 10) {
    throw "npm 10 or newer is required. Found $NpmVersion."
}

if (-not (Test-Path -LiteralPath $PythonPath)) {
    & $PythonCommand.Source -m venv $EnvironmentPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not create the project virtual environment.'
    }
}

if ($InstallDependencies) {
    Write-Host 'Installing only the pinned Python runtime dependencies in requirements.txt...'
    & $PythonPath -m pip install -r $RequirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Python dependency installation failed. See the pip output above.'
    }

    Write-Host 'Installing the exact frontend dependency tree from package-lock.json...'
    Push-Location $FrontendPath
    try {
        & $NpmCommand.Source ci
        if ($LASTEXITCODE -ne 0) {
            throw 'Frontend dependency installation failed. See the npm output above.'
        }
    }
    finally {
        Pop-Location
    }
}

& $PythonPath -c "import sys, fastapi, uvicorn, pydantic, multipart, pymupdf, docx, pptx, openpyxl, PIL; assert sys.version_info >= (3, 11), sys.version"
if ($LASTEXITCODE -ne 0) {
    throw 'Python dependencies are missing. On a new clone, run .\setup.ps1 -InstallDependencies.'
}

if (-not (Test-Path -LiteralPath (Join-Path $FrontendPath 'node_modules'))) {
    throw 'Frontend packages are missing. Run .\setup.ps1 -InstallDependencies to install the locked packages.'
}

Write-Host 'Context Studio dependencies are ready.'
Write-Host 'Python runtime packages: requirements.txt'
Write-Host 'Frontend packages: frontend/package.json + frontend/package-lock.json'
Write-Host 'No OCR executable, model weights, hosted service, or paid software is required.'
