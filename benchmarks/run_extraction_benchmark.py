"""Run a deterministic synthetic extraction/evidence benchmark.

This benchmark measures exact expected-text preservation and evidence integrity
for generated fixtures. It is not a substitute for a labelled corpus of real
customer documents or a human review of OCR/layout quality.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_studio.documents import extract_document


def _pdf() -> bytes:
    import pymupdf as fitz

    document = fitz.open()
    document.new_page().insert_text((72, 72), "Context Studio benchmark PDF page alpha")
    document.new_page().insert_text((72, 72), "Context Studio benchmark PDF page beta")
    result = document.tobytes()
    document.close()
    return result


def _docx() -> bytes:
    from docx import Document

    document = Document()
    document.add_heading("Benchmark Word heading", level=1)
    document.add_paragraph("Word paragraph locator benchmark phrase.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Control"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Word table evidence"
    table.cell(1, 1).text = "Verified"
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def _pptx() -> bytes:
    from pptx import Presentation
    from pptx.util import Inches

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1)).text = "PowerPoint shape evidence phrase"
    table = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(5), Inches(1)).table
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Result"
    table.cell(1, 0).text = "Slide table evidence"
    table.cell(1, 1).text = "Pass"
    stream = io.BytesIO()
    deck.save(stream)
    return stream.getvalue()


def _xlsx() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Benchmark Costs"
    sheet.append(["Category", "Amount"])
    sheet.append(["Spreadsheet evidence phrase", 42])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def build_corpus() -> list[dict[str, Any]]:
    csv_stream = io.StringIO(newline="")
    writer = csv.writer(csv_stream)
    writer.writerow(["Service", "Monthly cost"])
    writer.writerow(["CSV evidence phrase", "42"])

    return [
        {"name": "benchmark.txt", "content": b"Plain text evidence phrase for Context Studio.\n", "expected": ["Plain text evidence phrase"], "locators": ["text_file"]},
        {"name": "benchmark.md", "content": b"# Markdown benchmark\n\nMarkdown evidence phrase stays intact.\n", "expected": ["# Markdown benchmark", "Markdown evidence phrase"], "locators": ["text_file"]},
        {"name": "benchmark.csv", "content": csv_stream.getvalue().encode("utf-8"), "expected": ["CSV evidence phrase", "Monthly cost"], "locators": ["csv_table"]},
        {"name": "benchmark.json", "content": json.dumps({"service": "Context Studio", "note": "JSON evidence phrase"}).encode("utf-8"), "expected": ["Context Studio", "JSON evidence phrase"], "locators": ["json_document"]},
        {"name": "benchmark.html", "content": b"<html><body><h1>HTML evidence phrase</h1><script>must_not_appear()</script></body></html>", "expected": ["HTML evidence phrase"], "forbidden": ["must_not_appear"], "locators": ["html_visible_text"]},
        {"name": "benchmark.pdf", "content": _pdf(), "expected": ["PDF page alpha", "PDF page beta"], "locators": ["pdf_page"]},
        {"name": "benchmark.docx", "content": _docx(), "expected": ["Benchmark Word heading", "Word paragraph locator benchmark phrase", "Word table evidence"], "locators": ["docx_paragraph", "docx_table"]},
        {"name": "benchmark.pptx", "content": _pptx(), "expected": ["PowerPoint shape evidence phrase", "Slide table evidence"], "locators": ["pptx_shape", "pptx_table"]},
        {"name": "benchmark.xlsx", "content": _xlsx(), "expected": ["Benchmark Costs", "Spreadsheet evidence phrase", "42"], "locators": ["xlsx_sheet_heading", "xlsx_range"]},
    ]


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = extract_document(case["name"], case["content"], processing_mode="native_only")
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    except Exception as exc:  # A benchmark failure should be reported, not hide other fixtures.
        return {"name": case["name"], "passed": False, "error": f"{type(exc).__name__}: {exc}"}

    markdown = result.get("markdown", "")
    evidence = result.get("evidence") or {}
    blocks = evidence.get("blocks") if isinstance(evidence.get("blocks"), list) else []
    locators = {block.get("locator", {}).get("type") for block in blocks if isinstance(block.get("locator"), dict)}
    phrase_checks = [{"phrase": phrase, "passed": phrase in markdown} for phrase in case["expected"]]
    forbidden_checks = [{"phrase": phrase, "passed": phrase not in markdown} for phrase in case.get("forbidden", [])]
    locator_checks = [{"locator": locator, "passed": locator in locators} for locator in case["locators"]]

    range_checks = []
    for block in blocks:
        span = block.get("markdown_range") or {}
        start, end = span.get("start"), span.get("end")
        valid_range = isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(markdown)
        text = markdown[start:end] if valid_range else ""
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest() if valid_range else ""
        range_checks.append({"block_id": block.get("block_id"), "passed": valid_range and digest == block.get("content_sha256")})

    source_id_ok = evidence.get("source_id") == hashlib.sha256(case["content"]).hexdigest()
    try:
        repeated = extract_document(case["name"], case["content"], processing_mode="native_only")
        stable_ids_ok = (
            evidence.get("source_id") == (repeated.get("evidence") or {}).get("source_id")
            and [block.get("block_id") for block in blocks]
            == [block.get("block_id") for block in (repeated.get("evidence") or {}).get("blocks", [])]
        )
    except Exception:
        stable_ids_ok = False

    checks = [*phrase_checks, *forbidden_checks, *locator_checks, *range_checks]
    checks.extend([
        {"check": "source_sha256", "passed": source_id_ok},
        {"check": "stable_ids", "passed": stable_ids_ok},
        {"check": "evidence_schema_1.0", "passed": evidence.get("schema_version") == "1.0" and bool(blocks)},
    ])
    passed = all(item["passed"] for item in checks)
    return {
        "name": case["name"],
        "passed": passed,
        "elapsed_ms": elapsed_ms,
        "markdown_characters": len(markdown),
        "evidence_blocks": len(blocks),
        "locator_types": sorted(locators),
        "checks": checks,
    }


def main() -> int:
    results = [evaluate_case(case) for case in build_corpus()]
    passed = sum(bool(result.get("passed")) for result in results)
    total = len(results)
    check_total = sum(len(result.get("checks", [])) for result in results)
    check_passed = sum(sum(bool(check.get("passed")) for check in result.get("checks", [])) for result in results)
    report = {
        "benchmark": "context-studio-synthetic-extraction",
        "benchmark_version": "1.0",
        "corpus_kind": "generated_synthetic_fixtures",
        "native_only": True,
        "external_model_calls": 0,
        "fixtures_passed": passed,
        "fixtures_total": total,
        "checks_passed": check_passed,
        "checks_total": check_total,
        "results": results,
        "interpretation": "Synthetic regression evidence only; not a claim of real-world OCR, layout or semantic extraction accuracy.",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed == total and check_passed == check_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
