import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from context_studio.documents import extract_document
from context_studio.knowledge_store import KnowledgeStore


class KnowledgeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = KnowledgeStore(Path(self.temp.name) / 'data')

    def tearDown(self):
        self.temp.cleanup()

    def _extract(self, filename, content):
        return extract_document(filename, content, processing_mode='native_only')

    def test_ingest_persists_original_bytes_version_and_provenance_nodes(self):
        content = b'# Brief\n\nThe launch date is 12 May.'
        result = self.store.ingest('brief.md', content, self._extract('brief.md', content))
        self.assertEqual(result['version_number'], 1)
        self.assertEqual(result['content_sha256'], hashlib.sha256(content).hexdigest())
        self.assertTrue(result['created_new_version'])
        self.assertEqual(self.store.read_source_bytes(result['source_version_id']), content)
        nodes = self.store.list_nodes(result['source_version_id'])
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0]['content'], '# Brief')
        self.assertEqual(nodes[1]['content'], 'The launch date is 12 May.')
        self.assertEqual(nodes[0]['node_type'], 'section')
        self.assertIsNone(nodes[0]['parent_node_id'])
        self.assertEqual(nodes[1]['node_type'], 'paragraph')
        self.assertEqual(nodes[1]['parent_node_id'], nodes[0]['id'])
        self.assertEqual(nodes[0]['locator']['type'], 'text_file')
        self.assertEqual(nodes[0]['locator']['section'], 'Brief')
        self.assertEqual(nodes[0]['origin'], 'extracted')
        for node in nodes:
            self.assertEqual(node['content_sha256'], hashlib.sha256(node['content'].encode()).hexdigest())

    def test_reuploading_identical_bytes_does_not_create_a_duplicate_version(self):
        content = b'Identical source.'
        extraction = self._extract('notes.txt', content)
        first = self.store.ingest('notes.txt', content, extraction)
        with closing(sqlite3.connect(self.store.database_path)) as connection:
            connection.execute(
                "DELETE FROM artifact_dependencies WHERE artifact_id IN ("
                "SELECT id FROM derived_artifacts WHERE artifact_type = 'document_digest')"
            )
            connection.execute("DELETE FROM derived_artifacts WHERE artifact_type = 'document_digest'")
            connection.commit()
        second = self.store.ingest('notes.txt', content, extraction)
        self.assertEqual(first['source_id'], second['source_id'])
        self.assertEqual(first['source_version_id'], second['source_version_id'])
        self.assertTrue(first['created_new_version'])
        self.assertFalse(second['created_new_version'])
        self.assertEqual(len(self.store.list_sources()), 1)
        self.assertIsNotNone(self.store.get_digest(first['source_id']))

    def test_changed_bytes_create_new_version_and_mark_old_artifacts_stale(self):
        first_bytes = b'Launch date: 12 May.'
        second_bytes = b'Launch date: 19 May.'
        first = self.store.ingest('plan.txt', first_bytes, self._extract('plan.txt', first_bytes))
        second = self.store.ingest('plan.txt', second_bytes, self._extract('plan.txt', second_bytes))
        self.assertEqual(second['source_id'], first['source_id'])
        self.assertEqual(second['version_number'], 2)
        self.assertNotEqual(second['source_version_id'], first['source_version_id'])
        with closing(sqlite3.connect(self.store.database_path)) as connection:
            states = connection.execute('SELECT status FROM derived_artifacts ORDER BY created_at').fetchall()
        self.assertEqual([row[0] for row in states], ['superseded'] * 3 + ['current'] * 3)
        current = self.store.list_sources()[0]
        self.assertEqual(current['source_version_id'], second['source_version_id'])

    def test_user_edit_is_audited_and_invalidates_dependent_artifacts(self):
        content = b'Approved launch date: 12 May.'
        ingested = self.store.ingest('decision.txt', content, self._extract('decision.txt', content))
        node = next(item for item in self.store.list_nodes(ingested['source_version_id']) if '12 May' in item['content'])
        artifact_id = 'summary-1'
        with closing(sqlite3.connect(self.store.database_path)) as connection:
            connection.execute('PRAGMA foreign_keys = ON')
            connection.execute("""INSERT INTO derived_artifacts(
                id, source_version_id, artifact_type, artifact_key, content_json,
                content_sha256, status, generator, generator_version, created_at, updated_at
            ) VALUES (?, ?, 'summary', 'document', '{}', ?, 'current', 'test', '1', 'now', 'now')""",
                (artifact_id, ingested['source_version_id'], hashlib.sha256(b'{}').hexdigest()))
            connection.execute("INSERT INTO artifact_dependencies VALUES (?, 'document_node', ?, ?)",
                (artifact_id, node['id'], node['content_sha256']))
            connection.commit()
        edited = self.store.edit_node(node['id'], 'Approved launch date: 19 May.', 'Corrected after approval review')
        updated = next(item for item in self.store.list_nodes(ingested['source_version_id']) if item['id'] == node['id'])
        self.assertEqual(updated['origin'], 'user_edited')
        self.assertIn('19 May', updated['content'])
        with closing(sqlite3.connect(self.store.database_path)) as connection:
            edit = connection.execute('SELECT before_json, after_json, reason FROM knowledge_edits WHERE id = ?', (edited['edit_id'],)).fetchone()
            status = connection.execute('SELECT status FROM derived_artifacts WHERE id = ?', (artifact_id,)).fetchone()[0]
        self.assertIn('12 May', json.loads(edit[0])['content'])
        self.assertIn('19 May', json.loads(edit[1])['content'])
        self.assertEqual(edit[2], 'Corrected after approval review')
        self.assertEqual(status, 'stale')
        digest = self.store.get_digest(ingested['source_id'])
        self.assertIsNotNone(digest)
        self.assertIn('19 May', digest['text'])
        self.assertEqual(self.store.read_source_bytes(ingested['source_version_id']), content)

    def test_ingestion_builds_searchable_chunks_with_source_provenance(self):
        content = ("Project launch decision\n\n" +
                   "The approved launch date is 12 May 2027.\n\n" +
                   "The operations team owns the final readiness review.").encode()
        result = self.store.ingest('launch-plan.txt', content, self._extract('launch-plan.txt', content))
        self.assertGreaterEqual(result['chunk_count'], 1)
        matches = self.store.search('approved launch date', limit=5)
        self.assertGreaterEqual(len(matches), 1)
        self.assertEqual(matches[0]['source_id'], result['source_id'])
        self.assertEqual(matches[0]['display_name'], 'launch-plan.txt')
        self.assertIn('12 May 2027', matches[0]['content'])
        self.assertEqual(matches[0]['locator']['type'], 'text_file')
        self.assertTrue(matches[0]['locator']['section'])

    def test_reactivating_a_previous_version_restores_its_index(self):
        old_bytes = b'The approved date is 12 May.'
        new_bytes = b'The approved date is 19 May.'
        old = self.store.ingest('timeline.txt', old_bytes, self._extract('timeline.txt', old_bytes))
        self.store.ingest('timeline.txt', new_bytes, self._extract('timeline.txt', new_bytes))
        restored = self.store.ingest('timeline.txt', old_bytes, self._extract('timeline.txt', old_bytes))
        self.assertFalse(restored['created_new_version'])
        self.assertEqual(restored['source_version_id'], old['source_version_id'])
        self.assertGreaterEqual(restored['chunk_count'], 1)
        matches = self.store.search('approved date')
        self.assertTrue(any('12 May' in item['content'] for item in matches))
        self.assertFalse(any('19 May' in item['content'] for item in matches))

    def test_search_excludes_superseded_versions(self):
        first_bytes = b'The project launch date is 12 May.'
        second_bytes = b'The project launch date is 19 May.'
        first = self.store.ingest('date.txt', first_bytes, self._extract('date.txt', first_bytes))
        self.store.ingest('date.txt', second_bytes, self._extract('date.txt', second_bytes))
        matches = self.store.search('project launch date')
        self.assertTrue(matches)
        self.assertTrue(all(item['source_version_id'] != first['source_version_id'] for item in matches))
        self.assertTrue(any('19 May' in item['content'] for item in matches))

    def test_edit_rebuilds_lexical_index_so_old_text_is_not_searchable(self):
        content = b'The approved date is 12 May.'
        ingested = self.store.ingest('decision.txt', content, self._extract('decision.txt', content))
        node = next(item for item in self.store.list_nodes(ingested['source_version_id']) if '12 May' in item['content'])
        self.store.edit_node(node['id'], 'The approved date is 19 May.')
        old_matches = self.store.search('12 May')
        new_matches = self.store.search('19 May')
        self.assertEqual(old_matches, [])
        self.assertTrue(new_matches)

    def test_rejects_extraction_from_different_source_bytes(self):
        extraction = self._extract('notes.txt', b'Original source.')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.store.ingest('notes.txt', b'Different bytes.', extraction)

    def test_detects_corrupted_content_addressed_blob(self):
        content = b'Integrity matters.'
        result = self.store.ingest('integrity.txt', content, self._extract('integrity.txt', content))
        path = self.store.blob_dir / result['storage_key']
        path.write_bytes(b'corrupted')
        with self.assertRaisesRegex(RuntimeError, 'integrity check'):
            self.store.read_source_bytes(result['source_version_id'])


if __name__ == '__main__':
    unittest.main()
