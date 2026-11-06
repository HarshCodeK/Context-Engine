from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunking import structure_aware_chunks
from .document_structure import split_evidence_block
from .knowledge_schema import initialize_knowledge_db
from .summarization import build_extractive_digest
from .settings import MAX_TABLE_COLUMNS, MAX_TABLE_ROWS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _native_table_nodes(
    table: dict[str, Any], parent_node_key: str | None, start_ordinal: int
) -> list[dict[str, Any]]:
    """Expand an extractor table record into stable table → row → cell nodes."""
    table_key = str(table.get("table_key") or "")
    headers = table.get("headers")
    rows = table.get("rows")
    locator = table.get("locator")
    if not table_key or not isinstance(headers, list) or not isinstance(rows, list) or not isinstance(locator, dict):
        raise ValueError("Native table evidence is missing its stable key, headers, rows or locator")
    if len(headers) > MAX_TABLE_COLUMNS or len(rows) > MAX_TABLE_ROWS:
        raise ValueError("Native table evidence exceeds the configured structural bounds")

    def make_node(
        node_key: str,
        parent_key: str | None,
        node_type: str,
        title: str | None,
        content: str,
        node_locator: dict[str, Any],
        ordinal: int,
    ) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "node_key": node_key,
            "parent_node_key": parent_key,
            "ordinal": ordinal,
            "node_type": node_type,
            "title": title,
            "content": content,
            "locator_json": json.dumps(node_locator, ensure_ascii=False, sort_keys=True),
            "content_sha256": _sha256(content),
        }

    table_title = str(table.get("title") or "Table")
    table_node_key = f"{table_key}:table"
    result = [make_node(
        table_node_key,
        parent_node_key,
        "table",
        table_title,
        f"{table_title} · {len(rows)} data rows · {len(headers)} columns",
        locator,
        start_ordinal,
    )]

    for header in headers:
        if not isinstance(header, dict):
            raise ValueError("Native table header evidence is malformed")
        column_index = header.get("column_index")
        if not isinstance(column_index, int) or not 1 <= column_index <= MAX_TABLE_COLUMNS:
            raise ValueError("Native table header evidence has an invalid column index")
        column_label = str(header.get("column_label") or "")
        header_value = str(header.get("value") or "")
        header_label = str(header.get("label") or f"Column {column_index}")
        result.append(make_node(
            f"{table_key}:column:{column_index}",
            table_node_key,
            "column",
            header_label,
            header_value,
            {
                **locator,
                "type": "csv_column",
                "column": column_index,
                "column_label": column_label,
                "header": header_value,
                "header_label": header_label,
            },
            start_ordinal + len(result),
        ))

    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("cells"), list):
            raise ValueError("Native table row evidence is malformed")
        row_number = row.get("row_number")
        values = row.get("values")
        if not isinstance(row_number, int) or row_number < 2 or not isinstance(values, list):
            raise ValueError("Native table row evidence has an invalid record number or values")
        row_key = f"{table_key}:row:{row_number}"
        row_parts = []
        for index, value in enumerate(values):
            header = headers[index] if index < len(headers) else {}
            label = str(header.get("label") or f"Column {index + 1}") if isinstance(header, dict) else f"Column {index + 1}"
            text_value = str(value if value is not None else "")
            row_parts.append(f"{label}: {text_value if text_value else '[blank]'}")
        row_headers = [
            str(header.get("label") or f"Column {index + 1}") if isinstance(header, dict) else f"Column {index + 1}"
            for index, header in enumerate(headers)
        ]
        row_locator = {
            **locator,
            "type": "csv_row",
            "row": row_number,
            "headers_json": json.dumps(row_headers, ensure_ascii=False, separators=(",", ":")),
            "values_json": json.dumps(values, ensure_ascii=False, separators=(",", ":")),
        }
        result.append(make_node(
            row_key,
            table_node_key,
            "row",
            f"Record {row_number}",
            " | ".join(row_parts),
            row_locator,
            start_ordinal + len(result),
        ))

        for cell in row["cells"]:
            if not isinstance(cell, dict):
                raise ValueError("Native table cell evidence is malformed")
            column_index = cell.get("column_index")
            if not isinstance(column_index, int) or not 1 <= column_index <= MAX_TABLE_COLUMNS:
                raise ValueError("Native table cell evidence has an invalid column index")
            value = cell.get("value")
            if not isinstance(value, str):
                raise ValueError("Native table cell values must remain strings")
            cell_key = f"{row_key}:cell:{column_index}"
            cell_locator = {
                **locator,
                "type": "csv_cell",
                "row": row_number,
                "column": column_index,
                "column_label": str(cell.get("column_label") or ""),
                "header": str(cell.get("header") or ""),
                "header_label": str(cell.get("header_label") or f"Column {column_index}"),
                "is_empty": value == "",
            }
            result.append(make_node(
                cell_key,
                row_key,
                "cell",
                cell_locator["header_label"],
                value,
                cell_locator,
                start_ordinal + len(result),
            ))
    return result


class KnowledgeStore:
    """Local source/version store with immutable content-addressed source blobs."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.database_path = self.data_dir / "knowledge.sqlite3"
        self.blob_dir = self.data_dir / "source_blobs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        initialize_knowledge_db(self.database_path)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(str(self.database_path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _store_blob(self, content: bytes, digest: str) -> str:
        relative = Path(digest[:2]) / digest
        destination = (self.blob_dir / relative).resolve()
        if self.blob_dir not in destination.parents:
            raise ValueError("Invalid content-addressed storage key")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if _sha256(destination.read_bytes()) != digest:
                raise RuntimeError("Existing source blob failed its integrity check")
            return relative.as_posix()

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=".incoming-", delete=False
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
        return relative.as_posix()

    def ingest(
        self,
        filename: str,
        content: bytes,
        extraction: dict[str, Any],
        workspace_id: str = "default",
    ) -> dict[str, Any]:
        """Persist one extraction, creating a source version only when bytes change."""
        display_name = Path(filename).name.strip()
        if not display_name or not content:
            raise ValueError("A non-empty filename and source file are required")
        digest = _sha256(content)
        markdown = extraction.get("markdown")
        evidence = extraction.get("evidence") or {}
        blocks = evidence.get("blocks")
        if not isinstance(markdown, str) or not isinstance(blocks, list):
            raise ValueError("Extraction result is missing Markdown or evidence blocks")
        if evidence.get("source_sha256") != digest or evidence.get("source_id") != digest:
            raise ValueError("Extraction evidence does not match the uploaded source bytes")

        prepared_nodes = []
        native_tables = list(evidence.get("tables") or [])
        if not isinstance(evidence.get("tables") or [], list):
            raise ValueError("Extraction table evidence must be a list")
        for block in blocks:
            locator = block.get("locator")
            span = block.get("markdown_range")
            if not isinstance(locator, dict) or not isinstance(span, dict):
                raise ValueError("Evidence block is missing its source locator or Markdown range")
            start, end = span.get("start"), span.get("end")
            if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or end > len(markdown):
                raise ValueError("Evidence block contains an invalid Markdown range")
            block_text = markdown[start:end]
            if block.get("content_sha256") != _sha256(block_text):
                raise ValueError("Evidence block content hash does not match its Markdown range")
            block_id = str(block.get("block_id") or "")
            if not block_id:
                raise ValueError("Evidence block is missing a stable block ID")
            for structured in split_evidence_block(
                markdown,
                markdown_start=start,
                markdown_end=end,
                source_locator=locator,
                block_id=block_id,
            ):
                structured_locator = structured["locator_json"]
                if (
                    structured["node_type"] == "table"
                    and structured_locator.get("type") == "csv_table"
                    and native_tables
                ):
                    native_table = native_tables.pop(0)
                    native_table = {
                        **native_table,
                        "locator": {**structured_locator, **native_table.get("locator", {})},
                    }
                    prepared_nodes.extend(
                        _native_table_nodes(native_table, structured["parent_node_key"], len(prepared_nodes))
                    )
                    continue
                prepared_nodes.append({
                    "id": str(uuid.uuid4()),
                    "node_key": structured["node_key"],
                    "parent_node_key": structured["parent_node_key"],
                    "ordinal": len(prepared_nodes),
                    "node_type": structured["node_type"],
                    "title": structured["title"],
                    "content": structured["content"],
                    "locator_json": json.dumps(structured["locator_json"], ensure_ascii=False, sort_keys=True),
                    "content_sha256": structured["content_sha256"],
                })

        # A malformed or future extractor may provide table metadata without a
        # matching Markdown table block. Keep it inspectable as a root node tree
        # rather than silently dropping source evidence.
        for native_table in native_tables:
            prepared_nodes.extend(_native_table_nodes(native_table, None, len(prepared_nodes)))

        storage_key = self._store_blob(content, digest)
        timestamp = _now()
        metadata = {
            "format": extraction.get("format"),
            "pages": extraction.get("pages"),
            "warnings": extraction.get("warnings") or [],
            "processing": extraction.get("processing") or {},
            "characters": extraction.get("characters"),
            "words": extraction.get("words"),
        }
        extraction_status = "partial" if metadata["warnings"] else "complete"

        with self._connection() as connection:
            connection.execute(
                """INSERT INTO workspaces(id, name, created_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at""",
                (workspace_id, workspace_id, timestamp, timestamp),
            )
            source = connection.execute(
                """SELECT id, current_version_id FROM sources
                   WHERE workspace_id = ? AND display_name = ? COLLATE NOCASE
                   ORDER BY created_at LIMIT 1""",
                (workspace_id, display_name),
            ).fetchone()
            if source is None:
                source_id = str(uuid.uuid4())
                connection.execute(
                    """INSERT INTO sources(id, workspace_id, display_name, media_type, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (source_id, workspace_id, display_name, None, timestamp, timestamp),
                )
            else:
                source_id = source["id"]

            existing = connection.execute(
                """SELECT id, version_number FROM source_versions
                   WHERE source_id = ? AND content_sha256 = ?""",
                (source_id, digest),
            ).fetchone()
            if existing:
                created = False
                version_id = existing["id"]
                version_number = existing["version_number"]
                reactivated = source is not None and source["current_version_id"] != version_id
                if reactivated:
                    connection.execute(
                        """UPDATE derived_artifacts SET status = 'current', updated_at = ?
                           WHERE source_version_id = ? AND status = 'superseded'""",
                        (timestamp, version_id),
                    )
            else:
                created = True
                reactivated = False
                latest = connection.execute(
                    "SELECT COALESCE(MAX(version_number), 0) FROM source_versions WHERE source_id = ?",
                    (source_id,),
                ).fetchone()[0]
                version_number = latest + 1
                version_id = str(uuid.uuid4())
                connection.execute(
                    """INSERT INTO source_versions(
                           id, source_id, version_number, content_sha256, byte_size,
                           storage_key, file_extension, extraction_status,
                           extraction_metadata_json, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        version_id, source_id, version_number, digest, len(content),
                        storage_key, Path(display_name).suffix.lower(),
                        extraction_status, json.dumps(metadata, ensure_ascii=False), timestamp,
                    ),
                )
                if latest:
                    connection.execute(
                        """UPDATE derived_artifacts SET status = 'superseded', updated_at = ?
                           WHERE source_version_id IN (
                               SELECT id FROM source_versions WHERE source_id = ? AND id != ?
                           ) AND status = 'current'""",
                        (timestamp, source_id, version_id),
                    )
                node_ids = {node["node_key"]: node["id"] for node in prepared_nodes}
                for node in prepared_nodes:
                    parent_key = node["parent_node_key"]
                    parent_id = node_ids.get(parent_key) if parent_key else None
                    if parent_key and parent_id is None:
                        raise ValueError("Structured node references an unknown parent")
                    connection.execute(
                        """INSERT INTO document_nodes(
                               id, source_version_id, parent_node_id, node_key, ordinal,
                               node_type, title, content, locator_json, content_sha256,
                               origin, created_at, updated_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'extracted', ?, ?)""",
                        (
                            node["id"], version_id, parent_id, node["node_key"], node["ordinal"],
                            node["node_type"], node["title"], node["content"], node["locator_json"],
                            node["content_sha256"], timestamp, timestamp,
                        ),
                    )
                artifact_id = str(uuid.uuid4())
                artifact_payload = json.dumps(
                    {"markdown": markdown, "evidence": evidence},
                    ensure_ascii=False, separators=(",", ":"),
                )
                connection.execute(
                    """INSERT INTO derived_artifacts(
                           id, source_version_id, artifact_type, artifact_key,
                           content_json, content_sha256, status, generator,
                           generator_version, created_at, updated_at
                       ) VALUES (?, ?, 'extraction', 'native-parser', ?, ?, 'current',
                                 'context-studio-extractor', '1', ?, ?)""",
                    (artifact_id, version_id, artifact_payload, _sha256(artifact_payload), timestamp, timestamp),
                )
                connection.execute(
                    """INSERT INTO artifact_dependencies(
                           artifact_id, dependency_type, dependency_id, dependency_sha256
                       ) VALUES (?, 'source_version', ?, ?)""",
                    (artifact_id, version_id, digest),
                )

            connection.execute(
                """UPDATE sources SET display_name = ?, updated_at = ?, current_version_id = ?
                   WHERE id = ?""",
                (display_name, timestamp, version_id, source_id),
            )

        chunk_count = self.rebuild_index(version_id) if created or reactivated else None
        # Also backfill a missing digest when identical bytes are re-ingested
        # (for example, sources created before digest generation was added).
        document_digest = self.get_or_build_digest(source_id)
        return {
            "source_id": source_id,
            "source_version_id": version_id,
            "version_number": version_number,
            "content_sha256": digest,
            "storage_key": storage_key,
            "node_count": len(prepared_nodes),
            "created_new_version": created,
            "chunk_count": chunk_count,
            "digest_characters": document_digest["summary_characters"] if document_digest else None,
        }

    def read_source_bytes(self, source_version_id: str) -> bytes:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT content_sha256, storage_key FROM source_versions WHERE id = ?",
                (source_version_id,),
            ).fetchone()
        if row is None:
            raise KeyError("Source version not found")
        relative = Path(row["storage_key"])
        path = (self.blob_dir / relative).resolve()
        if self.blob_dir not in path.parents or not path.is_file():
            raise FileNotFoundError("Stored source blob is missing")
        content = path.read_bytes()
        if _sha256(content) != row["content_sha256"]:
            raise RuntimeError("Stored source blob failed its integrity check")
        return content

    def list_sources(self, workspace_id: str = "default") -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT s.id, s.display_name, s.created_at, s.updated_at,
                          v.id AS source_version_id, v.version_number,
                          v.content_sha256, v.byte_size, v.extraction_status
                   FROM sources s
                   LEFT JOIN source_versions v ON v.id = s.current_version_id
                   WHERE s.workspace_id = ?
                   ORDER BY s.updated_at DESC, s.display_name COLLATE NOCASE""",
                (workspace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_version(self, source_version_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT id AS source_version_id, source_id, version_number,
                          content_sha256, byte_size, file_extension,
                          extraction_status, created_at
                   FROM source_versions WHERE id = ?""",
                (source_version_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_versions(self, source_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT id AS source_version_id, version_number, content_sha256,
                          byte_size, file_extension, extraction_status,
                          extraction_metadata_json, created_at
                   FROM source_versions WHERE source_id = ? ORDER BY version_number DESC""",
                (source_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["extraction_metadata"] = json.loads(item.pop("extraction_metadata_json"))
            result.append(item)
        return result

    def list_nodes(self, source_version_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT id, parent_node_id, node_key, ordinal, node_type, title, content,
                          locator_json, content_sha256, origin
                   FROM document_nodes WHERE source_version_id = ? ORDER BY ordinal""",
                (source_version_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["locator"] = json.loads(item.pop("locator_json"))
            result.append(item)
        return result

    def edit_node(self, node_id: str, new_content: str, reason: str | None = None) -> dict[str, Any]:
        """Apply a user correction to canonical knowledge and stale dependent artifacts."""
        if not isinstance(new_content, str):
            raise ValueError("Edited knowledge text must be a string")
        timestamp = _now()
        changed_node_ids = [node_id]
        with self._connection() as connection:
            row = connection.execute(
                """SELECT id, source_version_id, parent_node_id, node_type,
                          locator_json, content, content_sha256
                   FROM document_nodes WHERE id = ?""",
                (node_id,),
            ).fetchone()
            if row is None:
                raise KeyError("Knowledge node not found")
            if row["node_type"] != "cell" and not new_content.strip():
                raise ValueError("Edited knowledge text cannot be empty")
            before = {"content": row["content"], "content_sha256": row["content_sha256"]}
            after = {"content": new_content, "content_sha256": _sha256(new_content)}
            edit_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO knowledge_edits(
                       id, source_version_id, document_node_id, edit_type,
                       before_json, after_json, reason, created_at
                   ) VALUES (?, ?, ?, 'correct_extraction', ?, ?, ?, ?)""",
                (
                    edit_id, row["source_version_id"], node_id,
                    json.dumps(before, ensure_ascii=False),
                    json.dumps(after, ensure_ascii=False),
                    (reason or "").strip() or None, timestamp,
                ),
            )
            cell_locator = json.loads(row["locator_json"])
            if cell_locator.get("type") == "csv_cell":
                cell_locator["is_empty"] = new_content == ""
            connection.execute(
                """UPDATE document_nodes
                   SET content = ?, content_sha256 = ?, locator_json = ?,
                       origin = 'user_edited', updated_at = ?
                   WHERE id = ?""",
                (
                    new_content, after["content_sha256"],
                    json.dumps(cell_locator, ensure_ascii=False, sort_keys=True), timestamp, node_id,
                ),
            )
            # A CSV row is a searchable composite of its original cells. Keep
            # that parent record in sync when one child cell is corrected, or
            # the old value would remain discoverable beside the new one.
            if cell_locator.get("type") == "csv_cell" and row["parent_node_id"]:
                parent = connection.execute(
                    """SELECT id, source_version_id, locator_json, content, content_sha256, node_type
                       FROM document_nodes WHERE id = ?""",
                    (row["parent_node_id"],),
                ).fetchone()
                if parent and parent["node_type"] == "row":
                    parent_locator = json.loads(parent["locator_json"])
                    try:
                        values = json.loads(parent_locator.get("values_json", "[]"))
                        headers = json.loads(parent_locator.get("headers_json", "[]"))
                        column_index = int(cell_locator.get("column", 0))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        values, headers, column_index = [], [], 0
                    if 1 <= column_index <= len(values):
                        values[column_index - 1] = new_content
                        parts = []
                        for index, value in enumerate(values):
                            label = headers[index] if index < len(headers) else f"Column {index + 1}"
                            parts.append(f"{label}: {value if value else '[blank]'}")
                        updated_row = " | ".join(parts)
                        parent_locator["values_json"] = json.dumps(
                            values, ensure_ascii=False, separators=(",", ":")
                        )
                        parent_before = {
                            "content": parent["content"],
                            "content_sha256": parent["content_sha256"],
                        }
                        parent_after = {
                            "content": updated_row,
                            "content_sha256": _sha256(updated_row),
                        }
                        connection.execute(
                            """INSERT INTO knowledge_edits(
                                   id, source_version_id, document_node_id, edit_type,
                                   before_json, after_json, reason, created_at
                               ) VALUES (?, ?, ?, 'correct_extraction', ?, ?, ?, ?)""",
                            (
                                str(uuid.uuid4()), parent["source_version_id"], parent["id"],
                                json.dumps(parent_before, ensure_ascii=False),
                                json.dumps(parent_after, ensure_ascii=False),
                                "Row summary refreshed after cell correction",
                                timestamp,
                            ),
                        )
                        connection.execute(
                            """UPDATE document_nodes
                               SET content = ?, content_sha256 = ?, locator_json = ?,
                                   origin = 'user_edited', updated_at = ?
                               WHERE id = ?""",
                            (
                                updated_row, parent_after["content_sha256"],
                                json.dumps(parent_locator, ensure_ascii=False, sort_keys=True),
                                timestamp, parent["id"],
                            ),
                        )
                        changed_node_ids.append(parent["id"])

            for changed_node_id in changed_node_ids:
                connection.execute(
                    """UPDATE derived_artifacts SET status = 'stale', updated_at = ?
                       WHERE id IN (
                           SELECT artifact_id FROM artifact_dependencies
                           WHERE dependency_type = 'document_node' AND dependency_id = ?
                       ) AND status = 'current'""",
                    (timestamp, changed_node_id),
                )
        self.rebuild_index(row["source_version_id"])
        self.build_digest(row["source_version_id"])
        return {"edit_id": edit_id, "node_id": node_id, "content_sha256": after["content_sha256"]}


    def rebuild_index(
        self, source_version_id: str, max_chars: int = 1200, overlap_chars: int = 120
    ) -> int:
        """Rebuild the deterministic FTS5 index for one source version."""
        timestamp = _now()
        with self._connection() as connection:
            version = connection.execute(
                """SELECT v.source_id, s.current_version_id
                   FROM source_versions v JOIN sources s ON s.id = v.source_id
                   WHERE v.id = ?""",
                (source_version_id,),
            ).fetchone()
            if version is None:
                raise KeyError("Source version not found")
            if version["current_version_id"] != source_version_id:
                raise ValueError("Only the current source version can be indexed")
            nodes = connection.execute(
                """SELECT id, title, content, locator_json, content_sha256
                   FROM document_nodes WHERE source_version_id = ? ORDER BY ordinal""",
                (source_version_id,),
            ).fetchall()
            connection.execute("DELETE FROM retrieval_chunks WHERE source_version_id = ?", (source_version_id,))
            chunk_count = 0
            dependency_hashes = []
            for node in nodes:
                title = node["title"] or ""
                chunks = structure_aware_chunks(node["content"], max_chars, overlap_chars)
                for ordinal, chunk in enumerate(chunks):
                    chunk_id = str(uuid.uuid4())
                    digest = _sha256(chunk)
                    cursor = connection.execute(
                        """INSERT INTO retrieval_chunks(
                               id, source_version_id, document_node_id, ordinal,
                               title, content, content_sha256, token_estimate, locator_json
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            chunk_id, source_version_id, node["id"], ordinal,
                            title, chunk, digest, (len(chunk) + 3) // 4, node["locator_json"],
                        ),
                    )
                    fts_rowid = cursor.lastrowid
                    connection.execute(
                        """INSERT INTO retrieval_fts(rowid, chunk_id, source_version_id,
                                                      document_node_id, title, content)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (fts_rowid, chunk_id, source_version_id, node["id"], title, chunk),
                    )
                    chunk_count += 1
                dependency_hashes.append((node["id"], node["content_sha256"]))

            connection.execute(
                """UPDATE derived_artifacts SET status = 'stale', updated_at = ?
                   WHERE source_version_id = ? AND artifact_type = 'lexical_index' AND status = 'current'""",
                (timestamp, source_version_id),
            )
            index_payload = json.dumps(
                {"chunk_count": chunk_count, "max_chars": max_chars, "overlap_chars": overlap_chars},
                sort_keys=True, separators=(",", ":"),
            )
            index_hash = _sha256(index_payload + json.dumps(dependency_hashes, separators=(",", ":")))
            existing_index = connection.execute(
                """SELECT id FROM derived_artifacts
                   WHERE source_version_id = ? AND artifact_type = 'lexical_index'
                         AND artifact_key = 'sqlite-fts5'""",
                (source_version_id,),
            ).fetchone()
            if existing_index:
                artifact_id = existing_index["id"]
                connection.execute("DELETE FROM artifact_dependencies WHERE artifact_id = ?", (artifact_id,))
                connection.execute(
                    """UPDATE derived_artifacts SET content_json = ?, content_sha256 = ?,
                              status = 'current', generator = 'context-studio-chunker',
                              generator_version = '1', updated_at = ? WHERE id = ?""",
                    (index_payload, index_hash, timestamp, artifact_id),
                )
            else:
                artifact_id = str(uuid.uuid4())
                connection.execute(
                    """INSERT INTO derived_artifacts(
                           id, source_version_id, artifact_type, artifact_key, content_json,
                           content_sha256, status, generator, generator_version, created_at, updated_at
                       ) VALUES (?, ?, 'lexical_index', 'sqlite-fts5', ?, ?, 'current',
                                 'context-studio-chunker', '1', ?, ?)""",
                    (artifact_id, source_version_id, index_payload, index_hash, timestamp, timestamp),
                )
            for node_id, node_hash in dependency_hashes:
                connection.execute(
                    """INSERT INTO artifact_dependencies(
                           artifact_id, dependency_type, dependency_id, dependency_sha256
                       ) VALUES (?, 'document_node', ?, ?)""",
                    (artifact_id, node_id, node_hash),
                )
        return chunk_count

    def search(self, query: str, workspace_id: str = "default", limit: int = 10) -> list[dict[str, Any]]:
        """Search current workspace sources with inspectable SQLite BM25 ranking."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
        if not terms:
            return []
        match_query = " AND ".join('"' + term.replace('"', '""') + '"' for term in terms[:20])
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT c.id AS chunk_id, c.source_version_id, c.document_node_id,
                          c.ordinal, c.title, c.content, c.content_sha256,
                          c.token_estimate, c.locator_json, s.id AS source_id,
                          s.display_name, v.version_number,
                          bm25(retrieval_fts, 0.0, 0.0, 0.0, 2.0, 1.0) AS rank_score
                   FROM retrieval_fts
                   JOIN retrieval_chunks c ON c.fts_rowid = retrieval_fts.rowid
                   JOIN source_versions v ON v.id = c.source_version_id
                   JOIN sources s ON s.id = v.source_id AND s.current_version_id = v.id
                   WHERE retrieval_fts MATCH ? AND s.workspace_id = ?
                   ORDER BY rank_score ASC LIMIT ?""",
                (match_query, workspace_id, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["locator"] = json.loads(item.pop("locator_json"))
            result.append(item)
        return result

    def build_digest(self, source_version_id: str) -> dict[str, Any]:
        """Build and cache a deterministic, provenance-linked extractive document digest."""
        version = self.get_version(source_version_id)
        if version is None:
            raise KeyError("Source version not found")
        nodes = self.list_nodes(source_version_id)
        digest = build_extractive_digest(nodes)
        payload = json.dumps(digest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest_hash = _sha256(payload)
        timestamp = _now()
        with self._connection() as connection:
            existing = connection.execute(
                """SELECT id FROM derived_artifacts
                   WHERE source_version_id = ? AND artifact_type = 'document_digest'
                         AND artifact_key = 'extractive-tfidf-v1'""",
                (source_version_id,),
            ).fetchone()
            if existing:
                artifact_id = existing["id"]
                connection.execute("DELETE FROM artifact_dependencies WHERE artifact_id = ?", (artifact_id,))
                connection.execute(
                    """UPDATE derived_artifacts SET content_json = ?, content_sha256 = ?,
                              status = 'current', updated_at = ? WHERE id = ?""",
                    (payload, digest_hash, timestamp, artifact_id),
                )
            else:
                artifact_id = str(uuid.uuid4())
                connection.execute(
                    """INSERT INTO derived_artifacts(
                           id, source_version_id, artifact_type, artifact_key, content_json,
                           content_sha256, status, generator, generator_version, created_at, updated_at
                       ) VALUES (?, ?, 'document_digest', 'extractive-tfidf-v1', ?, ?, 'current',
                                 'context-studio-extractive-summarizer', '1', ?, ?)""",
                    (artifact_id, source_version_id, payload, digest_hash, timestamp, timestamp),
                )
            connection.execute(
                """INSERT INTO artifact_dependencies(
                       artifact_id, dependency_type, dependency_id, dependency_sha256
                   ) VALUES (?, 'source_version', ?, ?)""",
                (artifact_id, source_version_id, version["content_sha256"]),
            )
            for node in nodes:
                connection.execute(
                    """INSERT INTO artifact_dependencies(
                           artifact_id, dependency_type, dependency_id, dependency_sha256
                       ) VALUES (?, 'document_node', ?, ?)""",
                    (artifact_id, node["id"], node["content_sha256"]),
                )
        return digest

    def get_digest(self, source_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT a.content_json, a.content_sha256, a.updated_at, v.id AS source_version_id,
                          v.version_number
                   FROM sources s
                   JOIN source_versions v ON v.id = s.current_version_id
                   JOIN derived_artifacts a ON a.source_version_id = v.id
                   WHERE s.id = ? AND a.artifact_type = 'document_digest'
                         AND a.status = 'current'""",
                (source_id,),
            ).fetchone()
        if row is None:
            return None
        result = json.loads(row["content_json"])
        result.update({
            "source_version_id": row["source_version_id"],
            "version_number": row["version_number"],
            "content_sha256": row["content_sha256"],
            "updated_at": row["updated_at"],
        })
        return result

    def get_or_build_digest(self, source_id: str) -> dict[str, Any] | None:
        """Return the current digest, lazily rebuilding it for older records."""
        digest = self.get_digest(source_id)
        if digest is not None:
            return digest
        with self._connection() as connection:
            row = connection.execute(
                "SELECT current_version_id FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()
        if row is None or not row["current_version_id"]:
            return None
        self.build_digest(row["current_version_id"])
        return self.get_digest(source_id)
