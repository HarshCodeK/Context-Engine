from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import time
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pymupdf as fitz
from docx import Document
from openpyxl import load_workbook
from PIL import Image, ImageOps, UnidentifiedImageError
from pptx import Presentation

from .settings import (
    MAX_BYTES, MAX_IMAGE_PIXELS, MAX_OCR_SECONDS, MAX_OCR_TOTAL_SECONDS,
    MAX_OCR_PAGES_PER_FILE, MAX_PAGES, MAX_TABLE_ROWS, MAX_TABLE_COLUMNS,
    MAX_TABLE_CELLS, MAX_PPTX_SLIDES, MAX_PPTX_SHAPES,
    MAX_DOCX_PARAGRAPHS, MAX_EXTRACTED_CHARS, OFFICE_MARKERS, SUPPORTED,
)

logger = logging.getLogger("context_studio")

def _tesseract_executable() -> str | None:
    configured = os.getenv("TESSERACT_CMD", "tesseract").strip()
    if not configured:
        return None
    configured_path = Path(configured).expanduser()
    if configured_path.is_file():
        return str(configured_path)
    return shutil.which(configured)


def _ocr_available() -> bool:
    return _tesseract_executable() is not None


class VisibleText(HTMLParser):
    """Extract visible HTML text while excluding script/style-like content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self.hidden += 1
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "template"} and self.hidden:
            self.hidden -= 1
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr", "section"} and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean(value: str) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"[ \t]+\n", "\n", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def table_md(rows) -> str:
    rows = [[str(cell if cell is not None else "").replace("|", r"\|").replace("\r", "").replace("\n", "<br>") for cell in row] for row in rows]
    if not rows:
        return "_No rows found._"
    width = max(map(len, rows))
    rows = [row + [""] * (width - len(row)) for row in rows]
    return "\n".join(
        ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
        + ["| " + " | ".join(row) + " |" for row in rows[1:]]
    )


class MarkdownChunks:
    """Build bounded Markdown and stable, versioned source-to-output evidence."""

    def __init__(self, title: str, source_id: str):
        self.parts = [title]
        self.characters = len(title)
        self.source_id = source_id
        self.evidence: list[dict[str, Any]] = []

    def append(self, value: Any, *, locator: dict[str, Any] | None = None, method: str = "native_parser") -> None:
        text = clean(str(value))
        if not text:
            return
        if self.characters + len(text) + 2 > MAX_EXTRACTED_CHARS:
            raise ValueError(f"Extracted output exceeds the {MAX_EXTRACTED_CHARS:,}-character safety limit; split the source into smaller files.")
        locator = locator or {"type": "document_section", "index": len(self.evidence) + 1}
        canonical_locator = json.dumps(locator, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        block_id = hashlib.sha256(f"{self.source_id}:{canonical_locator}".encode("utf-8")).hexdigest()[:24]
        start = self.characters + 2
        end = start + len(text)
        self.evidence.append({
            "block_id": block_id,
            "source_id": self.source_id,
            "locator": locator,
            "markdown_range": {"start": start, "end": end, "unit": "unicode_code_points", "end_exclusive": True},
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "extraction_method": method,
        })
        self.parts.append(text)
        self.characters = end

    def render(self) -> str:
        return "\n\n".join(self.parts)


def bounded_table_rows(rows, max_cells: int = MAX_TABLE_CELLS) -> tuple[list[list[Any]], bool]:
    """Collect a bounded table without materializing an untrusted full sheet."""
    result: list[list[Any]] = []
    cells = 0
    characters = 0
    truncated = False
    for raw_row in rows:
        if len(result) >= MAX_TABLE_ROWS or cells >= max_cells:
            truncated = True
            break
        row = list(raw_row)
        if len(row) > MAX_TABLE_COLUMNS:
            row = row[:MAX_TABLE_COLUMNS]
            truncated = True
        remaining = max_cells - cells
        if len(row) > remaining:
            row = row[:remaining]
            truncated = True
        row_characters = sum(len(str(value)) for value in row if value is not None)
        if characters + row_characters > MAX_EXTRACTED_CHARS:
            raise ValueError(f"Table text exceeds the {MAX_EXTRACTED_CHARS:,}-character safety limit")
        result.append(row)
        cells += len(row)
        characters += row_characters
        if cells >= max_cells:
            truncated = True
            break
    return result, truncated


def validate_office_archive(content: bytes, extension: str) -> None:
    """Check ZIP structure and expansion bounds before calling Office parsers."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            names = {item.filename for item in entries}
            if len(entries) > 5000:
                raise ValueError("Office archive contains too many entries (limit: 5,000)")
            if any(item.flag_bits & 0x1 for item in entries):
                raise ValueError("Encrypted Office documents are not supported; remove the password and retry")
            total = sum(item.file_size for item in entries)
            if total > 100 * 1024 * 1024:
                raise ValueError("Office archive expands beyond the 100 MB safety limit")
            for item in entries:
                if item.file_size > 50 * 1024 * 1024:
                    raise ValueError("An Office archive entry exceeds the 50 MB safety limit")
                if item.file_size > 1024 * 1024 and item.compress_size == 0:
                    raise ValueError("Office archive contains a suspicious highly-compressed entry")
                if item.compress_size and item.file_size / item.compress_size > 200:
                    raise ValueError("Office archive compression ratio exceeds the safety limit")
            if "[Content_Types].xml" not in names or OFFICE_MARKERS[extension] not in names:
                raise ValueError(f"File content does not look like a valid {extension[1:].upper()} document")
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid Office document archive") from exc


def validate_file_content(filename: str, content: bytes, content_type: str | None = None) -> str:
    """Validate file size, extension, and format signatures before parsing."""
    extension = Path(Path(filename).name).suffix.lower()
    if extension not in SUPPORTED:
        raise ValueError(f"Unsupported format: {extension or 'no extension'}")
    if not content:
        raise ValueError("This file is empty. Choose a file with content and retry.")
    if len(content) > MAX_BYTES:
        raise ValueError(f"File exceeds the {MAX_BYTES // (1024 * 1024)} MB limit")
    expected_mime = {
        ".pdf": {"application/pdf"}, ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
        ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        ".png": {"image/png"}, ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".webp": {"image/webp"},
        ".json": {"application/json", "text/json"}, ".csv": {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"},
        ".html": {"text/html", "application/xhtml+xml"}, ".htm": {"text/html", "application/xhtml+xml"},
        ".txt": {"text/plain"}, ".md": {"text/markdown", "text/plain"}, ".markdown": {"text/markdown", "text/plain"},
    }
    claimed = (content_type or "").split(";", 1)[0].strip().lower()
    if claimed and claimed not in {"application/octet-stream", "application/zip", "binary/octet-stream"} and claimed not in expected_mime[extension]:
        raise ValueError(f"The browser reported {claimed}, which does not match the .{extension.lstrip('.')} file type")
    if extension == ".pdf":
        if not content.lstrip().startswith(b"%PDF-"):
            raise ValueError("File extension says PDF, but the file signature is not a PDF")
    elif extension in OFFICE_MARKERS:
        validate_office_archive(content, extension)
    elif extension in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            with Image.open(io.BytesIO(content)) as image:
                actual = image.format
                allowed = {".png": {"PNG"}, ".jpg": {"JPEG"}, ".jpeg": {"JPEG"}, ".webp": {"WEBP"}}
                if actual not in allowed[extension]:
                    raise ValueError("Image extension does not match its actual format")
                width, height = image.size
                if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                    raise ValueError(f"Image dimensions exceed the {MAX_IMAGE_PIXELS:,}-pixel safety limit")
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Invalid or corrupt image file") from exc
    else:
        if b"\x00" in content:
            raise ValueError("This looks like a binary file, not a supported text document")
        if extension == ".json":
            try:
                json.loads(content.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Invalid JSON: check the encoding and syntax") from exc
    return extension


def ocr_image(image: Image.Image, timeout_seconds: float | None = None, deadline: float | None = None) -> str:
    """Run bounded OCR if the optional Tesseract executable is installed."""
    executable = _tesseract_executable()
    if executable is None:
        raise RuntimeError("OCR support is not available")
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError(f"Image dimensions exceed the {MAX_IMAGE_PIXELS:,}-pixel OCR limit")
    remaining = deadline - time.monotonic() if deadline is not None else MAX_OCR_SECONDS
    if timeout_seconds is not None:
        remaining = min(remaining, timeout_seconds)
    timeout = min(MAX_OCR_SECONDS, remaining)
    if timeout <= 0:
        raise TimeoutError("OCR time budget exhausted")
    source = io.BytesIO()
    image.save(source, format="PNG")
    try:
        result = subprocess.run(
            [executable, "stdin", "stdout", "-l", os.getenv("OCR_LANGUAGE", "eng")],
            input=source.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("Tesseract OCR exceeded its time budget") from exc
    if result.returncode:
        raise RuntimeError("Tesseract could not process this image")
    return result.stdout.decode("utf-8", errors="replace").strip()


def extract_document(filename: str, content: bytes, content_type: str | None = None, processing_mode: str = "auto") -> dict[str, Any]:
    started = time.perf_counter()
    if processing_mode not in {"auto", "native_only"}:
        raise ValueError("Processing mode must be 'auto' or 'native_only'")
    name = Path(filename).name
    ext = validate_file_content(name, content, content_type)
    source_id = hashlib.sha256(content).hexdigest()
    warnings: list[str] = []
    evidence_locator: dict[str, Any] = {"type": "file"}
    evidence_method = "deterministic_parser"
    pages = 1
    ocr_pages = 0
    ocr_attempts = 0
    empty_pages = 0
    native_only_scanned_pages = 0
    image_ocr_used = False
    title = Path(name).stem

    if ext in {".txt", ".md", ".markdown"}:
        evidence_locator = {"type": "text_file"}
        evidence_method = "utf8_decode"
        text = content.decode("utf-8-sig", errors="replace")
        if "\ufffd" in text:
            warnings.append("Some bytes could not be decoded as UTF-8; review the result.")
        md = text.strip() if ext in {".md", ".markdown"} else f"# {title}\n\n{text.strip()}"
    elif ext == ".csv":
        evidence_method = "csv_parse"
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = content.decode("utf-8-sig", errors="replace")
            warnings.append("Some CSV bytes could not be decoded as UTF-8; review cell contents.")
        try:
            rows, truncated = bounded_table_rows(csv.reader(io.StringIO(decoded, newline=""), strict=True))
        except csv.Error as exc:
            raise ValueError(f"Could not parse CSV: {exc}") from exc
        if truncated:
            warnings.append(f"CSV output truncated at {MAX_TABLE_ROWS:,} rows, {MAX_TABLE_COLUMNS:,} columns or {MAX_TABLE_CELLS:,} cells.")
        evidence_locator = {"type": "csv_table", "row_count": len(rows), "column_count": max((len(row) for row in rows), default=0)}
        md = f"# {title}\n\n" + table_md(rows)
    elif ext == ".json":
        evidence_locator = {"type": "json_document"}
        evidence_method = "json_parse"
        md = f"# {title}\n\n```json\n{json.dumps(json.loads(content.decode('utf-8-sig')), ensure_ascii=False, indent=2)}\n```"
    elif ext in {".html", ".htm"}:
        evidence_locator = {"type": "html_visible_text"}
        evidence_method = "html_visible_text_parse"
        parser = VisibleText()
        parser.feed(content.decode("utf-8", errors="replace"))
        md = f"# {title}\n\n{clean(''.join(parser.parts))}"
        warnings.append("HTML styling, links, and layout are omitted; visible text only.")
    elif ext == ".pdf":
        try:
            with fitz.open(stream=content, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise ValueError("This PDF is password-protected. Unlock it and retry.")
                if doc.page_count == 0:
                    raise ValueError("This PDF has no pages.")
                if doc.page_count > MAX_PAGES:
                    raise ValueError(f"PDF exceeds the {MAX_PAGES}-page limit")
                pages = doc.page_count
                chunks = MarkdownChunks(f"# {title}", source_id)
                ocr_deadline = time.monotonic() + MAX_OCR_TOTAL_SECONDS
                ocr_budget_warned = False
                for index, page in enumerate(doc, 1):
                    text = clean(page.get_text("text"))
                    page_method = "native_pdf_text" if text else "unreadable_scan"
                    if not text:
                        ocr_text = ""
                        ocr_allowed = processing_mode == "auto" and _ocr_available() and ocr_attempts < MAX_OCR_PAGES_PER_FILE and time.monotonic() < ocr_deadline
                        if ocr_allowed:
                            try:
                                rect = page.rect
                                rendered_pixels = max(0, int(rect.width * 130 / 72)) * max(0, int(rect.height * 130 / 72))
                                if rendered_pixels <= MAX_IMAGE_PIXELS:
                                    ocr_attempts += 1
                                    pixmap = page.get_pixmap(dpi=130, alpha=False)
                                    remaining = ocr_deadline - time.monotonic()
                                    if remaining > 0.1:
                                        with Image.open(io.BytesIO(pixmap.tobytes("png"))) as image:
                                            ocr_text = ocr_image(image, timeout_seconds=remaining, deadline=ocr_deadline)
                                    elif not ocr_budget_warned:
                                        warnings.append(f"PDF OCR stopped at the {MAX_OCR_PAGES_PER_FILE}-page or {MAX_OCR_TOTAL_SECONDS}-second per-file budget.")
                                        ocr_budget_warned = True
                                else:
                                    warnings.append(f"Page {index} was too large to render safely for OCR.")
                            except (RuntimeError, OSError, ValueError) as exc:
                                logger.info("OCR unavailable for page %s (%s)", index, type(exc).__name__)
                        elif processing_mode == "native_only":
                            native_only_scanned_pages += 1
                        elif _ocr_available() and not ocr_budget_warned:
                            warnings.append(f"PDF OCR stopped at the {MAX_OCR_PAGES_PER_FILE}-page or {MAX_OCR_TOTAL_SECONDS}-second per-file budget.")
                            ocr_budget_warned = True
                        if ocr_text:
                            text = ocr_text
                            page_method = "local_ocr"
                            ocr_pages += 1
                        else:
                            text = "_(No selectable text found on this page.)_"
                        if _ocr_available() and time.monotonic() >= ocr_deadline and not ocr_budget_warned:
                            warnings.append(f"PDF OCR stopped at the {MAX_OCR_PAGES_PER_FILE}-page or {MAX_OCR_TOTAL_SECONDS}-second per-file budget.")
                            ocr_budget_warned = True
                    chunks.append(f"## Page {index}\n\n{text}", locator={"type": "pdf_page", "page": index}, method=page_method)
                md = chunks.render()
                empty_pages = sum("No selectable text found" in chunk for chunk in chunks.parts)
                if ocr_pages:
                    warnings.append(f"OCR recovered text from {ocr_pages} scanned page(s); review recognition errors.")
                if native_only_scanned_pages:
                    warnings.append(f"Native text-only mode skipped OCR on {native_only_scanned_pages} scanned page(s).")
                if empty_pages:
                    if processing_mode == "native_only":
                        warnings.append(f"{empty_pages} page(s) had no selectable text; native-text-only mode left them unreadable.")
                    else:
                        warnings.append(f"{empty_pages} page(s) had no readable text. OCR may be unavailable, timed out, or unable to recognize the scan.")
                warnings.append("PDF reading order and tables may differ from the original page layout.")
        except fitz.FileDataError as exc:
            raise ValueError("Invalid or corrupt PDF file") from exc
    elif ext in {".png", ".jpg", ".jpeg", ".webp"}:
        evidence_method = "image_metadata"
        try:
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
                if processing_mode == "native_only":
                    text = ""
                    warnings.append("Native text-only mode skipped OCR; image text was not extracted.")
                elif not _ocr_available():
                    text = ""
                    warnings.append("OCR is unavailable in this environment; image text was not extracted.")
                else:
                    try:
                        text = ocr_image(image)
                        image_ocr_used = bool(text)
                        evidence_method = "local_ocr" if image_ocr_used else "image_metadata"
                    except (RuntimeError, OSError, ValueError) as exc:
                        text = ""
                        warnings.append(f"OCR could not finish for this image ({type(exc).__name__}). Try a smaller, clearer image.")
                md = f"# {title}\n\n{text or '_(No text could be extracted from this image.)_'}"
                evidence_locator = {"type": "image", "width": width, "height": height}
                warnings.append(f"Image dimensions: {width} × {height} pixels. Visual layout, diagrams, and non-text content are not interpreted.")
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Invalid or corrupt image file") from exc
    elif ext == ".docx":
        doc = Document(io.BytesIO(content))
        chunks = MarkdownChunks(f"# {title}", source_id)
        if len(doc.paragraphs) > MAX_DOCX_PARAGRAPHS:
            warnings.append(f"Word paragraphs truncated at {MAX_DOCX_PARAGRAPHS:,}.")
        for paragraph_index, paragraph in enumerate(doc.paragraphs[:MAX_DOCX_PARAGRAPHS], 1):
            text = paragraph.text.strip()
            if text:
                match = re.search(r"\d+", paragraph.style.name if paragraph.style else "")
                level = min(int(match.group()), 6) if match and paragraph.style and "heading" in paragraph.style.name.lower() else 0
                chunks.append("#" * level + " " + text if level else text,
                              locator={"type": "docx_paragraph", "paragraph": paragraph_index, "style": paragraph.style.name if paragraph.style else ""},
                              method="native_docx")
        remaining_cells = MAX_TABLE_CELLS
        for index, table in enumerate(doc.tables, 1):
            rows, truncated = bounded_table_rows(([cell.text for cell in row.cells] for row in table.rows), remaining_cells)
            chunks.append(f"## Table {index}", locator={"type": "docx_table_heading", "table": index}, method="native_docx")
            chunks.append(table_md(rows), locator={"type": "docx_table", "table": index, "row_start": 1, "row_end": len(rows), "column_count": max((len(row) for row in rows), default=0)}, method="native_docx")
            remaining_cells -= sum(len(row) for row in rows)
            if truncated:
                warnings.append(f"Word table extraction reached the {MAX_TABLE_CELLS:,}-cell or per-table row/column limit.")
                break
        md = chunks.render()
        warnings.append("Headers, footers, images, floating objects, and complex layout may be omitted.")
    elif ext == ".pptx":
        deck = Presentation(io.BytesIO(content))
        pages = len(deck.slides)
        chunks = MarkdownChunks(f"# {title}", source_id)
        if pages > MAX_PPTX_SLIDES:
            warnings.append(f"Presentation truncated at {MAX_PPTX_SLIDES:,} slides.")
        shape_count = 0
        remaining_cells = MAX_TABLE_CELLS
        shapes_truncated = False
        for index, slide in enumerate(deck.slides, 1):
            if index > MAX_PPTX_SLIDES or shapes_truncated:
                break
            chunks.append(f"## Slide {index}", locator={"type": "pptx_slide_heading", "slide": index}, method="native_pptx")
            for shape_index, shape in enumerate(slide.shapes, 1):
                shape_count += 1
                if shape_count > MAX_PPTX_SHAPES:
                    shapes_truncated = True
                    break
                if getattr(shape, "has_text_frame", False) and shape.text.strip():
                    chunks.append(shape.text.strip(), locator={"type": "pptx_shape", "slide": index, "shape": shape_index}, method="native_pptx")
                if getattr(shape, "has_table", False):
                    rows, truncated = bounded_table_rows(([cell.text for cell in row.cells] for row in shape.table.rows), remaining_cells)
                    chunks.append(table_md(rows), locator={"type": "pptx_table", "slide": index, "shape": shape_index, "row_start": 1, "row_end": len(rows), "column_count": max((len(row) for row in rows), default=0)}, method="native_pptx")
                    remaining_cells -= sum(len(row) for row in rows)
                    if truncated or remaining_cells <= 0:
                        warnings.append(f"Presentation table extraction reached the {MAX_TABLE_CELLS:,}-cell or per-table row/column limit.")
                        shapes_truncated = True
                        break
        if shapes_truncated and shape_count > MAX_PPTX_SHAPES:
            warnings.append(f"Presentation shape extraction truncated at {MAX_PPTX_SHAPES:,} shapes.")
        md = chunks.render()
        warnings.append("Speaker notes, animations, charts, and visual relationships are not extracted.")
    else:  # XLSX
        chunks = MarkdownChunks(f"# {title}", source_id)
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        try:
            remaining_cells = MAX_TABLE_CELLS
            for sheet in book.worksheets:
                chunks.append(f"## Sheet: {sheet.title}", locator={"type": "xlsx_sheet_heading", "sheet": sheet.title}, method="native_xlsx")
                actual_rows = sheet.max_row or 0
                actual_columns = sheet.max_column or 0
                row_limit = min(actual_rows, MAX_TABLE_ROWS)
                column_limit = min(actual_columns, MAX_TABLE_COLUMNS)
                if actual_rows > MAX_TABLE_ROWS:
                    warnings.append(f"Sheet '{sheet.title}' row range capped at {MAX_TABLE_ROWS:,}.")
                if actual_columns > MAX_TABLE_COLUMNS:
                    warnings.append(f"Sheet '{sheet.title}' column range capped at {MAX_TABLE_COLUMNS:,}.")
                rows, truncated = bounded_table_rows(
                    sheet.iter_rows(min_row=1, max_row=row_limit, min_col=1, max_col=column_limit, values_only=True),
                    remaining_cells,
                ) if row_limit and column_limit and remaining_cells else ([], remaining_cells <= 0)
                remaining_cells -= sum(len(row) for row in rows)
                if truncated:
                    warnings.append(f"Sheet '{sheet.title}' truncated at the configured row, column or {MAX_TABLE_CELLS:,}-cell limit.")
                if rows:
                    chunks.append(table_md(rows), locator={"type": "xlsx_range", "sheet": sheet.title, "row_start": 1, "row_end": len(rows), "column_start": 1, "column_end": max((len(row) for row in rows), default=0)}, method="native_xlsx")
                if remaining_cells <= 0:
                    warnings.append(f"Workbook extraction stopped at the {MAX_TABLE_CELLS:,}-cell total limit.")
                    break
        finally:
            book.close()
        md = chunks.render()
        warnings.append("Cached formula values are used; charts, formatting, macros, and hidden-sheet intent may be omitted.")

    md = clean(md)
    if len(md) > MAX_EXTRACTED_CHARS:
        raise ValueError(f"Extracted output exceeds the {MAX_EXTRACTED_CHARS:,}-character safety limit; split the source into smaller files.")
    if not md:
        warnings.append("No text content was extracted.")
    route_by_extension = {
        ".txt": ("text_decode", "Text decoding"), ".md": ("text_decode", "Markdown pass-through"),
        ".markdown": ("text_decode", "Markdown pass-through"), ".csv": ("tabular_parse", "CSV table parsing"),
        ".json": ("structured_parse", "JSON formatting"), ".html": ("html_parse", "Visible HTML text extraction"),
        ".htm": ("html_parse", "Visible HTML text extraction"),
        ".docx": ("office_parse", "Word document parsing"), ".pptx": ("office_parse", "PowerPoint text and table extraction"),
        ".xlsx": ("office_parse", "Spreadsheet value extraction"),
    }
    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        route, route_label = ("local_ocr", "Image text extracted with local OCR") if image_ocr_used else ("image_metadata", "Image metadata only; OCR not used")
    elif ext == ".pdf":
        route, route_label = ("pdf_text_ocr", "PDF text with local OCR fallback") if ocr_pages else ("pdf_text", "PDF native text extraction")
    else:
        route, route_label = route_by_extension[ext]
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    estimated_tokens = (len(md) + 3) // 4
    if ext in {".txt", ".md", ".markdown"}:
        decision_reason = "The source is already text; direct decoding preserves its literal content without an OCR or model call."
    elif ext == ".csv":
        decision_reason = "A bounded CSV parser preserves row and column structure; semantic model processing is unnecessary for conversion."
    elif ext == ".json":
        decision_reason = "A JSON parser validates and formats the existing structure without changing its meaning."
    elif ext in {".html", ".htm"}:
        decision_reason = "Visible text extraction avoids executing or rendering uploaded HTML; scripts and layout are deliberately omitted."
    elif ext == ".pdf":
        if processing_mode == "native_only":
            decision_reason = "Native-text-only policy selected. Selectable page text is extracted where present; OCR is skipped on pages without selectable text."
        elif ocr_pages:
            decision_reason = f"Native PDF text was preferred; local OCR was used only where selectable text was absent and recovered {ocr_pages} page(s)."
        elif ocr_attempts:
            decision_reason = "Native PDF text was extracted where available; local OCR was attempted on scanned pages but did not recover readable text."
        elif _ocr_available():
            decision_reason = "Native PDF text was sufficient; local OCR was available but not invoked because no scanned pages needed it."
        else:
            decision_reason = "Native PDF text was extracted. Scanned pages remain unreadable because local OCR is not configured."
    elif ext in {".png", ".jpg", ".jpeg", ".webp"}:
        if processing_mode == "native_only":
            decision_reason = "Native-text-only policy selected. Image metadata was retained and OCR was intentionally skipped."
        elif image_ocr_used:
            decision_reason = "Local OCR was selected because the source is an image; no hosted vision model was called."
        elif not _ocr_available():
            decision_reason = "Image metadata was retained, but text OCR is unavailable because Tesseract is not configured on this host."
        else:
            decision_reason = "Local OCR was attempted but returned no text; the result retains image metadata and an extraction warning."
    elif ext == ".docx":
        decision_reason = "The native Word document structure was parsed to preserve headings, paragraphs and tables without rasterizing pages."
    elif ext == ".pptx":
        decision_reason = "The native PowerPoint structure was parsed to preserve slide order and text/table content without vision inference."
    else:
        decision_reason = "Cached worksheet values were read from the native workbook structure; formulas and visual formatting are not recalculated."
    alternatives = [{
        "route": "hosted_model",
        "status": "not_configured",
        "reason": "No hosted model provider is connected; no external call or provider charge was incurred.",
    }]
    if ext in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
        if processing_mode == "native_only":
            alternatives.insert(0, {"route": "local_ocr", "status": "skipped_by_policy", "reason": "The user selected native text only."})
        elif not _ocr_available():
            alternatives.insert(0, {"route": "local_ocr", "status": "unavailable", "reason": "Tesseract is not configured on this host."})
        elif ext == ".pdf" and not ocr_pages:
            alternatives.insert(0, {"route": "local_ocr", "status": "not_needed", "reason": "No scanned page without selectable text required OCR."})
    if "chunks" in locals() and isinstance(chunks, MarkdownChunks):
        evidence_blocks = chunks.evidence
    else:
        canonical_locator = json.dumps(evidence_locator, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        block_id = hashlib.sha256(f"{source_id}:{canonical_locator}".encode("utf-8")).hexdigest()[:24]
        evidence_blocks = [{
            "block_id": block_id,
            "source_id": source_id,
            "locator": evidence_locator,
            "markdown_range": {"start": 0, "end": len(md), "unit": "unicode_code_points", "end_exclusive": True},
            "content_sha256": hashlib.sha256(md.encode("utf-8")).hexdigest(),
            "extraction_method": evidence_method,
        }]
    evidence = {
        "schema_version": "1.0",
        "source_id": source_id,
        "source_sha256": source_id,
        "blocks": evidence_blocks,
    }
    return {
        "filename": name,
        "markdown": md,
        "evidence": evidence,
        "characters": len(md),
        "words": len(re.findall(r"\b[\w'-]+\b", md)),
        "pages": pages,
        "warnings": list(dict.fromkeys(warnings)),
        "format": ext.lstrip("."),
        "processing": {
            "route": route,
            "route_label": route_label,
            "mode": "local_deterministic",
            "decision": {
                "policy": processing_mode,
                "selected_route": route,
                "reason": decision_reason,
                "alternatives": alternatives,
            },
            "duration_ms": duration_ms,
            "external_model_calls": 0,
        },
        "context": {
            "input_bytes": len(content),
            "markdown_bytes": len(md.encode("utf-8")),
            "estimated_tokens": estimated_tokens,
            "token_estimation": "ceil(markdown characters / 4); approximate only, not a model tokenizer",
        },
    }
