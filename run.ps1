$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw 'The project Python environment is missing. Run .\setup.ps1 -InstallDependencies first.'
}

& $PythonPath -c "import sys, site, fastapi, uvicorn, pymupdf, docx, pptx, openpyxl, PIL, multipart; assert sys.version_info >= (3, 11); assert not site.ENABLE_USER_SITE; assert pymupdf.__version__.startswith('1.'), pymupdf.__version__"
if ($LASTEXITCODE -ne 0) {
    throw 'The required Python packages are missing or PyMuPDF is not version 1.x. Read requirements.txt and ask before installing packages.'
}

if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'frontend\node_modules'))) {
    throw 'Frontend packages are missing. Run .\setup.ps1 -InstallDependencies first.'
}

# Always rebuild so a pulled branch or a recent source edit cannot leave a
# stale committed/local dist bundle serving an older interface.
Push-Location (Join-Path $ProjectRoot 'frontend')
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
finally {
    Pop-Location
}

Push-Location $ProjectRoot
try {
    & $PythonPath -m uvicorn app:app --host 127.0.0.1 --port 8001
}
finally {
    Pop-Location
}
