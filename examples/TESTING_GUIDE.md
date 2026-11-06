# Manual product acceptance — Context Studio

This guide is for checking the running product. You do not need to run Python tests, edit code, or use a terminal after setup.

## Start the app

From the project root in Windows PowerShell:

```powershell
.\setup.ps1 -InstallDependencies -InstallMachinePrerequisites
.\run.ps1
```

Open `http://127.0.0.1:8001` in your browser. The first command creates the project-local Python environment and installs the pinned Python and frontend dependencies. The second starts the local application. Keep the PowerShell window open while using the app.

Requirements: Python 3.11+, Node.js 22.12+, npm 10+, and Windows PowerShell 5.1. The setup command can install the optional Tesseract OCR engine through `winget`; no API key, hosted service, database server, or paid software is required.

## Ready-made files

All files below are fictional test data and are safe to upload to your local Context Studio workspace.

| File | What to check |
| --- | --- |
| `fixtures/northstar-programme.pdf` | Multi-page native PDF text extraction and page evidence. |
| `fixtures/northstar-programme.docx` | Word headings, paragraphs, and table extraction. |
| `fixtures/northstar-programme.pptx` | Slide-by-slide text extraction. |
| `fixtures/northstar-programme.xlsx` | Multi-sheet workbook extraction. |
| `fixtures/site-performance.csv` | Native table explorer, record filtering, cell selection, provenance, and search. |
| `fixtures/site-register.json` | Nested JSON and long text fields. |
| `fixtures/programme-handbook.html` | Semantic HTML extraction; embedded script text should not become document content. |
| `fixtures/northstar-programme.md` | Heading hierarchy, paragraphs, and Markdown table structure. |
| `fixtures/northstar-programme.txt` | Plain-text extraction and sectioning. |
| `fixtures/northstar-site-inspection.png` | Image upload, validation, metadata, and optional OCR route. |
| `fixtures/northstar-scanned-inspection.pdf` | Image-only PDF page and optional OCR fallback. |

## Suggested 10-minute acceptance run

1. Upload `northstar-programme.pdf` and `northstar-programme.docx` together. Confirm both appear, inspect extracted text, and check that the PDF has page-level evidence.
2. Upload `site-performance.csv`. Open its table explorer, filter for `Riverside`, select a cell, and confirm the source record and column are shown.
3. Search for `NS-0001`. Select a cell result and add it to Compile. Confirm the compiled evidence retains the filename, version, record, column, and source hash.
4. Edit a CSV cell in the working knowledge view. Confirm the parent record reflects the correction and that the original uploaded file remains untouched.
5. Upload `northstar-programme.xlsx` and inspect the extracted sheets. Then upload the PNG and scanned PDF to inspect the image-handling state.
6. Upload `site-performance.csv` a second time unchanged. It should not create a new source version. If you want to check changed-file versioning, make a temporary copy outside this repository, change one value, and upload it under the original filename. Do not overwrite the checked-in fixture.

## OCR note

Tesseract is optional; `setup.ps1 -InstallMachinePrerequisites` attempts to install it through `winget` when it is missing. If installation is cancelled or unavailable, the PNG and scanned PDF should produce a clear OCR-unavailable/unreadable warning rather than silently inventing text. Native-text PDFs and all non-OCR formats continue to work.

## Keep GitHub clean

The files in `examples/fixtures/` are generated, fictional, and intentionally tracked as test assets. Do not copy personal, client, employer, or confidential documents into this directory. The `.gitignore` excludes the local `data/` directory, source blobs, databases, uploads, exports, virtual environments, frontend dependencies, build output, logs, and local secrets. Before pushing changes, run:

```powershell
.\scripts\check-git-safety.ps1
```

This checks staged paths for common local/private data locations and secret or database file types. It is a guardrail, not a substitute for reviewing the staged diff.
