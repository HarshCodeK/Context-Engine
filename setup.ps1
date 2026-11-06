[CmdletBinding()]
param(
    [switch]$InstallDependencies,
    [switch]$InstallMachinePrerequisites
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$EnvironmentPath = Join-Path $ProjectRoot '.venv'
$PythonPath = Join-Path $EnvironmentPath 'Scripts\python.exe'
$RequirementsPath = Join-Path $ProjectRoot 'requirements.txt'
$FrontendPath = Join-Path $ProjectRoot 'frontend'

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
$NodeCommand = Get-Command node -ErrorAction SilentlyContinue
$NpmCommand = Get-Command npm -ErrorAction SilentlyContinue
$TesseractCommand = Get-Command tesseract -ErrorAction SilentlyContinue

if ($InstallMachinePrerequisites) {
    $WingetCommand = Get-Command winget -ErrorAction SilentlyContinue
    $MissingCorePrerequisites = (-not $PythonCommand -or -not $NodeCommand -or -not $NpmCommand)
    if ($MissingCorePrerequisites -and -not $WingetCommand) {
        throw 'Python/Node.js are missing and winget is unavailable. Install Python 3.11+ and Node.js 22.12+ manually, reopen PowerShell, then rerun setup.'
    }

    $InstalledMachineTool = $false
    if ($WingetCommand) {
        if (-not $PythonCommand) {
            Write-Host 'Installing Python 3.13 using Windows Package Manager...'
            & $WingetCommand.Source install --id Python.Python.3.13 --exact --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { throw 'Python installation failed through winget.' }
            $InstalledMachineTool = $true
        }
        if (-not $NodeCommand -or -not $NpmCommand) {
            Write-Host 'Installing Node.js LTS using Windows Package Manager...'
            & $WingetCommand.Source install --id OpenJS.NodeJS.LTS --exact --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { throw 'Node.js installation failed through winget.' }
            $InstalledMachineTool = $true
        }
        if (-not $TesseractCommand) {
            Write-Host 'Installing the optional Tesseract OCR engine...'
            & $WingetCommand.Source install --id tesseract-ocr.tesseract --exact --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {
                Write-Warning 'Tesseract could not be installed. OCR remains optional; image uploads will show an OCR-unavailable notice.'
            }
            else {
                $InstalledMachineTool = $true
            }
        }
    }
    elseif (-not $TesseractCommand) {
        Write-Warning 'winget is unavailable, so optional Tesseract OCR was not installed. Image uploads remain supported with an OCR-unavailable notice.'
    }
    if ($InstalledMachineTool) {
        throw 'One or more machine prerequisites were installed. Close and reopen PowerShell so PATH refreshes, then rerun .\setup.ps1 -InstallDependencies.'
    }
}

if (-not $PythonCommand) {
    throw 'Python 3.11 or newer is required. Install Python, then run this script again.'
}

& $PythonCommand.Source -c "import sys; assert sys.version_info >= (3, 11), sys.version"
if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.11 or newer is required.'
}

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

# Repair virtual environments created by older setup scripts with
# --system-site-packages. The project environment must not silently borrow
# packages from the user's global Python installation.
$VenvConfigPath = Join-Path $EnvironmentPath 'pyvenv.cfg'
if (Test-Path -LiteralPath $VenvConfigPath) {
    $VenvConfig = Get-Content -LiteralPath $VenvConfigPath -Raw
    if ($VenvConfig -match '(?im)^include-system-site-packages\s*=\s*true\s*$') {
        Write-Host 'Replacing a non-isolated Python environment with a clean project-only .venv...'
        Remove-Item -LiteralPath $EnvironmentPath -Recurse -Force
    }
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

& $PythonPath -c "import sys, site, fastapi, uvicorn, pydantic, multipart, pymupdf, docx, pptx, openpyxl, PIL; assert sys.version_info >= (3, 11), sys.version; assert not site.ENABLE_USER_SITE, 'The project venv must not expose global user packages'"
if ($LASTEXITCODE -ne 0) {
    throw 'Python dependencies are missing. On a new clone, run .\setup.ps1 -InstallDependencies.'
}

if (-not (Test-Path -LiteralPath (Join-Path $FrontendPath 'node_modules'))) {
    throw 'Frontend packages are missing. Run .\setup.ps1 -InstallDependencies to install the locked packages.'
}

Write-Host 'Context Studio dependencies are ready.'
Write-Host 'Python runtime packages: requirements.txt'
Write-Host 'Frontend packages: frontend/package.json + frontend/package-lock.json'
if (Get-Command tesseract -ErrorAction SilentlyContinue) {
    Write-Host 'Optional OCR engine: Tesseract is available.'
}
else {
    Write-Host 'Optional OCR engine: Tesseract is not installed; image uploads remain supported with an OCR-unavailable notice.'
}
Write-Host 'No model weights, hosted service, or paid software is required.'
