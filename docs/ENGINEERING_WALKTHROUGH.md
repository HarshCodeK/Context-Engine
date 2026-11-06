# Engineering walkthrough

## One-minute explanation

Context Studio is a local document-to-context workspace. It converts common office files and text formats into editable Markdown, keeps source evidence attached to each extraction, and builds a selected context pack for AI tools. It also stores reusable organization, project, and task rules that local agents can request through a read-only API.

The core design is deterministic and local. A language model is not required to extract files, review output, or assemble a context pack.

## Architecture

- **React + TypeScript:** file queue, processing controls, Markdown editor, context-pack selection, and context-rule management.
- **FastAPI:** upload validation, extraction routes, health/configuration, rule CRUD, and agent context.
- **Format libraries:** PyMuPDF, python-docx, python-pptx, openpyxl, Pillow, and Python's standard library.
- **SQLite:** explicitly saved context rules only.
- **Evidence:** source SHA-256, stable block IDs, native source locators, Markdown ranges, extraction method, and block content hashes.

## Hardest decision

The hardest decision was to make extraction deterministic and traceable before adding a model that rewrites documents. An LLM-first pipeline was tempting because it could produce a polished summary in one step. It was rejected because it would make parser failures harder to see, could omit tables or slide details, and would blur the boundary between source content and model interpretation.

Instead, native parsers preserve the source structure and return evidence with the Markdown. A semantic summary can be added as a separate, opt-in layer after it passes a factuality and latency benchmark. This keeps the original extraction inspectable even when a model is unavailable or produces a weak summary.

## Engineering decisions worth explaining

### Untrusted file handling

The browser gives immediate feedback, but FastAPI repeats every important check. The backend validates file signatures, Office archive members, batch sizes, page/slide/table limits, and extracted text size. OCR runs as a bounded local subprocess with per-page and total timeouts.

### Source provenance

Each extraction includes a source hash and stable evidence blocks. PDF blocks point to pages; DOCX blocks point to paragraphs and tables; PPTX blocks point to slides and shapes; XLSX blocks point to sheets and ranges. The context pack carries a bounded evidence manifest alongside the Markdown.

### Concurrent rule writes

The local rule library has a hard record limit. A simple count followed by an insert can race when two requests arrive together. `BEGIN IMMEDIATE` serializes that short transaction so concurrent creates cannot exceed the configured cap.

### Session data versus saved data

Uploaded source files and edited Markdown stay in the browser/server request lifecycle. SQLite persists only context rules that the user explicitly saves. The agent endpoint returns matching saved rules and never includes uploaded documents.

### Small dependency surface

The backend uses FastAPI, the format libraries already present on the machine, and the standard library. OCR is a Tesseract executable rather than a Python wrapper. The MCP example implements the protocol with the standard library. The frontend uses React, Vite, Tailwind, generated shadcn/ui components, Tabler icons, and Geist fonts; unused animation/icon/toast packages were removed.

## Three-minute demo

1. Upload `examples/fixtures/northstar-programme.pdf`, `northstar-programme.docx`, and `northstar-programme.xlsx`.
2. Build context with `Native text only` selected.
3. Select each source and show its Markdown, route reason, source hash, and evidence count.
4. Edit a heading or sentence and export that file.
5. Add the three successful sources to a context pack and export the pack.
6. Open Context Rules, add a project rule for `context-studio` with the `docs` tag, and request `/api/agent-context?project_key=context-studio&task_tags=docs`.
7. Explain that the API returns saved rules only; the uploaded documents remain separate.

## Current measured evidence

- 84 backend regression tests pass.
- The synthetic extraction benchmark passes 9/9 fixtures and 74/74 checks.
- A live API batch processed all nine non-image fixtures successfully.
- Frontend production build and lint pass; lint reports zero warnings and errors.
- The current environment has no OCR executable and no local summary model. No hosted model calls are made.

These results prove the tested fixture behavior. They do not prove real-world OCR accuracy, semantic summary quality, or universal parser fidelity.

## Resume bullet

Built Context Studio, a local-first document context workspace using React, TypeScript, FastAPI, and SQLite; added bounded PDF/Office/CSV/HTML/JSON extraction, editable Markdown, block-level source provenance, context-pack exports, persistent agent rules, and a read-only agent API, backed by 84 regression tests and a 74-check synthetic extraction benchmark.

## Next engineering milestone

Evaluate optional Tesseract OCR and a small local chat model as separate capabilities. Do not install either until the user approves the exact download. The summary model must be evaluated for factuality, citation to source blocks, latency on the two-core CPU, and behavior on long documents before it is enabled in the UI.
