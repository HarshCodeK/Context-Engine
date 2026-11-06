# Architecture

Context Studio is a single-process local web application. The browser owns the temporary source queue, editable Markdown drafts, and context-pack assembly. FastAPI validates and extracts uploaded files. SQLite stores only reusable context rules.

```text
React + TypeScript + shadcn/ui
          │ same-origin HTTP
          ▼
FastAPI (127.0.0.1:8001)
  ├── settings       request and extraction limits
  ├── documents      validation, native parsers, optional OCR, evidence
  ├── rules          SQLite rules, precedence and matching
  └── API            upload, health, rules and agent context routes
          │
          └── SQLite: data/context_studio.sqlite3

Local agent / MCP client ── GET /api/agent-context ──┘
```

## Runtime modules

| File | Responsibility |
| --- | --- |
| `app.py` | Imports the FastAPI app and serves the built React files from `dist/`. |
| `context_studio/settings.py` | Defines the project root, SQLite path, supported extensions, and validated limits. |
| `context_studio/documents.py` | Validates file bytes and Office archives, extracts supported formats, optionally invokes Tesseract, and creates Markdown/evidence records. |
| `context_studio/rules.py` | Creates the SQLite schema, validates rules, detects possible tag overlaps, applies scope precedence, and renders agent context. |
| `context_studio/api.py` | Defines HTTP routes, upload limits, loopback request checks, and response security headers. |
| `frontend/src/lib/api.ts` | Small typed fetch functions for the local API. |
| `frontend/src/features/` | Upload queue, output review, and context-rule UI. |

## Extraction lifecycle

1. The browser checks file extension, per-file size, batch count, and total batch size before sending the batch.
2. FastAPI repeats validation. Client-side checks are for usability; server-side checks are authoritative.
3. The document layer checks the actual file content and Office archive members before parsing.
4. Native parsers extract text, tables, slide content, and document structure. OCR is attempted only when automatic processing is selected and Tesseract is available.
5. The extractor creates Markdown and evidence blocks. The response includes a SHA-256 digest of the source, source locators, Markdown ranges, extraction method, and content hashes.
6. The browser keeps results in memory so the user can select, edit, copy, and export them. Uploaded source files are not written to disk.

## Context rules

Context rules are stored in `data/context_studio.sqlite3` using SQLite WAL mode. The schema is initialized on first use. Rule creation uses `BEGIN IMMEDIATE` around the count-and-insert operation so concurrent local requests cannot exceed the configured library limit.

Rules have one of three scopes:

- Organization rules apply to every request.
- Project rules apply when the project key matches.
- Task rules apply when both the project key and at least one task tag match.

The API returns the precedence order explicitly: organization, project, task. Higher priority sorts first within a scope. Potential overlaps are based on shared tags; the application does not claim to detect semantic contradictions.

## Context-pack assembly

The browser combines selected successful extractions into one Markdown file. It includes a source register, extracted content, processing notes, and up to 50 evidence blocks per source. The pack is rejected when it exceeds `MAX_CONTEXT_PACK_CHARS`.

If a user edits Markdown, the pack labels evidence ranges as references to the original extraction. This avoids implying that source ranges still map exactly to user-edited text.

## Local agent access

`GET /api/agent-context` returns only saved rules that match the supplied project key and task tags. It does not include uploaded documents or unsaved browser-session content. The included standard-library client and MCP server demonstrate how an agent can pull that context.

The API is intentionally local and single-user. Do not add cloud storage, a remote database, authentication, background workers, or multi-user infrastructure without a product requirement and a new threat review.
