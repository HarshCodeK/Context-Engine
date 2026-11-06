# Architecture

Context Studio is a local-first web application. React owns the interactive workspace and temporary upload selection. FastAPI validates and extracts source files. The knowledge workspace persists immutable originals and derived, provenance-linked records locally; the separate context-rule store remains local as well.

```text
React + TypeScript + shadcn/ui
          │ same-origin HTTP
          ▼
FastAPI (127.0.0.1:8001)
  ├── documents       validation, native parsers, optional OCR, extraction evidence
  ├── knowledge_store source versions, immutable blobs, nodes, artifacts, FTS5
  ├── rules           local context rules, precedence and matching
  └── API             upload, knowledge, search, health and agent context routes
          │
          ├── SQLite: data/context_studio.sqlite3 (context rules)
          └── SQLite: data/knowledge.sqlite3 + data/source_blobs/ (knowledge)

Local agent / MCP client ── GET /api/agent-context ── rules store
```

## Runtime modules

| File | Responsibility |
| --- | --- |
| `app.py` | FastAPI entry point and built frontend serving from `dist/`. |
| `context_studio/settings.py` | Validated upload, parser, OCR, table and workspace limits. |
| `context_studio/documents.py` | File validation, native extraction, optional Tesseract OCR, Markdown and source evidence. |
| `context_studio/document_structure.py` | Deterministic heading/paragraph/table-block segmentation with exact Markdown offsets. |
| `context_studio/knowledge_store.py` | Immutable source blobs, source versions, hierarchical nodes, audited edits, derived artifacts and FTS5 indexing. |
| `context_studio/rules.py` | SQLite rule schema, validation, overlap hints, scope precedence and agent context. |
| `context_studio/api.py` | HTTP routes, upload limits, loopback request checks and response security headers. |
| `frontend/src/lib/api.ts` | Typed same-origin API functions. |
| `frontend/src/features/workspace/` | Upload, knowledge inspection, native table exploration, search and context compilation. |

## Extraction and persistence lifecycle

1. The browser selects files and sends them to `/api/knowledge/ingest`.
2. FastAPI repeats all authoritative size, format, MIME and content-signature checks.
3. Native parsers extract Markdown plus evidence locators, content hashes and source ranges. OCR is attempted only when automatic processing is selected and Tesseract is available.
4. The knowledge store writes original bytes atomically to a content-addressed local blob path. It verifies hashes when reading those bytes back.
5. A source is versioned by its exact bytes. Re-uploading identical bytes does not create a duplicate version; changed bytes create a new immutable version.
6. Evidence is segmented into hierarchical knowledge nodes. Derived digests and lexical chunks/indexes retain dependency fingerprints and source locators.
7. The browser retrieves nodes, versions, digests and search results from the local API. The original uploaded file is never modified by knowledge edits.

The separate `/api/extract` endpoint remains available for memory-only conversion workflows; it does not persist original bytes in the knowledge library.

## Native CSV table structure

CSV extraction keeps its readable Markdown representation and adds a structured table payload to the evidence contract. The knowledge store expands that payload into a parent/child hierarchy:

```text
source version
└── document section
    └── table
        ├── column (header and column coordinate)
        ├── record (logical CSV record number)
        │   ├── cell (exact value, header and column coordinate)
        │   └── cell
        └── record
```

Record numbers are logical CSV records, not physical text lines, so quoted cells containing embedded newlines do not shift later coordinates. Values remain strings and are not silently coerced into numbers or dates. Empty cells remain explicit empty cell nodes. Duplicate and blank headers receive distinct display labels while retaining their original header text. Stable node keys are derived from source content identity, table, record and column coordinates.

Native CSV cell indexing is capped at 5,000 cells per table. The Markdown extraction and immutable original retain the complete parser-bounded table if the native-cell cap is reached; the extraction warning makes the reduced cell-level coverage visible.

## Context rules

Context rules are stored in `data/context_studio.sqlite3` using SQLite WAL mode. Rule creation uses `BEGIN IMMEDIATE` around the count-and-insert operation so concurrent local requests cannot exceed the configured library limit.

- Organization rules apply to every request.
- Project rules apply when the project key matches.
- Task rules apply when both the project key and at least one task tag match.

The API returns precedence explicitly: organization, project, task. Potential overlaps are based on shared tags; the application does not claim to detect semantic contradictions.

## Context-pack assembly

The browser combines selected current-version evidence into a provider-neutral Markdown pack. It includes a source register, source version and locator information, content hashes, processing notes and selected evidence. The pack is bounded by `MAX_CONTEXT_PACK_CHARS`.

If a user edits canonical knowledge, the correction is append-only in the audit table and the working node, digest and lexical index are refreshed. Original source bytes remain unchanged.

## Local agent access

`GET /api/agent-context` returns only saved rules that match the supplied project key and task tags. It does not include uploaded documents or unsaved browser-session content. The included standard-library client and MCP server demonstrate how an agent can pull that context.

The API is intentionally local and single-user. Do not expose it on a network: the local agent endpoint has no authentication or tenant isolation. Do not add cloud storage, a remote database, background workers, authentication or multi-user infrastructure without a product requirement and a new threat review.
