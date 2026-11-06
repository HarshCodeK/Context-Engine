# Product specification

## Problem

People often give AI tools whole PDFs, slide decks, spreadsheets, and copied notes without controlling what enters the context window or being able to trace an answer back to the source. The result is noisy prompts, hidden extraction failures, and weak provenance.

## Product outcome

Context Studio turns supported documents into clean, editable Markdown and reusable context packs. Every extraction shows how the content was read, how long it took, what warnings occurred, and which source blocks support the output.

## Long-term product direction

The intended product is a cost-aware context and intelligence layer for AI workflows, not only a file converter. It should select the least expensive processing path that preserves the quality required by the task. Depending on the input and task, that may mean native extraction, OCR, structured parsing, indexing/retrieval, a local specialist model, or hosted reasoning. The system must keep evidence and uncertainty visible and measure context size, latency, local compute, and external API spend before claiming that one route is cheaper or better.

The current release establishes the local extraction, evidence, context-pack, and context-rule foundations. Task-aware routing, semantic quality measurement, indexing/retrieval, local model adapters, and hosted provider adapters are later stages. They should be added only behind explicit route decisions and repeatable evaluations.

## Primary user

A developer, analyst, researcher, or knowledge worker who prepares documents for local or hosted AI tools and needs to control the context they provide.

## Main workflow

1. Add a batch of documents.
2. Review the file queue, sizes, and processing policy.
3. Build context and inspect success/error states.
4. Select a source to review Markdown, extraction route, warnings, source hash, and evidence blocks.
5. Edit Markdown when needed.
6. Select successful sources for a context pack and export it within the configured size limit.
7. Save reusable organization, project, or task instructions for local agents.

## Product principles

- **Source fidelity:** preserve extracted content and source locators.
- **Visible decisions:** show route, processing mode, warnings, duration, and estimated tokens.
- **Local by default:** process documents on the user's machine and do not persist uploaded files.
- **User control:** allow editing, source selection, and explicit exports.
- **Measured claims:** report actual time, bytes, characters, and token estimates. Do not claim money, energy, or time savings without a reproducible baseline.
- **Low cognitive load:** one primary upload action, a source queue, and one output surface. Context rules remain secondary.

## Supported input

`.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`, `.html`, `.htm`, `.json`, `.md`, `.markdown`, `.txt`, `.png`, `.jpg`, `.jpeg`, and `.webp`.

## Output

- Editable Markdown per source.
- Selected context pack with a source register, extracted content, processing notes, and bounded evidence manifest.
- Read-only JSON/Markdown agent context assembled from saved rules.

## Scope boundaries

The current product does not provide hosted storage, accounts, multi-user collaboration, audio/video transcription, archive ingestion, a vector database, semantic search, or a bundled language model. OCR and semantic summarization are optional local integrations and require separate installation approval.

The context-rule service currently supplies saved organization/project/task instructions. Repository-aware context, version history, automatic conflict resolution, and connectors for agent harnesses beyond the included HTTP/MCP examples remain future work.

## Measurable quality

- Extraction success rate by file type on the fixture corpus.
- Parser fidelity against known fixture text and table content.
- Evidence completeness and locator correctness.
- Median and p95 extraction time by file type and size.
- Context-pack characters and approximate tokens.
- Upload validation and failure-path correctness.
- Agent context matching and precedence correctness.
