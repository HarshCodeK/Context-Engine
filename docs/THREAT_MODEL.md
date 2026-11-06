# Threat model

## Trust boundary

Context Studio is a single-user application bound to `127.0.0.1`. Uploaded documents are untrusted input. Saved context rules are user-authored instructions that are returned to a local agent only when explicitly requested.

The application is not designed for a shared network, public hosting, or multiple tenants. The agent context endpoint has no authentication and must not be exposed outside loopback.

## Main risks and controls

| Risk | Control |
| --- | --- |
| Oversized upload or batch | Browser checks plus server-side per-file, file-count, aggregate-body, and session limits. Streamed requests are counted even when `Content-Length` is absent. |
| Extension spoofing or malformed Office file | Validate actual content and Office ZIP members before parsing. |
| Archive/XML resource abuse | Bound archive members, extracted text, document pages, table dimensions, slides, shapes, and paragraphs. |
| Image decompression or OCR time abuse | Pixel limits, page limits, per-page timeout, and total OCR timeout. |
| Upload flood | Per-client upload rate limit with bounded tracking state. |
| Cross-site state-changing request | Validate Host, Origin, and Fetch Metadata for POST/PUT/PATCH/DELETE. |
| Browser script injection | Local same-origin assets, restrictive script policy, no inline script, no object/embed, no framing. |
| MIME confusion and clickjacking | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and same-origin resource policy. |
| Sensitive API response caching | `Cache-Control: no-store` and `Pragma: no-cache` for API routes. |
| Rule-library cap race | SQLite `BEGIN IMMEDIATE` around the count-and-insert operation. |
| Accidental document retention | Uploaded files are processed in memory; only explicitly saved context rules persist. |
| Agent receives unrelated source data | Agent endpoint returns saved matching rules only; it never includes uploaded documents or browser-session content. |

## Content Security Policy

The app serves scripts and styles from the local origin. Inline scripts, inline style elements, and style attributes are blocked. Native select and progress controls avoid runtime positioning styles, and the remaining UI uses external CSS. No user-provided HTML is rendered as trusted markup.

## Data handling

- Uploaded bytes are not stored as source files.
- Extraction responses include source hashes and evidence metadata, but the response remains in the browser session unless the user exports it.
- Context rules are stored in a local SQLite database under `data/`.
- The local API binds to loopback and does not use a hosted service.
- No hosted model is called during extraction or context-pack assembly.

## Remaining limits

- Local loopback is not a substitute for authentication if the app is ever exposed to another machine or user.
- A malicious local process can call the API because the service assumes a trusted local user session.
- A document can contain misleading instructions or false information. Extraction preserves content; it does not certify factual accuracy.
- A future local summarizer must treat document text as untrusted input, quote or reference source evidence, enforce a timeout and output cap, and remain opt-in.
- Screenshots and browser DOM inspection do not prove full accessibility. Keyboard-only, screen-reader, and assistive-technology testing remains part of release QA.
