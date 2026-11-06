import io
import json
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from examples.mcp_server import GET_CONTEXT_TOOL, handle_message, main, run_stdio


MODERN_META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "Context Studio tests", "version": "1.0"},
}


def modern_request(request_id, method, params=None):
    metadata = json.loads(json.dumps(MODERN_META))
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": {**(params or {}), "_meta": metadata}}


class MCPServerTests(unittest.TestCase):
    def test_discover_advertises_current_protocol_and_tool_capability(self):
        response = handle_message(modern_request(1, "server/discover"))
        result = response["result"]
        self.assertEqual(result["supportedVersions"], ["2026-07-28"])
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["capabilities"], {"tools": {}})
        self.assertEqual(result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "context-studio")
        self.assertEqual(result["cacheScope"], "public")

    def test_discover_rejects_unsupported_version_with_supported_list(self):
        request = modern_request(2, "server/discover")
        request["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "2099-01-01"
        response = handle_message(request)
        self.assertEqual(response["error"]["code"], -32022)
        self.assertEqual(response["error"]["data"]["supported"], ["2026-07-28"])

    def test_modern_requests_require_protocol_and_capability_metadata(self):
        response = handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
        self.assertEqual(response["error"]["code"], -32602)

    def test_tools_list_exposes_one_read_only_tool_with_cache_hints(self):
        response = handle_message(modern_request(4, "tools/list"))
        result = response["result"]
        self.assertEqual(result["tools"], [GET_CONTEXT_TOOL])
        self.assertTrue(GET_CONTEXT_TOOL["annotations"]["readOnlyHint"])
        self.assertFalse(GET_CONTEXT_TOOL["annotations"]["destructiveHint"])
        self.assertEqual(result["ttlMs"], 300_000)
        self.assertEqual(result["resultType"], "complete")

    def test_modern_tool_call_returns_markdown_and_structured_provenance(self):
        payload = {
            "schema_version": "1.0", "markdown": "# Context\n\nVerify release.",
            "rules": [{"id": "rule-1", "scope": "project", "priority": 80}], "rule_count": 1,
        }
        params = {"name": "get_context", "arguments": {"project_key": "context-studio", "task_tags": ["release", "docs", "release"]}}
        with patch("examples.mcp_server.fetch_context", return_value=payload) as fetch:
            response = handle_message(modern_request(5, "tools/call", params))
        fetch.assert_called_once_with("http://127.0.0.1:8000", "context-studio", ["release", "docs"])
        self.assertEqual(response["result"]["content"][0]["text"], payload["markdown"])
        self.assertEqual(response["result"]["structuredContent"], payload)
        self.assertEqual(response["result"]["resultType"], "complete")
        self.assertFalse(response["result"]["isError"])

    def test_invalid_arguments_are_rejected_before_api_call(self):
        with patch("examples.mcp_server.fetch_context") as fetch:
            response = handle_message(modern_request(6, "tools/call", {"name": "get_context", "arguments": {"project_key": "../private"}}))
        self.assertTrue(response["result"]["isError"])
        self.assertIn("project_key", response["result"]["content"][0]["text"])
        fetch.assert_not_called()

    def test_tool_failure_is_reported_as_mcp_tool_error(self):
        with patch("examples.mcp_server.fetch_context", side_effect=OSError("local API unavailable")):
            response = handle_message(modern_request(7, "tools/call", {"name": "get_context", "arguments": {}}))
        self.assertTrue(response["result"]["isError"])
        self.assertIn("local API unavailable", response["result"]["content"][0]["text"])
        self.assertEqual(response["result"]["resultType"], "complete")

    def test_modern_notifications_do_not_emit_responses(self):
        self.assertIsNone(handle_message({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}}))

    def test_modern_stdio_round_trip_uses_discover_and_per_request_metadata(self):
        requests = [
            modern_request(1, "server/discover"),
            modern_request(2, "tools/list"),
            modern_request(3, "tools/call", {"name": "get_context", "arguments": {}}),
            {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 3}},
        ]
        incoming = io.StringIO("\n".join(json.dumps(item) for item in requests) + "\n")
        outgoing = io.StringIO()
        payload = {"schema_version": "1.0", "markdown": "# Local context", "rules": [], "rule_count": 0}
        with patch("examples.mcp_server.fetch_context", return_value=payload):
            run_stdio(incoming, outgoing)
        responses = [json.loads(line) for line in outgoing.getvalue().splitlines()]
        self.assertEqual([item["id"] for item in responses], [1, 2, 3])
        self.assertEqual(responses[2]["result"]["content"][0]["text"], "# Local context")

    def test_legacy_stdio_round_trip_remains_compatible(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "legacy test", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_context", "arguments": {}}},
            {"jsonrpc": "2.0", "method": "exit"},
        ]
        incoming, outgoing = io.StringIO("\n".join(json.dumps(item) for item in requests) + "\n"), io.StringIO()
        payload = {"schema_version": "1.0", "markdown": "# Legacy context", "rules": [], "rule_count": 0}
        with patch("examples.mcp_server.fetch_context", return_value=payload):
            run_stdio(incoming, outgoing)
        responses = [json.loads(line) for line in outgoing.getvalue().splitlines()]
        self.assertEqual([item["id"] for item in responses], [1, 2, 3])
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-11-25")
        self.assertNotIn("resultType", responses[1]["result"])
        self.assertEqual(responses[2]["result"]["content"][0]["text"], "# Legacy context")

    def test_legacy_initialize_negotiates_supported_fallback(self):
        incoming = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}) + "\n")
        outgoing = io.StringIO()
        run_stdio(incoming, outgoing)
        response = json.loads(outgoing.getvalue())
        self.assertEqual(response["result"]["protocolVersion"], "2025-11-25")

    def test_modern_server_rejects_legacy_initialize_outside_legacy_connection(self):
        response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}})
        self.assertEqual(response["error"]["code"], -32601)

    def test_mcp_cli_refuses_non_loopback_api_url(self):
        errors = io.StringIO()
        with redirect_stderr(errors):
            status = main(["--base-url", "https://example.com"])
        self.assertEqual(status, 2)
        self.assertIn("local-only", errors.getvalue())

    def test_malformed_json_receives_parse_error(self):
        incoming, outgoing = io.StringIO("{not-json}\n"), io.StringIO()
        run_stdio(incoming, outgoing)
        response = json.loads(outgoing.getvalue())
        self.assertEqual(response["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
