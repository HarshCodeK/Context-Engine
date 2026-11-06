import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz
from fastapi.testclient import TestClient
from docx import Document
from openpyxl import Workbook
from PIL import Image
from pptx import Presentation

import context_studio.api as app_module
import context_studio.documents as documents_module
import context_studio.rules as rules_module
from app import app


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # Rate-limit state is process-local; isolate endpoint tests from each other.
        app_module._request_times.clear()
        self.database_dir = tempfile.TemporaryDirectory()
        self.database_patch = patch.object(rules_module, 'DATABASE_PATH', Path(self.database_dir.name) / 'context-rules.sqlite3')
        self.knowledge_patch = patch.object(app_module, 'DATABASE_PATH', Path(self.database_dir.name) / 'knowledge-data' / 'context-rules.sqlite3')
        self.database_patch.start()
        self.knowledge_patch.start()

    def tearDown(self):
        self.knowledge_patch.stop()
        self.database_patch.stop()
        self.database_dir.cleanup()

    def test_knowledge_ingest_versions_sources_and_allows_audited_edits(self):
        first = self.client.post(
            '/api/knowledge/ingest',
            files=[('files', ('release.txt', b'Approved launch date: 12 May.', 'text/plain'))],
            data={'processing_mode': 'native_only'},
        )
        self.assertEqual(first.status_code, 201, first.text)
        payload = first.json()
        self.assertEqual(payload['storage'], 'local_persistent')
        self.assertEqual(payload['results'][0]['status'], 'success')
        knowledge = payload['results'][0]['knowledge']
        self.assertEqual(knowledge['version_number'], 1)

        sources = self.client.get('/api/knowledge/sources').json()['sources']
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['source_version_id'], knowledge['source_version_id'])
        versions = self.client.get(f"/api/knowledge/sources/{knowledge['source_id']}/versions").json()['versions']
        self.assertEqual(len(versions), 1)
        search = self.client.get('/api/knowledge/search', params={'q': 'approved launch date'})
        self.assertEqual(search.status_code, 200, search.text)
        self.assertTrue(search.json()['results'])
        self.assertIn('12 May', search.json()['results'][0]['content'])
        nodes = self.client.get(f"/api/knowledge/versions/{knowledge['source_version_id']}/nodes").json()['nodes']
        self.assertEqual(len(nodes), 2)
        decision_node = next(node for node in nodes if '12 May' in node['content'])
        self.assertEqual(decision_node['parent_node_id'], nodes[0]['id'])
        digest_response = self.client.get(f"/api/knowledge/sources/{knowledge['source_id']}/digest")
        self.assertEqual(digest_response.status_code, 200, digest_response.text)
        self.assertIn('12 May', digest_response.json()['digest']['text'])

        edited = self.client.patch(f"/api/knowledge/nodes/{decision_node['id']}", json={
            'content': 'Approved launch date: 19 May.',
            'reason': 'Decision log correction',
        })
        self.assertEqual(edited.status_code, 200, edited.text)
        refreshed = self.client.get(f"/api/knowledge/versions/{knowledge['source_version_id']}/nodes").json()['nodes']
        updated_node = next(node for node in refreshed if node['id'] == decision_node['id'])
        self.assertIn('19 May', updated_node['content'])
        self.assertEqual(updated_node['origin'], 'user_edited')
        updated_digest = self.client.get(f"/api/knowledge/sources/{knowledge['source_id']}/digest").json()['digest']
        self.assertIn('19 May', updated_digest['text'])

        second = self.client.post(
            '/api/knowledge/ingest',
            files=[('files', ('release.txt', b'Approved launch date: 19 May.', 'text/plain'))],
            data={'processing_mode': 'native_only'},
        )
        self.assertEqual(second.status_code, 201, second.text)
        versions = self.client.get(f"/api/knowledge/sources/{knowledge['source_id']}/versions").json()['versions']
        self.assertEqual([item['version_number'] for item in versions], [2, 1])

    def test_knowledge_api_rejects_invalid_workspace_and_missing_records(self):
        invalid = self.client.get('/api/knowledge/sources?workspace_id=../outside')
        self.assertEqual(invalid.status_code, 422)
        missing = self.client.get('/api/knowledge/sources/missing/versions')
        self.assertEqual(missing.status_code, 404)
        missing_node = self.client.patch('/api/knowledge/nodes/missing', json={'content': 'x'})
        self.assertEqual(missing_node.status_code, 404)

    def test_digest_endpoint_backfills_a_missing_legacy_artifact(self):
        ingested = self.client.post(
            '/api/knowledge/ingest',
            files=[('files', ('legacy.txt', b'The approved launch date is 21 May 2027.', 'text/plain'))],
            data={'processing_mode': 'native_only'},
        )
        self.assertEqual(ingested.status_code, 201, ingested.text)
        source_id = ingested.json()['results'][0]['knowledge']['source_id']
        database_path = Path(self.database_dir.name) / 'knowledge-data' / 'knowledge.sqlite3'
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute(
                "DELETE FROM artifact_dependencies WHERE artifact_id IN ("
                "SELECT id FROM derived_artifacts WHERE artifact_type = 'document_digest')"
            )
            connection.execute("DELETE FROM derived_artifacts WHERE artifact_type = 'document_digest'")
            connection.commit()

        response = self.client.get(f'/api/knowledge/sources/{source_id}/digest')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('21 May 2027', response.json()['digest']['text'])

    def test_health(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_security_headers_and_private_api_cache_policy(self):
        page = self.client.get('/')
        api = self.client.get('/api/health')
        for response in (page, api):
            self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
            self.assertEqual(response.headers.get('Referrer-Policy'), 'no-referrer')
            self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')
            self.assertEqual(response.headers.get('Cross-Origin-Resource-Policy'), 'same-origin')
            self.assertEqual(response.headers.get('X-Permitted-Cross-Domain-Policies'), 'none')
            self.assertEqual(response.headers.get('Permissions-Policy'), 'camera=(), microphone=(), geolocation=()')
            self.assertIn("script-src 'self'", response.headers.get('Content-Security-Policy', ''))
            self.assertNotIn('unsafe-inline', response.headers.get('Content-Security-Policy', ''))
            self.assertNotIn('fonts.googleapis.com', response.headers.get('Content-Security-Policy', ''))
        self.assertEqual(api.headers.get('Cache-Control'), 'no-store')
        self.assertEqual(api.headers.get('Pragma'), 'no-cache')
        self.assertIsNone(page.headers.get('Cache-Control'))

    def test_host_header_rejects_untrusted_hosts(self):
        response = self.client.get('/api/health', headers={'Host': 'attacker.example'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid Host', response.json()['error'])
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')

    def test_state_changing_requests_reject_cross_origin_but_allow_same_origin(self):
        payload = {'title': 'Origin check', 'scope': 'organization', 'content': 'Origin validation test.'}
        blocked = self.client.post('/api/context-rules', json=payload, headers={'Origin': 'https://attacker.example'})
        self.assertEqual(blocked.status_code, 403)
        self.assertIn('Cross-origin', blocked.json()['error'])
        blocked_fetch = self.client.delete('/api/context-rules/nonexistent', headers={'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(blocked_fetch.status_code, 403)
        self.assertEqual(self.client.get('/api/context-rules').json()['rules'], [])

        allowed = self.client.post('/api/context-rules', json=payload, headers={'Origin': 'http://testserver'})
        self.assertEqual(allowed.status_code, 201, allowed.text)
        rule_id = allowed.json()['rule']['id']
        self.assertEqual(self.client.delete(f'/api/context-rules/{rule_id}', headers={'Origin': 'http://testserver'}).status_code, 200)

    def test_public_config_matches_server_limits(self):
        response = self.client.get('/api/config')
        self.assertEqual(response.status_code, 200)
        config = response.json()
        self.assertEqual(config['max_files'], app_module.MAX_FILES)
        self.assertEqual(config['max_file_bytes'], app_module.MAX_BYTES)
        self.assertEqual(config['max_batch_bytes'], app_module.MAX_BATCH_BYTES)
        self.assertEqual(config['max_session_files'], app_module.MAX_SESSION_FILES)
        self.assertEqual(config['max_session_errors'], app_module.MAX_SESSION_ERRORS)
        self.assertEqual(config['max_context_rules'], app_module.MAX_CONTEXT_RULES)
        self.assertIn('.pdf', config['supported_extensions'])

    def test_context_rules_persist_order_and_report_tag_overlaps(self):
        organization = self.client.post('/api/context-rules', json={
            'title': 'Protect private data', 'scope': 'organization', 'tags': ['security', 'data'],
            'content': 'Never send private documents to an external model without approval.', 'priority': 90,
        })
        project = self.client.post('/api/context-rules', json={
            'title': 'Context Studio conventions', 'scope': 'project', 'project_key': 'context-studio',
            'tags': ['security', 'markdown'], 'content': 'Keep source names and page references in every export.', 'priority': 60,
        })
        task = self.client.post('/api/context-rules', json={
            'title': 'Release checklist', 'scope': 'task', 'project_key': 'context-studio',
            'tags': ['release'], 'content': 'Check the changelog and rollback path.', 'priority': 80,
        })
        self.assertEqual((organization.status_code, project.status_code, task.status_code), (201, 201, 201))

        response = self.client.get('/api/context-rules')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([rule['scope'] for rule in payload['rules']], ['organization', 'project', 'task'])
        self.assertEqual(payload['precedence'], ['organization', 'project', 'task'])
        self.assertEqual(len(payload['potential_overlaps']), 1)
        self.assertEqual(payload['potential_overlaps'][0]['shared_tags'], ['security'])

        project_id = project.json()['rule']['id']
        updated = self.client.put(f'/api/context-rules/{project_id}', json={
            'title': 'Updated project conventions', 'scope': 'project', 'project_key': 'context-studio',
            'tags': ['markdown'], 'content': 'Keep source names and page references in every export.', 'priority': 75,
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['rule']['priority'], 75)
        self.assertEqual(self.client.delete(f"/api/context-rules/{task.json()['rule']['id']}").status_code, 200)
        self.assertEqual(self.client.delete('/api/context-rules/missing-rule').status_code, 404)

        final = self.client.get('/api/context-rules').json()
        self.assertEqual(len(final['rules']), 2)
        self.assertEqual(final['potential_overlaps'], [])

    def test_context_rule_validation_requires_project_key_and_safe_tags(self):
        missing_key = self.client.post('/api/context-rules', json={
            'title': 'Project rule', 'scope': 'project', 'content': 'Use tests.',
        })
        bad_tag = self.client.post('/api/context-rules', json={
            'title': 'Organization rule', 'scope': 'organization', 'tags': ['not a tag'], 'content': 'Use tests.',
        })
        organization_key = self.client.post('/api/context-rules', json={
            'title': 'Organization rule', 'scope': 'organization', 'project_key': 'project-a', 'content': 'Use tests.',
        })
        unsafe_project_key = self.client.post('/api/context-rules', json={
            'title': 'Unsafe project rule', 'scope': 'project', 'project_key': '../other-project', 'content': 'Use tests.',
        })
        empty_title = self.client.post('/api/context-rules', json={
            'title': ' ', 'scope': 'organization', 'content': 'Use tests.',
        })
        empty_content = self.client.post('/api/context-rules', json={
            'title': 'Empty content', 'scope': 'organization', 'content': '',
        })
        excessive_content = self.client.post('/api/context-rules', json={
            'title': 'Long content', 'scope': 'organization', 'content': 'x' * 10_001,
        })
        self.assertEqual(missing_key.status_code, 422)
        self.assertEqual(bad_tag.status_code, 422)
        self.assertEqual(organization_key.status_code, 422)
        self.assertEqual(unsafe_project_key.status_code, 422)
        self.assertEqual(empty_title.status_code, 422)
        self.assertEqual(empty_content.status_code, 422)
        self.assertEqual(excessive_content.status_code, 422)

    def test_context_rules_survive_client_recreation(self):
        created = self.client.post('/api/context-rules', json={
            'title': 'Persistent organization rule', 'scope': 'organization', 'content': 'Keep source evidence.',
        })
        self.assertEqual(created.status_code, 201)
        with TestClient(app) as restarted_client:
            response = restarted_client.get('/api/context-rules')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['rules'][0]['id'], created.json()['rule']['id'])
        self.assertEqual(response.json()['rules'][0]['content'], 'Keep source evidence.')

    def test_agent_context_api_supplies_only_matching_enabled_rules_with_provenance(self):
        organization = self.client.post('/api/context-rules', json={
            'title': 'Organization guardrails', 'scope': 'organization', 'tags': ['security'],
            'content': 'Never expose private source material.', 'priority': 90,
        }).json()['rule']
        project = self.client.post('/api/context-rules', json={
            'title': 'Project conventions', 'scope': 'project', 'project_key': 'context-studio',
            'content': 'Keep page references.', 'priority': 60,
        }).json()['rule']
        task = self.client.post('/api/context-rules', json={
            'title': 'Release checks', 'scope': 'task', 'project_key': 'context-studio',
            'tags': ['release'], 'content': 'Verify rollback.', 'priority': 80,
        }).json()['rule']
        disabled = self.client.post('/api/context-rules', json={
            'title': 'Disabled guidance', 'scope': 'organization', 'content': 'Do not include me.', 'enabled': False,
        }).json()['rule']

        response = self.client.get('/api/agent-context', params={
            'project_key': ' Context-Studio ', 'task_tags': 'release,docs,release',
        })
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload['schema_version'], '1.0')
        self.assertEqual(payload['context'], {'project_key': 'context-studio', 'task_tags': ['release', 'docs']})
        self.assertEqual(payload['precedence'], ['organization', 'project', 'task'])
        self.assertEqual(payload['rule_count'], 3)
        self.assertEqual([rule['id'] for rule in payload['rules']], [organization['id'], project['id'], task['id']])
        self.assertNotIn(disabled['id'], [rule['id'] for rule in payload['rules']])
        self.assertIn(organization['id'], payload['markdown'])
        self.assertIn('Verify rollback.', payload['markdown'])
        self.assertIn('explicitly user-authored guidance', payload['markdown'])
        self.assertIn('No uploaded documents are included', payload['markdown'])
        self.assertGreater(payload['estimated_tokens'], 0)
        self.assertIn('approximate only', payload['token_estimation'])

        organization_only = self.client.get('/api/agent-context', params={'project_key': 'another-project'})
        self.assertEqual(organization_only.status_code, 200)
        self.assertEqual([rule['id'] for rule in organization_only.json()['rules']], [organization['id']])

    def test_agent_context_api_validates_scope_selectors_and_returns_empty_context(self):
        self.assertEqual(self.client.get('/api/agent-context', params={'project_key': '../private'}).status_code, 422)
        self.assertEqual(self.client.get('/api/agent-context', params={'task_tags': 'valid,bad tag'}).status_code, 422)
        self.assertEqual(self.client.get('/api/agent-context', params={'task_tags': ','.join(f'tag{i}' for i in range(21))}).status_code, 422)
        self.assertEqual(self.client.get('/api/agent-context', params={'task_tags': 'x' * 660}).status_code, 422)
        empty = self.client.get('/api/agent-context')
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()['rules'], [])
        self.assertEqual(empty.json()['rule_count'], 0)
        self.assertIn('No enabled rules match', empty.json()['markdown'])

    def test_agent_context_api_enforces_the_context_output_limit(self):
        created = self.client.post('/api/context-rules', json={
            'title': 'Large organization rule', 'scope': 'organization', 'content': 'x' * 200,
        })
        self.assertEqual(created.status_code, 201)
        with patch.object(app_module, 'MAX_CONTEXT_PACK_CHARS', 100):
            response = self.client.get('/api/agent-context')
        self.assertEqual(response.status_code, 413)
        self.assertIn('context exceeds', response.json()['detail'])

    def test_context_rule_library_has_a_hard_record_limit(self):
        payload = {'title':'One rule', 'scope':'organization', 'content':'Keep source provenance.'}
        with patch.object(app_module, 'MAX_CONTEXT_RULES', 1):
            first = self.client.post('/api/context-rules', json=payload)
            second = self.client.post('/api/context-rules', json={**payload, 'title':'Second rule'})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertIn('library is full', second.json()['detail'])

    def test_identical_context_rules_are_rejected_on_create_and_update(self):
        payload = {
            'title': 'Repository conventions', 'scope': 'project', 'project_key': 'context-studio',
            'tags': ['engineering'], 'content': 'Keep changes covered by tests.',
        }
        first = self.client.post('/api/context-rules', json=payload)
        duplicate = self.client.post('/api/context-rules', json={**payload, 'title': ' repository conventions '})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn('identical rule already exists', duplicate.json()['detail'])

        second = self.client.post('/api/context-rules', json={**payload, 'title': 'Testing conventions'})
        self.assertEqual(second.status_code, 201)
        collision = self.client.put(f"/api/context-rules/{second.json()['rule']['id']}", json=payload)
        self.assertEqual(collision.status_code, 409)
        saved = self.client.get('/api/context-rules').json()['rules']
        self.assertEqual(len(saved), 2)
        self.assertEqual(next(rule for rule in saved if rule['id'] == second.json()['rule']['id'])['title'], 'Testing conventions')

    def test_concurrent_rule_creates_cannot_exceed_library_capacity(self):
        payload = {'scope': 'organization', 'content': 'Keep source provenance.'}
        with patch.object(app_module, 'MAX_CONTEXT_RULES', 1):
            def create(index):
                with TestClient(app) as client:
                    return client.post('/api/context-rules', json={**payload, 'title': f'Concurrent rule {index}'}).status_code

            with ThreadPoolExecutor(max_workers=8) as pool:
                statuses = list(pool.map(create, range(8)))
        self.assertEqual(statuses.count(201), 1)
        self.assertEqual(statuses.count(409), 7)
        self.assertEqual(len(self.client.get('/api/context-rules').json()['rules']), 1)

    def test_extraction_reports_route_compute_time_and_context_estimate(self):
        content = b'Context is useful when it has evidence.'
        response = self.client.post('/api/extract', files=[
            ('files', ('notes.txt', content, 'text/plain')),
        ])
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['results'][0]
        self.assertEqual(result['processing']['route'], 'text_decode')
        self.assertEqual(result['processing']['mode'], 'local_deterministic')
        self.assertEqual(result['processing']['external_model_calls'], 0)
        self.assertGreaterEqual(result['processing']['duration_ms'], 0)
        self.assertEqual(result['context']['input_bytes'], len(content))
        self.assertEqual(result['context']['markdown_bytes'], len(result['markdown'].encode('utf-8')))
        self.assertEqual(result['context']['estimated_tokens'], (len(result['markdown']) + 3) // 4)
        self.assertIn('approximate only', result['context']['token_estimation'])
        self.assertEqual(result['processing']['decision']['selected_route'], 'text_decode')
        self.assertIn('already text', result['processing']['decision']['reason'])
        self.assertEqual(result['processing']['decision']['policy'], 'auto')
        self.assertEqual(result['processing']['external_model_calls'], 0)
        self.assertEqual(result['evidence']['schema_version'], '1.0')
        self.assertEqual(result['evidence']['source_id'], result['evidence']['source_sha256'])
        self.assertEqual(result['evidence']['blocks'][0]['locator'], {'type': 'text_file'})
        evidence_range = result['evidence']['blocks'][0]['markdown_range']
        self.assertEqual(result['markdown'][evidence_range['start']:evidence_range['end']], result['markdown'])

    def test_pdf_processing_policy_and_decision_trace_explain_ocr_choice(self):
        document = fitz.open()
        document.new_page()
        pdf = io.BytesIO()
        document.save(pdf)
        document.close()
        upload = ('files', ('scanned.pdf', pdf.getvalue(), 'application/pdf'))
        with patch.object(documents_module, '_ocr_available', return_value=False):
            automatic = self.client.post('/api/extract', files=[upload], data={'processing_mode': 'auto'})
            native = self.client.post('/api/extract', files=[upload], data={'processing_mode': 'native_only'})
        self.assertEqual((automatic.status_code, native.status_code), (200, 200))
        automatic_result = automatic.json()['results'][0]
        native_result = native.json()['results'][0]
        self.assertEqual(automatic_result['processing']['decision']['policy'], 'auto')
        self.assertIn('not configured', automatic_result['processing']['decision']['reason'])
        self.assertEqual(automatic_result['processing']['decision']['alternatives'][0]['status'], 'unavailable')
        self.assertEqual(native_result['processing']['decision']['policy'], 'native_only')
        self.assertIn('OCR is skipped on pages without selectable text', native_result['processing']['decision']['reason'])
        self.assertEqual(native_result['processing']['decision']['alternatives'][0]['status'], 'skipped_by_policy')
        self.assertTrue(any('Native text-only mode skipped OCR' in warning for warning in native_result['warnings']))
        self.assertTrue(any('native-text-only mode left them unreadable' in warning for warning in native_result['warnings']))

    def test_automatic_policy_uses_local_ocr_only_for_scanned_pdf_pages(self):
        document = fitz.open()
        document.new_page()
        pdf = io.BytesIO()
        document.save(pdf)
        document.close()
        upload = ('files', ('scanned.pdf', pdf.getvalue(), 'application/pdf'))
        with patch.object(documents_module, '_ocr_available', return_value=True), patch.object(documents_module, 'ocr_image', return_value='recognized scan text') as ocr:
            automatic = self.client.post('/api/extract', files=[upload], data={'processing_mode': 'auto'})
            native = self.client.post('/api/extract', files=[upload], data={'processing_mode': 'native_only'})
        self.assertEqual((automatic.status_code, native.status_code), (200, 200))
        automatic_result = automatic.json()['results'][0]
        native_result = native.json()['results'][0]
        self.assertIn('recognized scan text', automatic_result['markdown'])
        self.assertEqual(automatic_result['processing']['route'], 'pdf_text_ocr')
        self.assertIn('recovered 1 page', automatic_result['processing']['decision']['reason'])
        self.assertNotIn('recognized scan text', native_result['markdown'])
        self.assertEqual(native_result['processing']['route'], 'pdf_text')
        self.assertEqual(ocr.call_count, 1)

    def test_automatic_policy_uses_image_ocr_and_native_only_skips_it(self):
        image = Image.new('RGB', (16, 16), 'white')
        data = io.BytesIO()
        image.save(data, format='PNG')
        upload = ('files', ('screenshot.png', data.getvalue(), 'image/png'))
        with patch.object(documents_module, '_ocr_available', return_value=True), patch.object(documents_module, 'ocr_image', return_value='image text found') as ocr:
            automatic = self.client.post('/api/extract', files=[upload], data={'processing_mode': 'auto'})
            native = self.client.post('/api/extract', files=[upload], data={'processing_mode': 'native_only'})
        self.assertEqual((automatic.status_code, native.status_code), (200, 200))
        automatic_result = automatic.json()['results'][0]
        native_result = native.json()['results'][0]
        self.assertIn('image text found', automatic_result['markdown'])
        self.assertEqual(automatic_result['processing']['route'], 'local_ocr')
        self.assertIn('Local OCR was selected', automatic_result['processing']['decision']['reason'])
        self.assertNotIn('image text found', native_result['markdown'])
        self.assertEqual(native_result['processing']['route'], 'image_metadata')
        self.assertIn('intentionally skipped', native_result['processing']['decision']['reason'])
        self.assertEqual(ocr.call_count, 1)

    def test_processing_policy_rejects_unknown_values(self):
        response = self.client.post('/api/extract', files=[
            ('files', ('notes.txt', b'Policy validation', 'text/plain')),
        ], data={'processing_mode': 'send_to_cloud'})
        self.assertEqual(response.status_code, 422)

    def test_mixed_batch_keeps_success_when_one_file_is_invalid(self):
        response = self.client.post('/api/extract', files=[
            ('files', ('notes.txt', b'Useful notes', 'text/plain')),
            ('files', ('payload.exe', b'nope', 'application/octet-stream')),
        ])
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['processed'], 2)
        self.assertEqual(payload['results'][0]['status'], 'success')
        self.assertIn('Useful notes', payload['results'][0]['markdown'])
        self.assertEqual(payload['results'][1]['status'], 'error')

    def test_too_many_files_is_rejected_before_processing(self):
        response = self.client.post('/api/extract', files=[
            ('files', (f'notes-{i}.txt', b'x', 'text/plain')) for i in range(13)
        ])
        self.assertEqual(response.status_code, 400)
        self.assertIn('up to 12 files', response.json()['error'])

    def test_single_file_size_limit_is_enforced_by_endpoint(self):
        response = self.client.post('/api/extract', files=[
            ('files', ('large.txt', b'x' * (20 * 1024 * 1024 + 1), 'text/plain'))
        ])
        self.assertEqual(response.status_code, 200)
        result = response.json()['results'][0]
        self.assertEqual(result['status'], 'error')
        self.assertIn('20 MB limit', result['error'])

    def test_malformed_json_is_reported_per_file(self):
        response = self.client.post('/api/extract', files=[('files', ('bad.json', b'{', 'application/json'))])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['status'], 'error')

    def test_csv_truncates_at_configured_row_limit_with_warning(self):
        with patch.object(documents_module, 'MAX_TABLE_ROWS', 3):
            response = self.client.post('/api/extract', files=[
                ('files', ('rows.csv', b'Name\nAda\nGrace\nLinus', 'text/csv')),
            ])
        self.assertEqual(response.status_code, 200)
        result = response.json()['results'][0]
        self.assertEqual(result['status'], 'success')
        self.assertIn('Ada', result['markdown'])
        self.assertIn('Grace', result['markdown'])
        self.assertNotIn('Linus', result['markdown'])
        self.assertTrue(any('CSV output truncated' in warning for warning in result['warnings']))

    def test_xlsx_bounds_rows_and_columns(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['a1', 'b1', 'c1'])
        sheet.append(['a2', 'b2', 'c2'])
        sheet.append(['a3', 'b3', 'c3'])
        data = io.BytesIO()
        workbook.save(data)
        with patch.object(documents_module, 'MAX_TABLE_ROWS', 2), patch.object(documents_module, 'MAX_TABLE_COLUMNS', 2):
            response = self.client.post('/api/extract', files=[
                ('files', ('wide.xlsx', data.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')),
            ])
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['results'][0]
        self.assertEqual(result['status'], 'success')
        self.assertIn('b2', result['markdown'])
        self.assertNotIn('c1', result['markdown'])
        self.assertNotIn('a3', result['markdown'])
        self.assertTrue(any('row range capped' in warning for warning in result['warnings']))
        self.assertTrue(any('column range capped' in warning for warning in result['warnings']))

    def test_docx_bounds_paragraphs_and_table_cells(self):
        document = Document()
        document.add_paragraph('first paragraph')
        document.add_paragraph('second paragraph')
        document.add_paragraph('third paragraph must be omitted')
        table = document.add_table(rows=2, cols=2)
        table.cell(0, 0).text = 'table-a'
        table.cell(0, 1).text = 'table-b'
        table.cell(1, 0).text = 'table-c'
        table.cell(1, 1).text = 'table-d'
        data = io.BytesIO()
        document.save(data)
        with patch.object(documents_module, 'MAX_DOCX_PARAGRAPHS', 2), patch.object(documents_module, 'MAX_TABLE_CELLS', 2):
            response = self.client.post('/api/extract', files=[
                ('files', ('bounded.docx', data.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')),
            ])
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['results'][0]
        self.assertEqual(result['status'], 'success')
        self.assertIn('first paragraph', result['markdown'])
        self.assertIn('second paragraph', result['markdown'])
        self.assertNotIn('third paragraph', result['markdown'])
        self.assertIn('table-a', result['markdown'])
        self.assertNotIn('table-c', result['markdown'])
        self.assertTrue(any('paragraphs truncated' in warning for warning in result['warnings']))
        self.assertTrue(any('table extraction reached' in warning for warning in result['warnings']))

    def test_pptx_bounds_slides_and_shapes(self):
        deck = Presentation()
        first = deck.slides.add_slide(deck.slide_layouts[6])
        first.shapes.add_textbox(0, 0, 100, 100).text = 'first slide text'
        second = deck.slides.add_slide(deck.slide_layouts[6])
        second.shapes.add_textbox(0, 0, 100, 100).text = 'second slide text'
        data = io.BytesIO()
        deck.save(data)
        with patch.object(documents_module, 'MAX_PPTX_SLIDES', 1):
            response = self.client.post('/api/extract', files=[
                ('files', ('bounded.pptx', data.getvalue(), 'application/vnd.openxmlformats-officedocument.presentationml.presentation')),
            ])
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['results'][0]
        self.assertIn('first slide text', result['markdown'])
        self.assertNotIn('second slide text', result['markdown'])
        self.assertTrue(any('truncated at 1 slides' in warning for warning in result['warnings']))

        shape_deck = Presentation()
        slide = shape_deck.slides.add_slide(shape_deck.slide_layouts[6])
        slide.shapes.add_textbox(0, 0, 100, 100).text = 'keep this shape'
        slide.shapes.add_textbox(0, 0, 100, 100).text = 'drop this shape'
        shape_data = io.BytesIO()
        shape_deck.save(shape_data)
        with patch.object(documents_module, 'MAX_PPTX_SHAPES', 1):
            shape_response = self.client.post('/api/extract', files=[
                ('files', ('shape-limit.pptx', shape_data.getvalue(), 'application/vnd.openxmlformats-officedocument.presentationml.presentation')),
            ])
        shape_result = shape_response.json()['results'][0]
        self.assertIn('keep this shape', shape_result['markdown'])
        self.assertNotIn('drop this shape', shape_result['markdown'])
        self.assertTrue(any('shape extraction truncated' in warning for warning in shape_result['warnings']))

        table_deck = Presentation()
        table_slide = table_deck.slides.add_slide(table_deck.slide_layouts[6])
        table = table_slide.shapes.add_table(2, 2, 0, 0, 100, 100).table
        table.cell(0, 0).text = 'table-a'
        table.cell(0, 1).text = 'table-b'
        table.cell(1, 0).text = 'table-c'
        table.cell(1, 1).text = 'table-d'
        table_data = io.BytesIO()
        table_deck.save(table_data)
        with patch.object(documents_module, 'MAX_TABLE_CELLS', 2):
            table_response = self.client.post('/api/extract', files=[
                ('files', ('table-limit.pptx', table_data.getvalue(), 'application/vnd.openxmlformats-officedocument.presentationml.presentation')),
            ])
        table_result = table_response.json()['results'][0]
        self.assertIn('table-a', table_result['markdown'])
        self.assertNotIn('table-c', table_result['markdown'])
        self.assertTrue(any('Presentation table extraction reached' in warning for warning in table_result['warnings']))

    def test_extracted_output_limit_returns_actionable_error(self):
        with patch.object(documents_module, 'MAX_EXTRACTED_CHARS', 10):
            response = self.client.post('/api/extract', files=[
                ('files', ('large-output.txt', b'0123456789abcdefghij', 'text/plain')),
            ])
        self.assertEqual(response.status_code, 200)
        result = response.json()['results'][0]
        self.assertEqual(result['status'], 'error')
        self.assertIn('character safety limit', result['error'])

    def test_supported_formats_upload_through_api(self):
        pdf = io.BytesIO()
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), 'PDF smoke text')
        document.save(pdf)
        document.close()

        word = Document()
        word.add_paragraph('DOCX smoke text')
        docx = io.BytesIO()
        word.save(docx)

        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[5])
        slide.shapes.title.text = 'PPTX smoke text'
        pptx = io.BytesIO()
        deck.save(pptx)

        workbook = Workbook()
        workbook.active.append(['XLSX smoke text'])
        xlsx = io.BytesIO()
        workbook.save(xlsx)

        uploads = [
            ('files', ('notes.txt', b'TXT smoke text', 'text/plain')),
            ('files', ('rows.csv', b'Name,Role\nAda,Engineer', 'text/csv')),
            ('files', ('data.json', b'{"message":"JSON smoke text"}', 'application/json')),
            ('files', ('brief.pdf', pdf.getvalue(), 'application/pdf')),
            ('files', ('brief.docx', docx.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')),
            ('files', ('brief.pptx', pptx.getvalue(), 'application/vnd.openxmlformats-officedocument.presentationml.presentation')),
            ('files', ('brief.xlsx', xlsx.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')),
        ]
        response = self.client.post('/api/extract', files=uploads)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload['processed'], 7)
        self.assertTrue(all(item['status'] == 'success' for item in payload['results']), payload)
        for result, expected in zip(payload['results'], [
            'TXT smoke text', 'Ada', 'JSON smoke text', 'PDF smoke text',
            'DOCX smoke text', 'PPTX smoke text', 'XLSX smoke text',
        ]):
            self.assertIn(expected, result['markdown'])

    def test_empty_upload_and_corrupt_pdf_are_reported_per_file(self):
        response = self.client.post('/api/extract', files=[
            ('files', ('empty.txt', b'', 'text/plain')),
            ('files', ('broken.pdf', b'not a pdf', 'application/pdf')),
        ])
        self.assertEqual(response.status_code, 200, response.text)
        results = response.json()['results']
        self.assertEqual([item['status'] for item in results], ['error', 'error'])
        self.assertIn('empty', results[0]['error'].lower())
        self.assertIn('signature', results[1]['error'].lower())

    def test_aggregate_batch_limit_stops_processing_remaining_files(self):
        with patch.object(app_module, 'MAX_BATCH_BYTES', 5):
            response = self.client.post('/api/extract', files=[
                ('files', ('one.txt', b'123', 'text/plain')),
                ('files', ('two.txt', b'456', 'text/plain')),
                ('files', ('three.txt', b'789', 'text/plain')),
            ])
        self.assertEqual(response.status_code, 200, response.text)
        results = response.json()['results']
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]['status'], 'success')
        self.assertEqual(results[1]['status'], 'error')
        self.assertIn('batch exceeds', results[1]['error'].lower())
        self.assertIn('not processed', results[2]['error'].lower())

    def test_chunked_request_without_content_length_is_bounded(self):
        boundary = 'context-studio-boundary'
        body = (
            f'--{boundary}\r\n'
            'Content-Disposition: form-data; name="files"; filename="large.txt"\r\n'
            'Content-Type: text/plain\r\n\r\n'
        ).encode() + b'x' * (2 * 1024 * 1024 + 100) + f'\r\n--{boundary}--\r\n'.encode()
        with patch.object(app_module, 'MAX_BATCH_BYTES', 1):
            response = self.client.post(
                '/api/extract',
                content=iter((body[:1024 * 1024], body[1024 * 1024:])),
                headers={
                    'Content-Type': f'multipart/form-data; boundary={boundary}',
                    'Transfer-Encoding': 'chunked',
                },
            )
        self.assertEqual(response.status_code, 413, response.text)
        self.assertIn('batch limit', response.json()['error'].lower())
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')


if __name__ == '__main__':
    unittest.main()
