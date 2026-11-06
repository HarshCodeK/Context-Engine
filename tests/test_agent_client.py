import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from examples.agent_context_client import build_url, fetch_context, main


class AgentContextClientTests(unittest.TestCase):
    def test_build_url_encodes_project_and_repeated_task_tags(self):
        url = build_url('http://127.0.0.1:8000/', 'context-studio', ['release', 'security'])
        parsed = urlsplit(url)
        self.assertEqual(parsed.path, '/api/agent-context')
        self.assertEqual(parse_qs(parsed.query), {
            'project_key': ['context-studio'], 'task_tags': ['release,security'],
        })

    def test_client_refuses_non_loopback_and_non_root_base_urls(self):
        for base_url in ('https://127.0.0.1:8000', 'http://example.com', 'http://127.0.0.1:8000/private'):
            with self.subTest(base_url=base_url), self.assertRaises(ValueError):
                build_url(base_url, None, [])

    def test_fetch_context_checks_schema_and_returns_payload(self):
        expected = {'schema_version': '1.0', 'markdown': '# Agent context', 'rules': [], 'rule_count': 0}
        response = io.BytesIO(json.dumps(expected).encode())
        with patch('examples.agent_context_client.urlopen', return_value=response) as open_url:
            payload = fetch_context('http://localhost:8000', 'context-studio', ['release'])
        self.assertEqual(payload, expected)
        self.assertEqual(open_url.call_args.kwargs['timeout'], 5)
        self.assertEqual(open_url.call_args.args[0].get_header('Accept'), 'application/json')

    def test_cli_prints_markdown_for_agent_consumption(self):
        payload = {'schema_version': '1.0', 'markdown': '# Scoped rules\n\nVerify release.'}
        output = io.StringIO()
        with patch('examples.agent_context_client.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())), redirect_stdout(output):
            status = main(['--project-key', 'context-studio', '--task-tag', 'release'])
        self.assertEqual(status, 0)
        self.assertIn('Verify release.', output.getvalue())

    def test_cli_reports_unsupported_response_without_printing_context(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch('examples.agent_context_client.urlopen', return_value=io.BytesIO(b'{"schema_version":"2.0"}')), redirect_stdout(output), redirect_stderr(errors):
            status = main([])
        self.assertEqual(status, 1)
        self.assertEqual(output.getvalue(), '')
        self.assertIn('unsupported or malformed response', errors.getvalue())


if __name__ == '__main__':
    unittest.main()
