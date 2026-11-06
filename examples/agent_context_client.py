"""Small dependency-free client for local coding-agent context retrieval.

Agents can run this command before a task and consume its Markdown on stdout.
The client deliberately accepts loopback URLs only so saved rules are not sent
to an accidentally configured remote host.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


def build_url(base_url: str, project_key: str | None, task_tags: list[str]) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Context Studio agent access is local-only; use an http:// loopback base URL")
    if parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Base URL must contain only the local host and optional port")
    params: dict[str, str] = {}
    if project_key:
        params["project_key"] = project_key
    if task_tags:
        params["task_tags"] = ",".join(task_tags)
    return urlunsplit(("http", parsed.netloc, "/api/agent-context", urlencode(params), ""))


def fetch_context(base_url: str, project_key: str | None, task_tags: list[str]) -> dict:
    url = build_url(base_url, project_key, task_tags)
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    with urlopen(request, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("markdown"), str):
        raise ValueError("Context Studio returned an unsupported or malformed response")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch scoped Context Studio rules for a local AI agent")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Local Context Studio URL (loopback only)")
    parser.add_argument("--project-key", help="Project key to match")
    parser.add_argument("--task-tag", action="append", default=[], help="Task tag to match; may be repeated")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format (default: markdown)")
    args = parser.parse_args(argv)
    try:
        payload = fetch_context(args.base_url, args.project_key, args.task_tag)
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["markdown"])
        return 0
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        print(f"Context Studio returned HTTP {exc.code}: {detail}", file=sys.stderr)
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Could not retrieve local Context Studio context: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
