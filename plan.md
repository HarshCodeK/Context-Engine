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
- [ ] Extend hierarchy into native table/row/cell nodes across supported formats.
- [ ] Add version diffing and selective dependency invalidation.

## Verification

- Full backend suite: **113 tests passed** after the nested hierarchy, structure, digest, legacy-backfill and API changes.
- Frontend lint: **0 warnings and 0 errors**.
- Frontend TypeScript + Vite production build: passed.
- Browser QA on an isolated temporary database: upload, section segmentation, cached digest display, audited edit, digest refresh, lexical search, context selection and digest substitution all exercised.
- After editing the launch date from 19 May to 20 May 2027, search returned the new date and zero matches for the old date.
- Browser API requests on the final QA port returned HTTP 200 for health, source/version/node/digest reads and search. The earlier 8002 log contained a pre-fix 404; the final QA run used port 8003 and a fresh isolated database.
- Hierarchy browser QA on isolated port 8004 ingested a nested Markdown outline and rendered all eight heading/paragraph nodes with full section paths; parent-child relationships and exact offsets are covered by backend tests.

## Safety and migration notes

- The existing `data/context_studio.sqlite3` database and legacy extraction/context-rule behavior remain untouched.
- The knowledge store uses a separate `data/knowledge.sqlite3` database and `data/source_blobs/` directory and is now exposed through the local API and React workspace.
- `parent_node_id` already existed in schema version 1, so hierarchy activation required no database migration. Existing flat records remain valid root nodes; newly ingested Markdown headings/paragraphs use explicit parent links.
- Markdown tables are currently represented as table-block child nodes. Individual cell/row nodes across spreadsheets and Office/PDF formats are still future work.
- Existing parsers remain ingestion adapters; they are not the product's core differentiator.
- Document digests remain deterministic extractive artifacts, not semantic AI summaries. Digest substitution may increase or decrease context size depending on the task; no token-saving claim is made.
- No documents are sent to an external model; no model provider or embedding service is configured.
- No packages, runtimes, model weights or external services were installed.
- No global environments, other projects, or user documents were deleted.
