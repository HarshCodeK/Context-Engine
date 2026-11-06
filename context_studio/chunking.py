from __future__ import annotations

import re


def _split_long_segment(segment: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", segment.strip())
    result: list[str] = []
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            result.append(sentence)
            continue
        words = sentence.split()
        current = ""
        for word in words:
            if len(word) > max_chars:
                if current:
                    result.append(current)
                    current = ""
                result.extend(word[index:index + max_chars] for index in range(0, len(word), max_chars))
                continue
            candidate = f"{current} {word}".strip()
            if len(candidate) > max_chars and current:
                result.append(current)
                current = word
            else:
                current = candidate
        if current:
            result.append(current)
    return result


def structure_aware_chunks(text: str, max_chars: int = 1200, overlap_chars: int = 120) -> list[str]:
    """Pack paragraphs/sentences deterministically, splitting only oversized units."""
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars")
    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    segments: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            segments.append(paragraph)
        else:
            segments.extend(_split_long_segment(paragraph, max_chars))

    chunks: list[str] = []
    current = ""
    for segment in segments:
        candidate = f"{current}\n\n{segment}".strip() if current else segment
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            overlap = current[-overlap_chars:] if overlap_chars else ""
            if overlap:
                boundary = overlap.find(" ")
                if boundary >= 0:
                    overlap = overlap[boundary + 1:]
            current = f"{overlap}\n\n{segment}".strip() if overlap else segment
            if len(current) > max_chars:
                # The segment is already bounded; trim overlap rather than split it again.
                current = segment
        else:
            current = segment
    if current:
        chunks.append(current)
    return chunks
