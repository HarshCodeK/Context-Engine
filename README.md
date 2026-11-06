# Context Studio

Context Studio is a local document-to-context workspace. It turns supported files into editable Markdown, keeps each extraction decision visible, records source evidence, and assembles selected files into a bounded context pack for AI tools.

The product is built around three Cs:

- **Cost:** measure bytes, processing time, approximate tokens, and external spend before making savings claims.
- **Computation:** choose and explain the extraction route.
- **Context:** preserve the useful information, its scope, and its source evidence.

## What works

- Upload up to 12 files per batch, with per-file and total-size limits.
- Extract PDF, DOCX, PPTX, XLSX, CSV, HTML, JSON, Markdown, text, and common image formats.
- Inspect extraction route, processing time, estimated tokens, warnings, source SHA-256, and block-level evidence.
- Preserve CSV tables as searchable table, column, record, and cell nodes with exact row/column provenance; inspect and filter them in the table explorer.
- Edit extracted Markdown in the browser and export a single file or a selected context pack.
- Save organization, project, and task rules in SQLite.
- Let local agents pull matching rules through a read-only HTTP endpoint or the included MCP server.
- Run without a hosted model or cloud storage.

## Current limits

- OCR is optional. If Tesseract is not installed, scanned PDF pages and images are reported as unreadable; native text extraction still works.
- Semantic summarization is not enabled. The current output is faithful extraction and structured context. A local model can be added after its quality and speed are benchmarked on this machine.
- CSV native cell indexing is capped at 5,000 cells per table to keep local knowledge-node fan-out bounded. The extracted Markdown table and immutable original remain available when the cap is reached.
- Audio/video transcription, GIF/TIFF, legacy `.doc`/`.xls`/`.ppt`, EPUB, and archive ingestion are not supported.
- The lightweight `/api/extract` route processes files in memory. The knowledge workspace's `/api/knowledge/ingest` route deliberately persists original bytes in the local content-addressed `data/source_blobs/` store and metadata/derived knowledge in `data/knowledge.sqlite3`; these local data files are excluded from Git.

## Requirements

- Python 3.11 or newer.
- Node.js 22.12 or newer and npm 10 or newer.
- Windows PowerShell 5.1 for the supplied setup and run scripts. The Python application itself uses cross-platform libraries.
- No API key, hosted service, OCR executable, local model, database server, or paid software is required.

## Set up a fresh clone

From the project root, run:

```powershell
.\setup.ps1 -InstallDependencies -InstallMachinePrerequisites
```

This checks for Python 3.11+ and Node.js 22.12+/npm 10+. With `-InstallMachinePrerequisites`, if Windows Package Manager (`winget`) is available, it installs missing Python 3.13, Node.js LTS, and the optional Tesseract OCR engine, then asks you to reopen PowerShell and rerun setup so the updated PATH is picked up. It creates an isolated `.venv` (and repairs an older environment if it was configured to expose global Python packages), installs the pinned Python runtime packages from `requirements.txt`, and installs the exact frontend dependency tree from `frontend/package-lock.json` using `npm ci`. It does not reuse unrelated global Python packages. Package installation requires an internet connection. No model weights or hosted services are downloaded.

For backend tests, install the additional test client dependency:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Run the application

After setup, start the production-style local app with:

```powershell
.\run.ps1
```

The script checks the project environment, rebuilds the frontend from the current source, and starts FastAPI on loopback. It does not install packages.

Start the backend from the project root:

```powershell
& .\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001
```

For the production-style local app, build the frontend first:

```powershell
cd frontend
npm run build
cd ..
& .\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001` in the Chat On Steroids internal browser.

For frontend development, keep the backend running on port 8001 and start Vite in a second terminal:

```powershell
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` requests to the local backend.

`requirements.txt` contains the application's Python runtime dependencies and explicitly pinned ASGI compatibility components. `requirements-dev.txt` adds the HTTP transport used by FastAPI's test client. Frontend dependencies are declared in `frontend/package.json` and locked in `frontend/package-lock.json`; do not copy JavaScript packages into the Python requirements file.

See [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) for the human-readable dependency inventory, versions, purposes, and optional tooling. For a ready-made set of safe sample files and a no-code acceptance checklist, see [examples/TESTING_GUIDE.md](examples/TESTING_GUIDE.md).

## Verify

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd frontend
npm run build
npm run lint
```

Run the extraction benchmark with:

```powershell
cd ..
& .\.venv\Scripts\python.exe benchmarks/run_extraction_benchmark.py
```

## Project map

```text
app.py                       FastAPI entry point and built frontend serving
context_studio/
  settings.py                limits and environment settings
  documents.py               validation, parsers, OCR adapter, evidence
  rules.py                   SQLite context-rule library and matching
  api.py                     HTTP routes and local security controls
frontend/                    React, TypeScript, Vite, Tailwind and shadcn/ui
tests/                       backend regression suite
examples/                    agent clients and sample documents
benchmarks/                  extraction benchmark
docs/                        architecture, API, security and decisions
plan.md                      staged delivery plan
```

## Local API

The OpenAPI page is available at `http://127.0.0.1:8001/api/docs` while the backend is running. See [docs/API.md](docs/API.md) for the endpoint contracts and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module boundaries.

For the product direction and interview walkthrough, see [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) and [docs/ENGINEERING_WALKTHROUGH.md](docs/ENGINEERING_WALKTHROUGH.md). Optional OCR and local summary installs are listed in [docs/OPTIONAL_LOCAL_TOOLS.md](docs/OPTIONAL_LOCAL_TOOLS.md); neither is installed without approval.

Keep the service bound to `127.0.0.1`. The local agent endpoint has no authentication or tenant isolation and must not be exposed to a network.
