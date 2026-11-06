from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections import OrderedDict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import documents
from .documents import extract_document
from .rules import (
    ContextRuleInput, _agent_context_markdown, _database, _matching_context_rules,
    _normalise_rule, _read_context_rules, _rule_from_row,
)
from .knowledge_store import KnowledgeStore
from .settings import (
    DATABASE_PATH,
    MAX_BATCH_BYTES, MAX_BYTES, MAX_CONTEXT_PACK_CHARS, MAX_CONTEXT_RULES,
    MAX_FILES, MAX_SESSION_BYTES, MAX_SESSION_ERRORS, MAX_SESSION_FILES,
    MAX_TRACKED_CLIENTS, RATE_LIMIT, SUPPORTED,
)

logger = logging.getLogger("context_studio")
app = FastAPI(title="Context Studio", version="1.0.0", docs_url="/api/docs")
_request_times: OrderedDict[str, deque[float]] = OrderedDict()

def _allow_upload(client: str, now: float) -> bool:
    recent = _request_times.get(client)
    if recent is None:
        if len(_request_times) >= MAX_TRACKED_CLIENTS:
            _request_times.popitem(last=False)
        recent = deque()
        _request_times[client] = recent
    else:
        _request_times.move_to_end(client)
    while recent and now - recent[0] > 60:
        recent.popleft()
    if len(recent) >= RATE_LIMIT:
        return False
    recent.append(now)
    return True


@app.middleware("http")
async def security_headers(request: Request, call_next):
    def secure(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("Pragma", "no-cache")
        return response

    host = (request.url.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "testserver"}:
        return secure(JSONResponse({"error": "Invalid Host header."}, status_code=400))

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        if fetch_site == "cross-site":
            return secure(JSONResponse({"error": "Cross-origin state-changing requests are not allowed."}, status_code=403))
        if origin:
            try:
                parsed_origin = urlsplit(origin)
                origin_tuple = (parsed_origin.scheme.lower(), (parsed_origin.hostname or "").lower(), parsed_origin.port)
                request_tuple = (request.url.scheme.lower(), host, request.url.port)
            except ValueError:
                origin_tuple = ("", "", None)
                request_tuple = (request.url.scheme.lower(), host, request.url.port)
            if origin_tuple != request_tuple:
                return secure(JSONResponse({"error": "Cross-origin state-changing requests are not allowed."}, status_code=403))

    content_length = request.headers.get("content-length")
    upload_path = request.url.path in {"/api/extract", "/api/knowledge/ingest"}
    if content_length and upload_path:
        try:
            if int(content_length) > MAX_BATCH_BYTES + 2 * 1024 * 1024:
                return secure(JSONResponse({"error": f"Request exceeds the {MAX_BATCH_BYTES // (1024 * 1024)} MB batch limit."}, status_code=413))
        except ValueError:
            return secure(JSONResponse({"error": "Invalid request size."}, status_code=400))
    # Content-Length is optional for streamed/chunked requests. Count received
    # bytes as well so those requests cannot bypass the aggregate upload bound.
    body_limit = MAX_BATCH_BYTES + 2 * 1024 * 1024
    received_bytes = 0
    body_too_large = False
    if upload_path:
        original_receive = request.receive

        async def receive_with_limit():
            nonlocal received_bytes, body_too_large
            message = await original_receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > body_limit:
                    body_too_large = True
                    return {"type": "http.disconnect"}
            return message

        request._receive = receive_with_limit
    try:
        response = await call_next(request)
    except Exception:
        if body_too_large:
            return secure(JSONResponse({"error": f"Request exceeds the {MAX_BATCH_BYTES // (1024 * 1024)} MB batch limit."}, status_code=413))
        raise
    if body_too_large:
        return secure(JSONResponse({"error": f"Request exceeds the {MAX_BATCH_BYTES // (1024 * 1024)} MB batch limit."}, status_code=413))
    return secure(response)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version, "ocr_available": documents._ocr_available()}


@app.get("/api/config")
def public_config():
    """Return the same bounded upload settings the browser uses for validation."""
    return {
        "max_files": MAX_FILES,
        "max_file_bytes": MAX_BYTES,
        "max_batch_bytes": MAX_BATCH_BYTES,
        "max_session_files": MAX_SESSION_FILES,
        "max_session_errors": MAX_SESSION_ERRORS,
        "max_session_bytes": MAX_SESSION_BYTES,
        "max_context_pack_chars": MAX_CONTEXT_PACK_CHARS,
        "max_context_rules": MAX_CONTEXT_RULES,
        "supported_extensions": sorted(SUPPORTED),
    }


@app.get("/api/context-rules")
def list_context_rules():
    """List saved local rules in explicit organisation → project → task order."""
    return _read_context_rules()


@app.get("/api/agent-context")
def get_agent_context(project_key: str | None = None, task_tags: str = ""):
    """Expose matching saved rules to a local agent through a read-only pull API.

    Keep this service bound to loopback: the local rule store has no authentication
    or tenant isolation and must not be exposed as a public multi-user endpoint.
    """
    project_key = (project_key or "").strip().lower() or None
    if project_key and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", project_key):
        raise HTTPException(status_code=422, detail="Invalid project_key; use letters, numbers, dots, underscores and hyphens")
    if len(task_tags) > 659:
        raise HTTPException(status_code=422, detail="task_tags is too long; supply up to 20 tags of at most 32 characters each")
    tags = [tag.strip().lower() for tag in task_tags.split(",") if tag.strip()]
    if len(tags) > 20:
        raise HTTPException(status_code=422, detail="Supply no more than 20 task tags")
    if any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", tag) for tag in tags):
        raise HTTPException(status_code=422, detail="Invalid task_tags; use comma-separated letters, numbers, underscores and hyphens")
    tags = list(dict.fromkeys(tags))
    rules = _matching_context_rules(project_key, tags)
    markdown = _agent_context_markdown(project_key, tags, rules)
    if len(markdown) > MAX_CONTEXT_PACK_CHARS:
        raise HTTPException(status_code=413, detail=f"Matching agent context exceeds the {MAX_CONTEXT_PACK_CHARS:,}-character safety limit; narrow the project/task scope or shorten saved rules")
    return {
        "schema_version": "1.0",
        "context": {"project_key": project_key, "task_tags": tags},
        "precedence": ["organization", "project", "task"],
        "rule_count": len(rules),
        "rules": rules,
        "markdown": markdown,
        "estimated_tokens": (len(markdown) + 3) // 4,
        "token_estimation": "ceil(Markdown characters / 4); approximate only, not a model tokenizer",
        "source_policy": "Only explicitly saved rules are returned. Uploaded documents and browser-session context packs are not included.",
    }


@app.post("/api/context-rules", status_code=201)
def create_context_rule(rule: ContextRuleInput):
    values = _normalise_rule(rule)
    rule_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _database() as connection:
        # Serialize the count-and-insert pair so concurrent local requests cannot
        # exceed the configured library cap.
        connection.execute("BEGIN IMMEDIATE")
        count = connection.execute("SELECT COUNT(*) FROM context_rules").fetchone()[0]
        if count >= MAX_CONTEXT_RULES:
            raise HTTPException(status_code=409, detail=f"The local rule library is full ({MAX_CONTEXT_RULES} rules). Delete or consolidate a rule first.")
        duplicate = connection.execute(
            "SELECT 1 FROM context_rules WHERE scope=? AND project_key IS ? AND lower(title)=lower(?) AND tags_json=? AND content=? LIMIT 1",
            (values["scope"], values["project_key"], values["title"], json.dumps(values["tags"]), values["content"]),
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="An identical rule already exists in this scope. Edit the existing rule instead.")
        connection.execute(
            "INSERT INTO context_rules (id, title, scope, project_key, tags_json, content, priority, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rule_id, values["title"], values["scope"], values["project_key"], json.dumps(values["tags"]), values["content"], values["priority"], int(values["enabled"]), now, now),
        )
    return {"rule": {"id": rule_id, **values, "created_at": now, "updated_at": now}}


@app.put("/api/context-rules/{rule_id}")
def update_context_rule(rule_id: str, rule: ContextRuleInput):
    values = _normalise_rule(rule)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        duplicate = connection.execute(
            "SELECT 1 FROM context_rules WHERE id<>? AND scope=? AND project_key IS ? AND lower(title)=lower(?) AND tags_json=? AND content=? LIMIT 1",
            (rule_id, values["scope"], values["project_key"], values["title"], json.dumps(values["tags"]), values["content"]),
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="An identical rule already exists in this scope. Edit the existing rule instead.")
        cursor = connection.execute(
            "UPDATE context_rules SET title=?, scope=?, project_key=?, tags_json=?, content=?, priority=?, enabled=?, updated_at=? WHERE id=?",
            (values["title"], values["scope"], values["project_key"], json.dumps(values["tags"]), values["content"], values["priority"], int(values["enabled"]), now, rule_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Context rule not found")
        row = connection.execute("SELECT * FROM context_rules WHERE id=?", (rule_id,)).fetchone()
    return {"rule": _rule_from_row(row)}


@app.delete("/api/context-rules/{rule_id}")
def delete_context_rule(rule_id: str):
    with _database() as connection:
        cursor = connection.execute("DELETE FROM context_rules WHERE id=?", (rule_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Context rule not found")
    return {"deleted": True, "id": rule_id}


@app.post("/api/extract")
async def extract(
    request: Request,
    files: list[UploadFile] = File(...),
    processing_mode: Literal["auto", "native_only"] = Form("auto"),
):
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    if not _allow_upload(client, now):
        return JSONResponse({"error": "Upload rate limit reached. Wait a minute and try again."}, status_code=429)
    if not files:
        return JSONResponse({"error": "Choose at least one file."}, status_code=400)
    if len(files) > MAX_FILES:
        return JSONResponse({"error": f"Upload up to {MAX_FILES} files per batch."}, status_code=400)
    results = []
    total_bytes = 0
    for upload in files:
        name = Path(upload.filename or "untitled").name.replace("\x00", "")
        try:
            data = await upload.read(MAX_BYTES + 1)
            total_bytes += len(data)
            if total_bytes > MAX_BATCH_BYTES:
                results.append({"status": "error", "filename": name, "error": f"Batch exceeds the {MAX_BATCH_BYTES // (1024 * 1024)} MB total limit; remove some files and retry."})
                # Avoid parsing remaining files after aggregate budget is exhausted.
                for pending in files[len(results):]:
                    results.append({"status": "error", "filename": Path(pending.filename or "untitled").name, "error": "Not processed because the batch size limit was reached."})
                    await pending.close()
                break
            # Office/PDF parsing and OCR are CPU/blocking operations. Keep them
            # off the ASGI event loop so other uploads and health checks can run.
            extracted = await run_in_threadpool(extract_document, name, data, upload.content_type, processing_mode)
            results.append({"status": "success", **extracted})
        except (ValueError, json.JSONDecodeError) as exc:
            results.append({"status": "error", "filename": name, "error": str(exc)})
        except Exception as exc:
            logger.info("Extraction failed (%s)", type(exc).__name__)
            results.append({"status": "error", "filename": name, "error": "Could not read this file. Check its format, integrity, and whether it is password-protected."})
        finally:
            await upload.close()
    return {"results": results, "processed": len(results), "storage": "memory-only"}


class KnowledgeEditInput(BaseModel):
    content: str = Field(min_length=1, max_length=2_000_000)
    reason: str | None = Field(default=None, max_length=1000)


def _knowledge_store() -> KnowledgeStore:
    return KnowledgeStore(DATABASE_PATH.parent)


@app.post("/api/knowledge/ingest", status_code=201)
async def ingest_knowledge(
    request: Request,
    files: list[UploadFile] = File(...),
    workspace_id: str = Form("default"),
    processing_mode: Literal["auto", "native_only"] = Form("auto"),
):
    """Extract and persist sources into the local, versioned knowledge workspace."""
    workspace_id = workspace_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", workspace_id):
        raise HTTPException(status_code=422, detail="Invalid workspace_id")
    client = request.client.host if request.client else "unknown"
    if not _allow_upload(client, time.monotonic()):
        return JSONResponse({"error": "Upload rate limit reached. Wait a minute and try again."}, status_code=429)
    if not files:
        return JSONResponse({"error": "Choose at least one file."}, status_code=400)
    if len(files) > MAX_FILES:
        return JSONResponse({"error": f"Upload up to {MAX_FILES} files per batch."}, status_code=400)

    store = _knowledge_store()
    results = []
    total_bytes = 0
    for index, upload in enumerate(files):
        name = Path(upload.filename or "untitled").name.replace("\x00", "")
        try:
            data = await upload.read(MAX_BYTES + 1)
            total_bytes += len(data)
            if len(data) > MAX_BYTES:
                raise ValueError(f"File exceeds the {MAX_BYTES // (1024 * 1024)} MB limit")
            if total_bytes > MAX_BATCH_BYTES:
                raise ValueError(f"Batch exceeds the {MAX_BATCH_BYTES // (1024 * 1024)} MB total limit")
            extracted = await run_in_threadpool(extract_document, name, data, upload.content_type, processing_mode)
            persisted = await run_in_threadpool(store.ingest, name, data, extracted, workspace_id)
            results.append({"status": "success", **extracted, "knowledge": persisted})
        except (ValueError, json.JSONDecodeError) as exc:
            results.append({"status": "error", "filename": name, "error": str(exc)})
        except Exception as exc:
            logger.info("Knowledge ingestion failed (%s)", type(exc).__name__)
            results.append({"status": "error", "filename": name, "error": "Could not safely ingest this file. Check its format, integrity, and available disk space."})
        finally:
            await upload.close()
        if total_bytes > MAX_BATCH_BYTES:
            for pending in files[index + 1:]:
                results.append({"status": "error", "filename": Path(pending.filename or "untitled").name, "error": "Not processed because the batch size limit was reached."})
                await pending.close()
            break
    return {"results": results, "processed": len(results), "storage": "local_persistent", "workspace_id": workspace_id}


@app.get("/api/knowledge/sources")
def list_knowledge_sources(workspace_id: str = "default"):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", workspace_id):
        raise HTTPException(status_code=422, detail="Invalid workspace_id")
    return {"sources": _knowledge_store().list_sources(workspace_id)}


@app.get("/api/knowledge/sources/{source_id}/versions")
def list_knowledge_versions(source_id: str):
    versions = _knowledge_store().list_versions(source_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return {"versions": versions}


@app.get("/api/knowledge/versions/{source_version_id}/nodes")
def list_knowledge_nodes(source_version_id: str):
    store = _knowledge_store()
    if not store.get_version(source_version_id):
        raise HTTPException(status_code=404, detail="Source version not found")
    return {"nodes": store.list_nodes(source_version_id)}


@app.get("/api/knowledge/sources/{source_id}/digest")
def get_knowledge_digest(source_id: str):
    digest = _knowledge_store().get_or_build_digest(source_id)
    if digest is None:
        raise HTTPException(status_code=404, detail="Current document digest not found")
    return {"digest": digest}


@app.get("/api/knowledge/search")
def search_knowledge(
    q: str = Query(min_length=1, max_length=500),
    workspace_id: str = "default",
    limit: int = Query(default=10, ge=1, le=100),
):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", workspace_id):
        raise HTTPException(status_code=422, detail="Invalid workspace_id")
    try:
        results = _knowledge_store().search(q, workspace_id, limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"query": q, "results": results, "count": len(results), "ranking": "SQLite FTS5 BM25; lower score ranks higher"}


@app.patch("/api/knowledge/nodes/{node_id}")
def edit_knowledge_node(node_id: str, edit: KnowledgeEditInput):
    try:
        return {"edit": _knowledge_store().edit_node(node_id, edit.content, edit.reason)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Knowledge node not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
