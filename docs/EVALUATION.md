# Evaluation and release checks

## Automated checks

The migrated backend regression suite covers upload validation, parser behavior, extraction bounds, OCR decision paths, security headers, context-rule validation and precedence, the agent endpoint, and the example agent/MCP clients.

| Check | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest discover -s tests -v` | 84 tests passed on Python 3.13 with PyMuPDF 1.28.2. |
| `npm run build` | Passed after final UI changes. Main JavaScript bundle is 304.55 kB (98.09 kB gzip); the rules panel is split into a 7.50 kB lazy chunk. |
| `npm run lint` | Passed with 0 warnings and 0 errors (19 source files). |
| `npm ls --depth=0` | Passed. 18 direct frontend packages; unused Motion, Phosphor, Sonner, and ScrollArea component files removed. `@base-ui/react` remains required by the generated Button, Badge, Input, and Separator components. |
| Dependency manifest audit | Passed. Nine pinned Python runtime packages, one Python test dependency, 11 frontend runtime dependencies, and 7 frontend development dependencies are documented. `setup.ps1` validation mode passed without installing or downloading anything. |
| Extraction benchmark | 9/9 synthetic fixtures passed, with 74/74 evidence and content checks. No hosted model calls. |
| `run.ps1` | Passed. The documented launcher validated the existing Python environment and started Uvicorn on `127.0.0.1:8001` without installing packages. |

## Live API smoke test

The running app returned HTTP 200 for health, configuration, and the root page. A single `native_only` batch containing all nine non-image fixture formats returned 9 successful results and `storage: "memory-only"`. The live context-rule create, agent-context match, and delete flow also completed successfully, leaving zero saved test rules.

The response included the expected strict Content Security Policy with no `unsafe-inline` directive.

## Follow-up resource-constrained verification

During the dependency-manifest update, the setup validation and all declared Python imports passed, the targeted mocked-OCR test passed, and frontend lint plus the installed dependency-tree audit passed. A full test-suite rerun encountered Windows memory-commit exhaustion (`MemoryError` while allocating large synthetic upload fixtures); the remaining OCR-path test passed when run alone. A fresh frontend build attempt also stopped when the TypeScript compiler could not reserve Windows virtual memory (`VirtualAlloc`, error 1455). No dependency installation or download was attempted. The earlier recorded 84-test pass and successful production build predate this manifest-only update; repeat the full suite and build when the host has more available commit/pagefile capacity.

## Browser checks

The Context Studio page was inspected in the Chat On Steroids internal browser. A real fixture file was supplied through the page's file-input change handler, the upload request returned HTTP 200, and the source reached the ready state with Markdown, route details, source SHA-256, and evidence visible. Markdown was edited and both the individual `.md` export and selected context-pack export were downloaded; their saved contents were inspected and contained the edited text. An unsupported `.exe` was rejected in the browser before upload. Malformed JSON reached the API and produced the expected per-file error message in the source queue.

The rules UI created a temporary rule, edited its title, disabled it, enabled it, and deleted it using inline confirmation. The live agent-context API separately matched a project-scoped test rule and cleanup returned the database to zero rules. The browser initially reported a CSP violation from Base UI's ScrollArea inline styles. The two scroll areas were replaced with focusable native overflow containers; after rebuilding and reloading, the rules panel opened with no new console errors. Keyboard Tab navigation reached the theme control with the focus-visible class.

The browser screenshot capture has not produced a usable image. Responsive CSS was exercised at 390 px, 720 px, 768 px, and 1440 px using same-origin iframe layout checks inside the existing internal browser. At all four widths the document had no horizontal overflow; the hero stacked at 390 px, the workbench stacked at 390/720/768 px, and the two-column desktop workbench returned at 1440 px. The 720 px check also exercises the layout width expected from 200% zoom on a 1440 px desktop, but actual browser zoom was not changed. The OS file chooser and physical drag gesture were not exercised, but both the actual file-input change handler and the dropzone's dragenter/dragover/drop event path were exercised with browser File/DataTransfer objects. Actual 200% zoom and screen-reader checks remain manual acceptance items.

## Manual acceptance checklist

- [x] Exercise the file-input change handler and dropzone drag/drop event path with supported files; the upload and extraction requests succeed.
- [x] Reject an unsupported extension before upload and show a useful malformed-JSON error after upload.
- [x] Build context and confirm a successful source reports Markdown, route reason, source hash, and evidence count.
- [x] Edit Markdown, export one file, and confirm the downloaded text matches the edit.
- [x] Export a selected context pack and confirm the downloaded pack includes the edited Markdown and evidence manifest.
- [x] Create, edit, disable, enable, and delete a temporary organization rule through the UI.
- [x] Call `/api/agent-context` and confirm a project-scoped rule matches; delete the test rule and verify zero saved rules remain.
- [x] Check keyboard Tab navigation and the focus-visible class on the active theme control.
- [x] Check responsive layout at 390 px, 720 px, 768 px, and 1440 px widths with no horizontal overflow.
- [ ] Exercise the OS file chooser and physical drag gesture; check 200% zoom and a screen reader.

## Known limitations

- Tesseract is not installed in the current environment; OCR-dependent extraction is unavailable.
- No local summarization model is installed or configured. The current product performs faithful extraction and context assembly.
- Browser screenshot and mobile viewport checks remain incomplete because the internal browser debugger stopped responding during the test session.
