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
