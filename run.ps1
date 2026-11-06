$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $PythonPath)) {
    $PythonCommand = Get-Command python -ErrorAction Stop
    $PythonPath = $PythonCommand.Source
}

& $PythonPath -c "import sys, fastapi, uvicorn, pymupdf, docx, pptx, openpyxl, PIL, multipart; assert sys.version_info >= (3, 11); assert pymupdf.__version__.startswith('1.'), pymupdf.__version__"
if ($LASTEXITCODE -ne 0) {
    throw 'The required Python packages are missing or PyMuPDF is not version 1.x. Read requirements.txt and ask before installing packages.'
}

if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'dist\index.html'))) {
    Push-Location (Join-Path $ProjectRoot 'frontend')
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    }
    finally {
        Pop-Location
    }
}

Push-Location $ProjectRoot
try {
    & $PythonPath -m uvicorn app:app --host 127.0.0.1 --port 8001
}
finally {
    Pop-Location
}
