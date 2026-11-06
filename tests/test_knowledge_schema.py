import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from context_studio.knowledge_schema import SCHEMA_VERSION, initialize_knowledge_db


class KnowledgeSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'knowledge.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def test_initializes_versioned_schema_idempotently(self):
        self.assertEqual(initialize_knowledge_db(self.database), SCHEMA_VERSION)
        self.assertEqual(initialize_knowledge_db(self.database), SCHEMA_VERSION)
        with closing(sqlite3.connect(self.database)) as connection:
            version = connection.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertTrue({'workspaces', 'sources', 'source_versions', 'document_nodes', 'derived_artifacts', 'artifact_dependencies', 'knowledge_edits', 'entities', 'claims', 'claim_evidence', 'entity_mentions'} <= tables)

    def test_schema_enforces_foreign_keys_and_version_uniqueness(self):
        initialize_knowledge_db(self.database)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute('PRAGMA foreign_keys = ON')
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO sources(id, workspace_id, display_name, created_at, updated_at) VALUES ('s1', 'missing', 'x.txt', 'now', 'now')")

    def test_rejects_database_from_newer_application_version(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            connection.execute("INSERT INTO schema_migrations VALUES (999, 'future')")
            connection.commit()
        with self.assertRaisesRegex(RuntimeError, 'newer than this application supports'):
            initialize_knowledge_db(self.database)


if __name__ == '__main__':
    unittest.main()
