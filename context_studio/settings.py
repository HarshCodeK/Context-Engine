from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.getenv("CONTEXT_STUDIO_DB", str(ROOT / "data" / "context_studio.sqlite3"))).expanduser()
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = ROOT / DATABASE_PATH


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


MAX_BYTES = _positive_int_env("MAX_FILE_BYTES", 20 * 1024 * 1024)
MAX_FILES = _positive_int_env("MAX_BATCH_FILES", 12)
MAX_BATCH_BYTES = _positive_int_env("MAX_BATCH_BYTES", 64 * 1024 * 1024)
MAX_PAGES = _positive_int_env("MAX_PDF_PAGES", 100)
MAX_IMAGE_PIXELS = _positive_int_env("MAX_IMAGE_PIXELS", 25_000_000)
MAX_OCR_SECONDS = _positive_int_env("OCR_TIMEOUT_SECONDS", 12)
MAX_OCR_TOTAL_SECONDS = _positive_int_env("OCR_TOTAL_SECONDS", 60)
MAX_OCR_PAGES_PER_FILE = _positive_int_env("OCR_PAGES_PER_FILE", 20)
RATE_LIMIT = _positive_int_env("UPLOADS_PER_MINUTE", 10)
MAX_TABLE_ROWS = _positive_int_env("MAX_TABLE_ROWS", 2000)
MAX_TABLE_COLUMNS = _positive_int_env("MAX_TABLE_COLUMNS", 200)
MAX_TABLE_CELLS = _positive_int_env("MAX_TABLE_CELLS", 100_000)
MAX_PPTX_SLIDES = _positive_int_env("MAX_PPTX_SLIDES", 200)
MAX_PPTX_SHAPES = _positive_int_env("MAX_PPTX_SHAPES", 20_000)
MAX_DOCX_PARAGRAPHS = _positive_int_env("MAX_DOCX_PARAGRAPHS", 20_000)
MAX_EXTRACTED_CHARS = _positive_int_env("MAX_EXTRACTED_CHARS", 2_000_000)
MAX_SESSION_FILES = _positive_int_env("MAX_SESSION_FILES", 24)
MAX_SESSION_ERRORS = _positive_int_env("MAX_SESSION_ERRORS", 24)
MAX_SESSION_BYTES = _positive_int_env("MAX_SESSION_BYTES", 128 * 1024 * 1024)
MAX_CONTEXT_PACK_CHARS = _positive_int_env("MAX_CONTEXT_PACK_CHARS", 2_000_000)
MAX_CONTEXT_RULES = _positive_int_env("MAX_CONTEXT_RULES", 200)
MAX_TRACKED_CLIENTS = 2048

SUPPORTED = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm",
    ".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg", ".webp",
}
OFFICE_MARKERS = {
    ".docx": "word/document.xml",
    ".pptx": "ppt/presentation.xml",
    ".xlsx": "xl/workbook.xml",
}
