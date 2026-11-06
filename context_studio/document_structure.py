from __future__ import annotations

import hashlib
import re
from typing import Any

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")


def split_evidence_block(
    markdown: str,
    *,
    markdown_start: int,
    markdown_end: int,
    source_locator: dict[str, Any],
    block_id: str,
) -> list[dict[str, Any]]:
    """Build a deterministic heading/paragraph tree with exact Markdown offsets."""
    text = markdown[markdown_start:markdown_end]
    line_offsets: list[tuple[int, int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        line_offsets.append((offset, offset + len(line), line))
        offset += len(line)
    if not line_offsets and text:
        line_offsets.append((0, len(text), text))

    # Events are emitted in document order. A parent heading is always emitted
    # before its descendants, allowing the store to resolve parent IDs in one pass.
    events: list[dict[str, Any]] = []
    heading_stack: list[tuple[int, int, str]] = []  # level, event index, title
    pending: list[tuple[int, int, str]] = []

    def append_node(
        start: int,
        end: int,
        *,
        node_type: str,
        title: str | None = None,
        parent_index: int | None = None,
        section_path: str | None = None,
    ) -> int | None:
        raw = text[start:end]
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        absolute_start = markdown_start + start + leading
        absolute_end = markdown_start + start + trailing
        content = markdown[absolute_start:absolute_end]
        if not content:
            return None
        locator = {
            **source_locator,
            "section": section_path or source_locator.get("section", "Document"),
            "markdown_start": absolute_start,
            "markdown_end": absolute_end,
        }
        events.append({
            "node_type": node_type,
            "title": title,
            "content": content,
            "locator_json": locator,
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "parent_index": parent_index,
        })
        return len(events) - 1

    def flush_pending() -> None:
        if not pending:
            return
        groups: list[list[tuple[int, int, str]]] = []
        current: list[tuple[int, int, str]] = []
        for line in pending:
            if not line[2].strip():
                if current:
                    groups.append(current)
                    current = []
            else:
                current.append(line)
        if current:
            groups.append(current)

        parent_index = heading_stack[-1][1] if heading_stack else None
        section_path = " / ".join(item[2] for item in heading_stack) or None
        for group in groups:
            start, end = group[0][0], group[-1][1]
            first = group[0][2].strip()
            node_type = "table" if _TABLE_LINE.match(first) else "paragraph"
            append_node(
                start,
                end,
                node_type=node_type,
                parent_index=parent_index,
                section_path=section_path,
            )
        pending.clear()

    for start, end, line in line_offsets:
        match = _HEADING.match(line.rstrip("\r\n"))
        if not match:
            pending.append((start, end, line))
            continue

        flush_pending()
        level = len(match.group(1))
        title = match.group(2).strip()
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        parent_index = heading_stack[-1][1] if heading_stack else None
        heading_index = append_node(
            start,
            end,
            node_type="section",
            title=title,
            parent_index=parent_index,
            section_path=" / ".join([item[2] for item in heading_stack] + [title]),
        )
        if heading_index is not None:
            heading_stack.append((level, heading_index, title))

    flush_pending()

    result: list[dict[str, Any]] = []
    multiple = len(events) > 1
    event_keys = [
        f"{block_id}:part:{index + 1}" if multiple else block_id
        for index in range(len(events))
    ]
    for index, event in enumerate(events):
        parent_index = event.pop("parent_index")
        result.append({
            "node_key": event_keys[index],
            "parent_node_key": event_keys[parent_index] if parent_index is not None else None,
            "ordinal": index,
            **event,
        })
    return result
