from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    media_type TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    current_version_id TEXT REFERENCES source_versions(id),
    UNIQUE(workspace_id, id),
    FOREIGN KEY(id, current_version_id) REFERENCES source_versions(source_id, id)
);
CREATE INDEX idx_sources_workspace_updated ON sources(workspace_id, updated_at DESC);

CREATE TABLE source_versions (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK(version_number > 0),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    byte_size INTEGER NOT NULL CHECK(byte_size >= 0),
    storage_key TEXT NOT NULL,
    file_extension TEXT NOT NULL,
    extraction_status TEXT NOT NULL CHECK(extraction_status IN ('pending', 'complete', 'partial', 'failed')),
    extraction_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(source_id, version_number),
    UNIQUE(source_id, content_sha256),
    UNIQUE(source_id, id)
);
CREATE INDEX idx_source_versions_source ON source_versions(source_id, version_number DESC);
CREATE INDEX idx_source_versions_hash ON source_versions(content_sha256);
CREATE TRIGGER trg_source_version_identity_immutable
BEFORE UPDATE OF source_id, version_number, content_sha256, byte_size, storage_key, file_extension, created_at
ON source_versions
BEGIN
    SELECT RAISE(ABORT, 'source version identity is immutable');
END;

CREATE TABLE document_nodes (
    id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_versions(id) ON DELETE CASCADE,
    parent_node_id TEXT REFERENCES document_nodes(id) ON DELETE CASCADE,
    node_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    node_type TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    locator_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    origin TEXT NOT NULL CHECK(origin IN ('extracted', 'user_edited', 'model_derived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_version_id, node_key)
);
CREATE INDEX idx_document_nodes_parent ON document_nodes(parent_node_id, ordinal);
CREATE INDEX idx_document_nodes_version ON document_nodes(source_version_id, ordinal);

CREATE TABLE retrieval_chunks (
    fts_rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    source_version_id TEXT NOT NULL REFERENCES source_versions(id) ON DELETE CASCADE,
    document_node_id TEXT NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    token_estimate INTEGER NOT NULL CHECK(token_estimate >= 0),
    locator_json TEXT NOT NULL,
    UNIQUE(document_node_id, ordinal)
);
CREATE INDEX idx_retrieval_chunks_version ON retrieval_chunks(source_version_id, document_node_id, ordinal);
CREATE VIRTUAL TABLE retrieval_fts USING fts5(
    chunk_id UNINDEXED,
    source_version_id UNINDEXED,
    document_node_id UNINDEXED,
    title,
    content,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER trg_retrieval_chunks_delete AFTER DELETE ON retrieval_chunks
BEGIN
    DELETE FROM retrieval_fts WHERE rowid = old.fts_rowid;
END;

CREATE TABLE derived_artifacts (
    id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_versions(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    artifact_key TEXT NOT NULL,
    content_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN ('current', 'stale', 'superseded', 'failed')),
    generator TEXT NOT NULL,
    generator_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_version_id, artifact_type, artifact_key)
);
CREATE INDEX idx_derived_artifacts_status ON derived_artifacts(status, artifact_type);

CREATE TABLE artifact_dependencies (
    artifact_id TEXT NOT NULL REFERENCES derived_artifacts(id) ON DELETE CASCADE,
    dependency_type TEXT NOT NULL CHECK(dependency_type IN ('source_version', 'document_node', 'knowledge_edit')),
    dependency_id TEXT NOT NULL,
    dependency_sha256 TEXT NOT NULL CHECK(length(dependency_sha256) = 64),
    PRIMARY KEY(artifact_id, dependency_type, dependency_id)
);

CREATE TABLE knowledge_edits (
    id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_versions(id) ON DELETE CASCADE,
    document_node_id TEXT REFERENCES document_nodes(id) ON DELETE SET NULL,
    edit_type TEXT NOT NULL CHECK(edit_type IN ('correct_extraction', 'edit_summary', 'add_annotation', 'resolve_conflict')),
    before_json TEXT,
    after_json TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_knowledge_edits_version ON knowledge_edits(source_version_id, created_at);

CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(workspace_id, entity_type, normalized_name)
);

CREATE TABLE claims (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    subject_entity_id TEXT REFERENCES entities(id) ON DELETE SET NULL,
    predicate TEXT NOT NULL,
    object_text TEXT NOT NULL,
    normalized_object TEXT NOT NULL,
    valid_from TEXT,
    valid_until TEXT,
    confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    status TEXT NOT NULL CHECK(status IN ('candidate', 'accepted', 'disputed', 'superseded')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_claims_workspace_status ON claims(workspace_id, status, predicate);

CREATE TABLE claim_evidence (
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    document_node_id TEXT NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
    evidence_role TEXT NOT NULL CHECK(evidence_role IN ('supports', 'contradicts', 'qualifies')),
    PRIMARY KEY(claim_id, document_node_id, evidence_role)
);

CREATE TABLE entity_mentions (
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    document_node_id TEXT NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
    mention_text TEXT NOT NULL,
    start_offset INTEGER,
    end_offset INTEGER,
    PRIMARY KEY(entity_id, document_node_id, mention_text)
);
"""

def initialize_knowledge_db(path: str | Path) -> int:
    """Create or migrate the local knowledge schema; safe to call repeatedly."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=10)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        ).fetchone()[0]
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Knowledge database schema {current} is newer than this application supports ({SCHEMA_VERSION})"
            )
        if current < 1:
            from datetime import datetime, timezone
            pending = ""
            for line in _SCHEMA.splitlines(keepends=True):
                pending += line
                if sqlite3.complete_statement(pending):
                    if pending.strip():
                        connection.execute(pending)
                    pending = ""
            if pending.strip():
                raise RuntimeError("Knowledge schema contains an incomplete SQL statement")
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (1, datetime.now(timezone.utc).isoformat()),
            )
        connection.commit()
        return SCHEMA_VERSION
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

