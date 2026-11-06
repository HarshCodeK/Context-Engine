# Sample document fixtures

These are fictional but realistic test documents from one community-energy programme. They allow parser behavior to be compared across formats without mixing unrelated topics.

| Format | File | Coverage |
| --- | --- | --- |
| Plain text | `northstar-programme.txt` | Multi-section narrative and Unicode text. |
| Markdown | `northstar-programme.md`, `northstar-programme.markdown` | Headings, paragraphs, tables, and lists. |
| PDF | `northstar-programme.pdf` | Nine pages of native selectable text. |
| Word | `northstar-programme.docx` | Headings, paragraphs, and a multi-row table. |
| PowerPoint | `northstar-programme.pptx` | Ten slides with long speaker-facing text and a summary slide. |
| Excel | `northstar-programme.xlsx` | Three sheets, site rows, budget, and risk tables. |
| CSV | `site-performance.csv` | 120 records with numeric and categorical values. |
| JSON | `site-register.json` | Nested records, arrays, and long text fields. |
| HTML | `programme-handbook.html` | Semantic sections, headings, a table, and script content that must not be extracted. |
| Image | `northstar-site-inspection.png` | Synthetic site-inspection image for image validation and optional OCR. |
| Scanned PDF | `northstar-scanned-inspection.pdf` | One-page image-only PDF for the optional scanned-page OCR path. |

Regenerate the fixtures from the project root:

```powershell
python examples/generate_sample_fixtures.py
```

The generator uses the same format libraries as the application. No network request or model is required. It writes the image and scanned-PDF fixtures as well as the document corpus.

The image fixtures are synthetic and contain no real people, addresses, customers, or sites. They are suitable for upload-flow checks and OCR fallback checks. Tesseract is optional and can be installed by `setup.ps1 -InstallMachinePrerequisites`; OCR accuracy should be evaluated separately with licensed, representative scans (a clean printed page, a skewed phone photo, and a text-heavy screenshot). Do not add private customer documents to this directory.

For a guided manual acceptance run, see [`../TESTING_GUIDE.md`](../TESTING_GUIDE.md).
