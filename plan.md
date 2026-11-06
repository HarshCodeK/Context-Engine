# Context Studio ? Execution Tracker

The product goal, architecture principles, company use cases and staged roadmap now live in [`goal.md`](goal.md). This file tracks implementation evidence only.

## Current milestone

**Stage 1 ? Knowledge foundation**

- [x] Record the product goal and living-context architecture in `goal.md`.
- [x] Establish the canonical knowledge schema and migration versioning.
- [x] Model workspaces, sources, immutable source versions, provenance nodes, derived artifacts, dependencies, edits, entities and evidence-backed claims.
- [x] Persist source bytes in a content-addressed local blob store.
- [x] Avoid duplicate versions for unchanged bytes; create a new version when the same named source changes.
- [x] Record provenance nodes from the existing extraction evidence contract.
- [x] Store original bytes in an atomic, content-addressed blob layout and verify integrity on reads.
- [x] Add deterministic structure-aware chunking and a local SQLite FTS5/BM25 index.
- [x] Exclude superseded source versions from current-workspace search and rebuild the index after a knowledge edit.
- [x] Expose persistent ingestion, source/version/node inspection, lexical search, cached digest retrieval and audited node editing through local API routes.
- [x] Generate a deterministic extractive digest per source version, with exact sentence offsets and evidence hashes; refresh it after knowledge edits.
- [x] Audit user corrections and invalidate explicitly dependent derived artifacts.
- [x] Add integrity checks for stored source blobs.
- [x] Add API endpoints and integration tests for persistent knowledge ingestion and retrieval.
- [x] Segment extracted evidence into heading-led sections and paragraph units with source offsets.
- [x] Expose the knowledge store in the React workspace, including digest provenance and audited knowledge editing.
- [x] Backfill missing digests lazily for older records and duplicate re-ingests.
- [x] Make digest substitution an explicit compiler choice; do not append a digest beside passages from the same source.
- [x] Build deterministic nested heading parents with paragraph and table-block children; preserve source offsets and expose parent links to the inspector.
- [x] Expand CSV into native table/column/record/cell nodes with stable source-derived keys, exact string values, blank-cell preservation and record/column locators.
- [x] Index native CSV cells and record summaries in FTS5; add a bounded, filterable table explorer with direct cell inspection.
- [ ] Extend native table/row/cell extraction to XLSX, DOCX, PPTX and PDF while preserving format-specific sheet/page/table coordinates.
- [ ] Add version diffing and selective dependency invalidation.

## Verification

- Full backend suite: **118 tests passed** after CSV native table extraction, persistence, search, edit and row-summary coverage.
- Frontend lint: **0 warnings and 0 errors** after the table explorer implementation.
- Frontend TypeScript + Vite production build: passed after the table explorer implementation.
- Browser QA on an isolated temporary database: upload, section segmentation, cached digest display, audited edit, digest refresh, lexical search, context selection and digest substitution all exercised.
- After editing the launch date from 19 May to 20 May 2027, search returned the new date and zero matches for the old date.
- Browser API requests on the final QA port returned HTTP 200 for health, source/version/node/digest reads and search. The earlier 8002 log contained a pre-fix 404; the final QA run used port 8003 and a fresh isolated database.
- Hierarchy browser QA on isolated port 8004 ingested a nested Markdown outline and rendered all eight heading/paragraph nodes with full section paths; parent-child relationships and exact offsets are covered by backend tests.
- CSV native table automated coverage: duplicate headers, blank headers/cells, quoted commas, embedded newlines, Unicode, stable table keys, exact cell values, parent links, cell-level FTS search, duplicate re-ingest, cell correction/blanking with refreshed row search, and immutable source-byte reads.
- Isolated browser QA on port 8005 with a synthetic 120-record × 9-column CSV: one CSV source node plus one native table; 120 records and 9 headers displayed; filtering `Riverside` returned 40 records; searching `NS-0001` returned cell-level and row-level evidence; compiled cell context retained source/version/location/hash; cell edits refreshed the row summary and clearing a cell remained supported; the original blob still matched the fixture byte-for-byte; identical re-upload stayed at v1 and changed bytes under the same filename created v2 while preserving v1 history.
- Responsive browser QA at 390 CSS pixels: document width remained 375 pixels while the 991-pixel table content scrolled inside its 288-pixel viewport; no horizontal page overflow. Browser console reported zero errors or warnings.

## Safety and migration notes

- The existing `data/context_studio.sqlite3` database and legacy extraction/context-rule behavior remain untouched.
- The knowledge store uses a separate `data/knowledge.sqlite3` database and `data/source_blobs/` directory and is now exposed through the local API and React workspace.
- `parent_node_id` already existed in schema version 1, so hierarchy activation required no database migration. Existing flat records remain valid root nodes; newly ingested Markdown headings/paragraphs use explicit parent links.
- Markdown tables remain table-block child nodes. CSV is now expanded into native table/column/record/cell nodes; XLSX, DOCX, PPTX and PDF native table expansion remains future work.
- Existing parsers remain ingestion adapters; they are not the product's core differentiator.
- Document digests remain deterministic extractive artifacts, not semantic AI summaries. Digest substitution may increase or decrease context size depending on the task; no token-saving claim is made.
- No documents are sent to an external model; no model provider or embedding service is configured.
- No packages, runtimes, model weights or external services were installed.
- No global environments, other projects, or user documents were deleted.
