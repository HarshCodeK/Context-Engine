# Local API

Base URL: `http://127.0.0.1:8001`

Interactive OpenAPI docs: `/api/docs`.

## Health and configuration

### `GET /api/health`

Returns `status`, application `version`, and `ocr_available`.

### `GET /api/config`

Returns the server limits used by the browser: maximum file count, per-file bytes, batch bytes, session limits, context-pack character limit, rule limit, and supported extensions.

## Document extraction

### `POST /api/extract`

Content type: `multipart/form-data`.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `files` | file, repeatable | Yes | One or more supported documents. |
| `processing_mode` | string | No | `auto` (default) or `native_only`. |

The response contains `results`, `processed`, and `storage: "memory-only"`. Each result has `status` and `filename`. Successful results also contain Markdown, format/word/character counts, processing decision, context estimates, warnings, and evidence. Failed results contain an `error` message.

The endpoint enforces file count, file size, aggregate size, and upload rate limits. A batch can return a mixture of successful and failed file results.

CSV evidence includes an additional `evidence.tables` payload. It detects comma, semicolon, tab and pipe delimiters, and preserves the detected delimiter, original header text, disambiguated display labels, logical record numbers, one-based column indexes, spreadsheet-style column labels, exact string values and explicit empty-cell markers. Native cell indexing is capped at 5,000 cells per table; the Markdown table and original source are retained when this structural cap is reached.

## Persistent knowledge workspace

### `POST /api/knowledge/ingest`

Accepts the same repeated `files` and optional `processing_mode` fields as `/api/extract`, plus an optional `workspace_id`. It extracts each file and persists the original bytes in the local content-addressed blob store. Unchanged bytes reuse the existing source version; changed bytes create a new immutable version. The response includes the extraction result and a `knowledge` summary (`source_id`, `source_version_id`, `version_number`, node count and index metadata).

### `GET /api/knowledge/sources`

Lists current sources in a workspace.

### `GET /api/knowledge/sources/{source_id}/versions`

Lists immutable versions and extraction metadata for one source.

### `GET /api/knowledge/versions/{source_version_id}/nodes`

Returns the version's hierarchical knowledge nodes. CSV nodes include `table`, `column`, `row` and `cell` types. Cell locators identify the logical record, column, original header and empty-cell state.

### `GET /api/knowledge/sources/{source_id}/digest`

Returns the current deterministic extractive digest, lazily rebuilding it for older sources when necessary.

### `GET /api/knowledge/search?q={query}`

Searches current source versions using SQLite FTS5/BM25. Results retain source identity, version, node ID, locator and content hash. A CSV cell match is returned with its record and column provenance.

### `PATCH /api/knowledge/nodes/{node_id}`

Applies an audited correction to the working knowledge node and refreshes dependent digest/index artifacts. Correcting a CSV cell also regenerates its parent record summary so the old value does not remain searchable in the row. CSV cells may be intentionally cleared; the cell remains present with an explicit empty state. The immutable source bytes are not modified.

## Context rules

### `GET /api/context-rules`

Returns the saved `rules`, possible shared-tag overlaps, and precedence order.

### `POST /api/context-rules`

Creates a rule. JSON body:

```json
{
  "title": "Engineering standards",
  "scope": "project",
  "project_key": "context-studio",
  "tags": ["release", "docs"],
  "content": "Keep changes small and verify behavior with tests.",
  "priority": 50,
  "enabled": true
}
```

`scope` is `organization`, `project`, or `task`. Project and task rules require a `project_key`. Organization rules cannot have one. Tags are optional except that task rules need at least one tag to match. Priority is an integer from 0 to 100.

### `PUT /api/context-rules/{rule_id}`

Replaces the specified rule using the same JSON body as create.

### `DELETE /api/context-rules/{rule_id}`

Deletes one rule and returns `{ "deleted": true, "id": "..." }`.

## Agent context

### `GET /api/agent-context`

Query parameters:

| Parameter | Description |
| --- | --- |
| `project_key` | Optional project key. |
| `task_tags` | Optional comma-separated tags, up to 20. |

The response contains the requested context, matching rules, precedence, Markdown, rule count, and an approximate token count. The endpoint returns saved rules only. It never includes uploaded files or unsaved browser-session Markdown.

This endpoint has no authentication and is intended for loopback-only use. Do not expose it on a network.
