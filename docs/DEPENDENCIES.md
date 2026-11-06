# Context Studio dependency inventory

This file describes the dependencies required to clone, run, and test this project. The manifests are the source of truth:

- Python runtime: `requirements.txt`
- Python test tools: `requirements-dev.txt`
- Frontend direct dependencies: `frontend/package.json`
- Exact frontend dependency resolution: `frontend/package-lock.json`

Do not replace these manifests with a full `pip freeze` from a developer workstation. The current development `.venv` was created with access to pre-existing system packages, so its package listing contains unrelated tools.

## Python runtime

Python 3.11 or newer is required. The versions below are pinned in `requirements.txt`.

| Package | Version | Purpose |
| --- | ---: | --- |
| `fastapi` | 0.141.1 | HTTP API and request validation |
| `starlette` | 1.10.0 | ASGI toolkit used by FastAPI |
| `uvicorn` | 0.52.4 | Local ASGI server |
| `pydantic` | 2.12.5 | Request and context-rule data validation |
| `python-multipart` | 0.0.32 | Multipart file uploads |
| `pymupdf` | 1.28.2 | PDF text and page extraction |
| `python-docx` | 1.2.0 | DOCX extraction |
| `python-pptx` | 1.0.2 | PPTX extraction |
| `openpyxl` | 3.1.5 | XLSX extraction |
| `Pillow` | 11.3.0 | Image validation and metadata |

The backend also uses Python's standard library for SQLite, CSV, HTML, JSON, hashing, ZIP validation, subprocess management, and the MCP example. Those modules do not need separate installation.

## Python development dependency

`requirements-dev.txt` includes the runtime requirements and:

| Package | Version | Purpose |
| --- | ---: | --- |
| `httpx2` | 2.16.0 | HTTP transport required by Starlette 1.10's `TestClient` |

This development-only dependency is not needed to launch the application.

## Frontend direct dependencies

The exact resolved versions below were observed in the existing `frontend/node_modules` tree. The allowed version ranges are recorded in `frontend/package.json`; the lockfile pins the full dependency tree for `npm ci`.

### Runtime dependencies

| Package | Resolved version | Purpose |
| --- | ---: | --- |
| `react` | 19.3.1 | UI rendering |
| `react-dom` | 19.3.1 | Browser rendering |
| `@base-ui/react` | 1.9.0 | Accessible UI primitives used by generated shadcn components |
| `class-variance-authority` | 0.7.1 | Component variants |
| `cn` | 0.5.1 | Class-name helper used by the UI utility |
| `next-themes` | 0.4.6 | Light/dark theme state |
| `@tabler/icons-react` | 3.50.0 | Interface icons |
| `@fontsource-variable/geist` | 5.3.0 | Geist interface font |
| `@fontsource-variable/geist-mono` | 5.3.0 | Geist Mono technical text |
| `tailwindcss` | 4.3.3 | Utility CSS |
| `@tailwindcss/vite` | 4.3.3 | Tailwind/Vite integration |

### Development dependencies

| Package | Resolved version | Purpose |
| --- | ---: | --- |
| `vite` | 8.3.5 | Frontend development server and production bundler |
| `@vitejs/plugin-react` | 6.1.2 | React support in Vite |
| `typescript` | 7.0.2 | Type checking and compilation |
| `oxlint` | 1.90.0 | JavaScript/TypeScript linting |
| `@types/node` | 24.19.2 | Node type definitions |
| `@types/react` | 19.3.0 | React type definitions |
| `@types/react-dom` | 19.3.0 | React DOM type definitions |

Generated shadcn/ui component source files are committed in `frontend/src/components/ui`. The shadcn CLI is not needed to run or build a clone.

## Machine prerequisites (not Python/npm packages)

| Tool | Minimum version | Current development workstation |
| --- | ---: | ---: |
| Python | 3.11 | 3.13.14 |
| Node.js | 22.12 | 24.22.0 |
| npm | 10 | 11.19.1 |
| Windows PowerShell | 5.1 | 5.1 |

The application itself uses SQLite from Python's standard library. No separate database server is needed.

## Deliberately not installed or required

- Tesseract OCR: optional external executable (Apache-2.0). `setup.ps1 -InstallMachinePrerequisites` installs `tesseract-ocr.tesseract` through `winget` when it is missing; the catalog version checked for this setup was 5.5.3. If installation is unavailable or cancelled, image uploads still work and show an explicit OCR-unavailable notice.
- `pytesseract`: not used; the optional adapter calls the Tesseract executable directly.
- `llama.cpp`, Qwen model weights, Cactus Needle, JAX, or another local LLM runtime: not installed or required.
- Hosted AI APIs, API keys, paid services, cloud storage, Redis, Celery, or a vector database: not required.
- `pymupdf4llm`, `pymupdf-layout`, `onnxruntime`, `numpy`, and `networkx`: not imported by the application and not listed as project dependencies.

Optional tools must be separately reviewed and explicitly approved before anyone downloads them.

## Licensing note

The listed dependencies are available without a paid subscription. PyMuPDF is distributed under AGPL-3.0-or-later (with a separate commercial licensing option from its publisher); anyone distributing a derivative application should review and comply with the applicable license. Check the individual package licenses before redistributing the application.

## Fresh clone setup

From the project root, on Windows PowerShell:

```powershell
.\setup.ps1 -InstallDependencies -InstallMachinePrerequisites
```

The script checks Python 3.11+ and Node.js 22.12+/npm 10+. With `-InstallMachinePrerequisites`, it can install Python 3.13, Node.js LTS, and Tesseract OCR through Windows Package Manager (`winget`) when missing; reopen PowerShell and rerun setup after a machine-level installation so PATH refreshes. It then creates an isolated `.venv`, installs only `requirements.txt`, and runs `npm ci` against the checked-in lockfile. It does not install model weights or hosted services. For the backend test suite, additionally run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```
