# Context Studio — Product Goal & Engineering Blueprint

**Status:** Active product direction  
**Project:** 01 — Document Context  
**Working title:** Context Studio  
**Category:** Local-first, living knowledge and context infrastructure for AI-enabled teams

## 1. The problem

Teams repeatedly give AI systems the same documents, ask the same questions, and pay to rediscover facts that the organisation already knows. The information is scattered across specifications, meeting notes, spreadsheets, policies, research and changing decisions.

A folder of files is not usable organisational context. A pile of generated summaries is not trustworthy organisational memory either.

Context Studio turns changing source material into a structured, versioned, searchable knowledge layer that can supply the right evidence to people and LLMs at the moment it is needed.

## 2. Product promise

**Keep team knowledge current. Give every AI task the right context, with evidence.**

The product should:
- Ingest a company's documents once and preserve their identity, versions and source lineage.
- Extract structure, facts, tables, entities, decisions, dates and relationships where supported.
- Maintain compact summaries and indexes as derived, refreshable artifacts—not replacements for source evidence.
- Let users correct, annotate and edit the working knowledge representation.
- Support safe document editing workflows with explicit source/version tracking; never silently overwrite originals.
- Retrieve relevant evidence for a question and compile a bounded context pack for any LLM.
- Explain what was selected, why it was selected, what was omitted, and where every claim came from.
- Detect stale derived context, conflicting claims and changes that may invalidate previous answers.
- Work locally by default, with explicit adapters for optional models and external services.

## 3. The key product insight: a living context layer

The core object is not a Markdown export or a chat transcript. It is a **versioned knowledge workspace**.

Each source has:
- Stable source ID and content hash.
- Original file retained unchanged unless a user explicitly replaces it.
- Version history and change detection.
- Extracted canonical representation.
- Structural units (pages, headings, paragraphs, tables, rows/cells where possible).
- Provenance coordinates back to the original source.
- Derived summaries, entities, claims, links and retrieval chunks.
- Processing status, parser/version metadata, warnings and timestamps.

Derived artifacts must declare which source versions they depend on. If a source changes, invalidate only affected artifacts and rebuild them. Never present an outdated summary or index as current.

### Editing model

There are two distinct editing surfaces:
1. **Knowledge editing:** edit extracted text, structured facts, annotations, summaries and decisions inside Context Studio. Keep the original source immutable and record the editor, time, source version and change.
2. **Source document editing:** where format support allows, provide an explicit export/round-trip workflow that creates a new document version. Do not promise lossless in-place editing for arbitrary PDF, Office, image or other formats.

The canonical representation is the editable working layer. It must preserve provenance and make user corrections distinguishable from machine extraction.

## 4. Signature experience: Context Debugger

A user asks: "What is the current launch date, what changed, and who approved it?"

Context Studio shows:
- How the question was interpreted.
- Which sources and versions were searched.
- Candidate passages and retrieval scores.
- Why each item ranked where it did.
- Conflicting claims and their dates/authority.
- The evidence selected for the final context.
- Token estimate, budget and context size.
- Exact source/page/section/table-cell lineage.
- A compact, editable context brief ready to send to an LLM.
- A way to inspect, pin, remove or correct evidence before export.

The result is not a generic chatbot. It is a transparent context preparation and knowledge-maintenance workbench.

## 5. Core architecture

Keep the architecture understandable, local-first and replaceable. Do not add infrastructure or dependencies without a measured need and explicit approval.

### A. Source and version registry
- Ingest uploads and record stable IDs, hashes, metadata and versions.
- Detect unchanged, modified, duplicated and deleted sources.
- Preserve original bytes and immutable source snapshots.
- Track source replacement and user-approved deletion.

### B. Extraction and canonical document model
- Keep format-specific parsing behind small adapters.
- Normalize outputs into a canonical document tree.
- Represent headings, paragraphs, lists, tables, cells, metadata and source coordinates.
- Keep extraction warnings and unsupported content visible.
- Parsers are replaceable components; the product's value is the canonical model, provenance and downstream intelligence—not reinventing PDF/Office file specifications.

### C. Structure-aware segmentation
- Build semantic units from document structure rather than arbitrary fixed character windows.
- Use hierarchical parent/child chunks, overlap only where justified, and preserve source coordinates.
- Make chunking deterministic and test boundary cases.

### D. Knowledge derivation
- Generate document-level and section-level summaries only when a model adapter is configured.
- Extract candidate facts, decisions, entities, dates and relationships with confidence and evidence.
- Mark model-derived output as derived and fallible.
- Keep deterministic extraction distinct from model inference.
- Recompute only derived artifacts affected by source changes or user edits.

### E. Search and retrieval
- Start with an inspectable lexical retrieval engine (SQLite FTS5/BM25 where available).
- Add local embeddings and vector ranking only after establishing a baseline and obtaining approval for model/runtime requirements.
- Support hybrid ranking, metadata filters, parent-child expansion, deduplication and diversity.
- Return ranked evidence with explainable scores and provenance.

### F. Context compiler
- Select evidence under a context/token budget.
- Optimize relevance, coverage, diversity, freshness and source authority.
- Preserve citations and uncertainty.
- Detect and display conflicting claims rather than silently choosing one.
- Produce provider-neutral Markdown and JSON context packs.
- Estimate tokens honestly; label estimates and support provider-specific tokenizers only when configured.

### G. Change propagation
- Source change -> compare versions -> identify changed structural units -> invalidate dependent summaries/chunks/index entries -> rebuild affected artifacts -> mark dependent context packs stale.
- User edits to canonical knowledge follow the same dependency invalidation rules.
- Show processing state and allow retry; never silently claim stale context is fresh.

### H. Delivery and integrations
- Local API for applications and agents.
- Provider-neutral context pack contract.
- Optional LLM adapters, configured explicitly by the user.
- No model provider receives source material unless the user configures and invokes that integration.
- Read-only agent access by default; write operations require explicit authorization and audit records.

## 6. Company use cases

Prioritize real workflows, not a feature checklist:
1. **Product and engineering:** specifications, architecture decisions, release notes, meeting decisions, issue histories; answer what changed and why.
2. **Customer success and sales:** approved product facts, account notes and support history; prepare current, cited customer context.
3. **Operations and compliance:** policies, SOPs, revisions and audit evidence; show current policy and its lineage.
4. **Research and analysis:** papers, reports, datasets and notes; compare findings and preserve caveats.
5. **Internal AI agents:** retrieve only relevant, current, permission-appropriate context instead of attaching entire folders to every prompt.

Permissions and multi-user collaboration are a later stage. Do not imply enterprise access control exists until implemented and tested.

## 7. Evaluation: prove it is better

Build a fixed, deliberately difficult evaluation corpus with source changes, duplicate passages, conflicting dates, tables, long documents, near-duplicates and ambiguous questions.

Measure:
- Extraction coverage and provenance accuracy.
- Chunk boundary quality and deterministic stability.
- Retrieval Recall@k, Precision@k and MRR.
- Citation precision and claim support.
- Conflict detection precision/recall.
- Context token count and evidence coverage.
- Stale-artifact invalidation correctness.
- Incremental update time versus full rebuild.
- End-to-end latency, memory and CPU on the actual target machine.

Compare against simple baselines: whole-document prompting, fixed-size chunking, lexical-only search and naive top-k retrieval. Publish measured results only; never invent token savings or accuracy claims.

## 8. Technology policy

- Backend: Python and FastAPI, unless inspection demonstrates a compelling reason to change.
- Persistence: SQLite initially; use transactions, explicit schema migrations and indexes.
- Frontend: React + TypeScript + Vite, with real generated shadcn/ui components already in the project.
- Search: SQLite FTS5 as the first measurable baseline.
- Parsing: use small, well-understood format parsers behind adapters; do not write complex PDF/Office parsers from scratch.
- Embeddings and local inference: optional, pluggable and approval-gated. No model weights or runtime downloads without approval.
- No Redis, Kubernetes, cloud database, vector database, agent framework, hosted LLM, telemetry or paid service without a concrete requirement and approval.
- Keep a clean isolated Python environment. Do not uninstall global packages or modify other projects.
- Keep the project runnable locally and explainable in an engineering interview.

## 9. Product experience

Primary navigation should reflect three jobs:
1. **Knowledge** — sources, versions, document structure, edits, decisions and freshness.
2. **Explore** — ask a question, search, inspect evidence and conflicts.
3. **Compile** — debug retrieval, select evidence, manage token budget and export/send context.

The interface should make source freshness, provenance and uncertainty visible. Avoid generic chatbot-first design, fake analytics, decorative metrics and nonfunctional controls.

## 10. Delivery stages and gates

### Stage 0 — Baseline and safe reset
- Inventory the complete current project, active processes, data and dependencies.
- Identify reusable extraction, validation, provenance, API, rule, test and UI work.
- Establish a clean baseline with tests and a dependency map.
- Move obsolete implementation into a clearly labelled archive only after confirming no unique data or useful behavior will be lost.
- Do not delete user data, uploaded documents, databases, fixtures or working code before a verified backup and explicit scope check.

### Stage 1 — Knowledge foundation
- Define canonical document schema, source registry, version model and provenance contract.
- Define deterministic ingestion and structure-aware segmentation.
- Build migrations and tests first.
- Preserve original files and record extraction decisions.

### Stage 2 — Searchable knowledge
- Implement lexical index and explainable retrieval.
- Add filters, parent-child expansion and deduplication.
- Build benchmark corpus and baseline metrics.
- Add embeddings only after measured need and approval.

### Stage 3 — Living updates and editing
- Build editable canonical knowledge view and annotation/correction workflow.
- Add version diffs and dependency tracking.
- Incrementally refresh affected summaries, chunks and indexes.
- Add explicit round-trip export for supported formats; original source remains safe.

### Stage 4 — Context compiler and debugger
- Implement budget-aware evidence selection, conflict presentation and citations.
- Expose exact context pack and retrieval trace.
- Add Markdown/JSON export and stable API contract.

### Stage 5 — Team-ready workflows
- Build project/workspace organization and use-case workflows.
- Add optional LLM adapters and controlled send-to-model flow.
- Add auditability and permission boundaries before multi-user deployment.

### Stage 6 — Product hardening
- Benchmark on representative hardware and corpora.
- Security review, resource limits, failure recovery and data lifecycle controls.
- Documentation, local installation, backup/restore and end-to-end QA.
- No claim of production or enterprise readiness without evidence.

## 11. Working rules

- Complete Project #1 before starting another portfolio project.
- Work in small, reviewable stages; do not implement the entire roadmap in one pass.
- Inspect before changing; preserve existing work until replacements pass tests.
- Keep source history and user data safe. Prefer reversible archival over destructive deletion.
- No unapproved installs, downloads, global environment changes or paid services.
- Do not confuse using a parser library with outsourcing the product's core engineering.
- Do not call the product RAG, real-time, collaborative, secure or enterprise-ready unless the corresponding behavior exists and has tests.
- Keep docs, tests and shipped behavior in sync.
- At each stage, report what changed, what passed, what remains and the next smallest step.

## 12. Definition of success

A team can maintain a changing knowledge workspace; inspect and correct its derived knowledge; ask questions against current sources; see the exact evidence and conflicts; compile a concise, bounded, provider-neutral context pack; and deliver it to an AI system without repeatedly reprocessing or blindly resending entire documents. Changes propagate correctly, stale knowledge is visible, and every important claim can be traced back to its source.
 
