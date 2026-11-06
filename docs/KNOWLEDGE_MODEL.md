# Knowledge model and invariants

This document describes the persisted knowledge model used by the local Context Studio API and React workspace.

## Core records

| Record | Purpose | Important invariant |
|---|---|---|
| Workspace | Boundary for a team's knowledge | Every source, entity and claim belongs to one workspace |
| Source | Stable identity of a named document | A source can have many immutable content versions |
| Source version | One exact byte-level revision | SHA-256, size, extension and storage key identify the original bytes |
| Document node | A structured unit extracted from a source version | Every node has a stable key, parent/ordinal, locator and content hash |
| Retrieval chunk | A bounded, deterministic segment derived from a document node | Keeps the parent node, source locator, content hash and approximate token count |
| Derived artifact | An extractive document digest, chunk set, index payload or generated context representation | It records generator/version and a current/stale/superseded/failed state |
| Artifact dependency | The exact inputs used to create a derived artifact | A derived artifact is valid only while its dependency fingerprints match |
| Knowledge edit | An auditable user correction or annotation | Edits are append-only records; they never mutate original source bytes |
| Entity / claim | Candidate structured facts and named concepts | Claims retain evidence links and explicit candidate/accepted/disputed/superseded state |
| Claim evidence | Source nodes that support, contradict or qualify a claim | No claim should be treated as grounded without linked evidence |

## Version and freshness rules

1. Source identity is separate from source content identity. Renaming a document does not change its content hash.
2. Every byte-level change creates a new source version. The prior version and its source bytes remain available until the user explicitly deletes them under the data-retention workflow.
3. Derived artifacts are tied to exact source versions and generator versions. A new source version does not rewrite historical outputs.
4. The active workspace view must never present an artifact from an old source version as current. It must show stale or superseded/rebuild-required state until refreshed.
5. Reprocessing unchanged bytes with the same parser/generator version should be deterministic where the underlying format permits it.
6. A correction to canonical knowledge is recorded as a knowledge edit, with before/after values and a reason when supplied. It invalidates dependent summaries, chunks and indexes.
7. Original uploaded files are immutable. Editing extracted knowledge is not the same as editing the original Office/PDF file. Round-trip editing is a separate export feature with explicit format support.

## Provenance contract

Document nodes are organized into nested heading parents with paragraph and table-block children where Markdown structure is available. Unheaded paragraphs remain root nodes. Every document node carries:
- source version ID;
- stable node key and parent/ordinal position;
- node type and optional title;
- original-format locator (page, paragraph, slide, sheet/cell range, etc.);
- exact extracted text and SHA-256 content hash;
- origin classification: extracted, user-edited or model-derived.

A model-generated summary, claim or entity mention must link back to one or more source nodes. Confidence is not a substitute for evidence. Conflicting claims remain visible as disputed rather than being silently collapsed.

## Incremental update contract

The intended update graph is:

`source version -> document nodes -> chunks / summaries / claims / entity mentions -> search index -> compiled context packs`

On a source update, only descendants depending on changed nodes should be invalidated and rebuilt. The first release may use a conservative whole-document invalidation policy; selective node-level invalidation must be added only when dependency tracking is correct and tested.

## Initial implementation boundary

The initial SQLite migration and first store slice persist immutable source blobs, source versions, hierarchical evidence nodes, derived-artifact dependencies and audited user corrections. The existing `parent_node_id` field is now populated for nested Markdown headings, paragraphs and table blocks; pre-existing flat nodes remain valid roots and no schema migration is required. Structure-aware chunking and SQLite FTS5/BM25 indexing are implemented for current source versions; edits rebuild the affected document index and extractive digest. The local API and React workspace expose ingestion, source/version/node inspection, hierarchy, digest inspection, lexical search and knowledge-node editing. Missing digests on older records are rebuilt lazily. The context compiler can explicitly substitute a version-matched digest (with node/locator/hash provenance) for selected passages from that source; it does not append both by default. Native table-cell modeling, embeddings, model-generated semantic summaries, claim extraction and contradiction resolution remain future vertical slices. No new third-party dependency was added.
