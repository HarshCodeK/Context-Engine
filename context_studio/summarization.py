from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any

_WORDS = re.compile(r"[\w'-]{2,}", re.UNICODE)
_SENTENCES = re.compile(r"[^.!?\n]+(?:[.!?]+|(?=\n)|$)")
_STOPWORDS = {
    "about", "after", "again", "against", "also", "among", "and", "are", "because",
    "been", "before", "being", "between", "both", "but", "can", "could", "did",
    "does", "each", "for", "from", "had", "has", "have", "into", "its", "may",
    "might", "more", "most", "not", "our", "out", "over", "same", "should",
    "such", "than", "that", "the", "their", "them", "then", "there", "these", "they",
    "this", "those", "through", "under", "until", "upon", "was", "were", "when",
    "where", "which", "while", "will", "with", "within", "would", "you", "your",
}
_SIGNAL_WORDS = {
    "approved", "approval", "decision", "decided", "launch", "deadline", "date",
    "owner", "risk", "budget", "requirement", "required", "must", "shall", "change",
    "changed", "status", "target", "issue", "action", "scope", "metric", "constraint",
    "because", "therefore", "however", "except", "only", "unless", "increase",
    "decrease", "delay", "resolved", "revised", "current", "superseded",
}
_DATE_OR_NUMBER = re.compile(r"(?:\b\d{1,4}[/-]\d{1,2}(?:[/-]\d{1,4})?\b|\b\d+(?:\.\d+)?%?\b)")


def _tokens(text: str) -> list[str]:
    return [word.casefold() for word in _WORDS.findall(text) if word.casefold() not in _STOPWORDS]


def build_extractive_digest(
    nodes: list[dict[str, Any]],
    *,
    max_sentences: int = 12,
    max_chars: int = 1800,
) -> dict[str, Any]:
    """Create a deterministic, source-linked evidence digest without a language model."""
    if max_sentences < 1 or max_chars < 100:
        raise ValueError("Digest limits must be positive and max_chars must be at least 100")

    candidates: list[dict[str, Any]] = []
    document_frequency: Counter[str] = Counter()
    node_count = max(1, len(nodes))

    for node in nodes:
        content = str(node.get("content") or "")
        node_terms = set(_tokens(content))
        document_frequency.update(node_terms)
        node_position = 0
        for match in _SENTENCES.finditer(content):
            raw_sentence = match.group(0)
            leading = len(raw_sentence) - len(raw_sentence.lstrip())
            trailing = len(raw_sentence.rstrip())
            sentence = raw_sentence.strip()
            if len(sentence) < 28:
                continue
            words = _tokens(sentence)
            if len(words) < 4:
                continue
            candidates.append({
                "node_id": node["id"],
                "locator": node.get("locator") or {},
                "content_sha256": node.get("content_sha256"),
                "start_offset": match.start() + leading,
                "end_offset": match.start() + trailing,
                "text": sentence,
                "words": words,
                "position": node_position,
            })
            node_position += 1

    if not candidates:
        return {
            "text": "",
            "method": "extractive-tfidf-v1",
            "evidence": [],
            "input_characters": sum(len(str(node.get("content") or "")) for node in nodes),
            "summary_characters": 0,
        }

    sentence_frequency = Counter(
        word for candidate in candidates for word in set(candidate["words"])
    )
    seen_sets: list[set[str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = " ".join(candidate["words"])
        terms = set(candidate["words"])
        if normalized in seen or any(
            len(terms & prior) / max(1, len(terms | prior)) >= 0.76
            for prior in seen_sets
        ):
            candidate["score"] = -1.0
            continue
        seen.add(normalized)
        seen_sets.append(terms)
        term_counts = Counter(candidate["words"])
        lexical = sum(
            (1.0 + math.log(count)) *
            (math.log((len(candidates) + 1) / (sentence_frequency[word] + 0.5)) + 1.0)
            for word, count in term_counts.items()
        )
        signal = sum(1 for word in terms if word in _SIGNAL_WORDS)
        numeric = 1 if _DATE_OR_NUMBER.search(candidate["text"]) else 0
        length = len(candidate["words"])
        length_fit = 1.0 if 9 <= length <= 34 else 0.72 if length < 9 else 0.82
        lead = 1.0 / (1.0 + candidate["position"] * 0.08)
        boilerplate = 0.45 if candidate["text"].casefold().startswith("implementation note:") else 1.0
        candidate["score"] = round((lexical + signal * 0.8 + numeric * 0.4) * length_fit * lead * boilerplate, 8)

    ranked = sorted(
        (candidate for candidate in candidates if candidate["score"] >= 0),
        key=lambda item: (-item["score"], item["start_offset"], item["node_id"]),
    )

    chosen: list[dict[str, Any]] = []
    chosen_chars = 0
    node_coverage: set[str] = set()
    for candidate in ranked:
        if candidate["node_id"] in node_coverage:
            continue
        extra = len(candidate["text"]) + (2 if chosen else 0)
        if chosen and chosen_chars + extra > max_chars:
            continue
        chosen.append(candidate)
        chosen_chars += extra
        node_coverage.add(candidate["node_id"])
        if len(chosen) >= max_sentences:
            break
    for candidate in ranked:
        if candidate in chosen or len(chosen) >= max_sentences:
            continue
        extra = len(candidate["text"]) + (2 if chosen else 0)
        if chosen_chars + extra > max_chars:
            continue
        chosen.append(candidate)
        chosen_chars += extra

    chosen.sort(key=lambda item: (item["node_id"], item["start_offset"]))
    digest_text = "\n\n".join(item["text"] for item in chosen)
    evidence = [{
        "node_id": item["node_id"],
        "locator": item["locator"],
        "start_offset": item["start_offset"],
        "end_offset": item["end_offset"],
        "node_content_sha256": item["content_sha256"],
        "sentence_sha256": hashlib.sha256(item["text"].encode("utf-8")).hexdigest(),
        "score": item["score"],
    } for item in chosen]

    return {
        "text": digest_text,
        "method": "extractive-tfidf-v1",
        "evidence": evidence,
        "input_characters": sum(len(str(node.get("content") or "")) for node in nodes),
        "summary_characters": len(digest_text),
    }


