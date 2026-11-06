# Optional local tools — approval required

The core app works without either tool. No installer, model weight, or runtime has been downloaded.

## OCR: Tesseract

- Purpose: read text from scanned PDF pages and image files.
- Candidate: Tesseract OCR 5.5.x for Windows, using the installer referenced by the Tesseract documentation (UB Mannheim builds).
- Integration: the backend calls `tesseract.exe` directly. No Python wrapper or extra Python package is needed.
- Tradeoff: OCR is slower and less reliable on skewed, low-resolution, handwritten, or complex-layout pages. The app will retain native extraction and report OCR warnings.
- Approval check: confirm the exact installer version, download size, language data, license, and installation path before downloading.

## Local summaries: llama.cpp + Qwen3.5

- Purpose: generate a short semantic summary after deterministic extraction.
- Candidate runtime: `llama.cpp` Windows x64 CPU build, exposing its local OpenAI-compatible HTTP endpoint.
- Candidate model: Qwen3.5 0.8B Q4_K_M GGUF; the model card lists approximately 505 MB for the quantized weights.
- Integration: the FastAPI app can call the local endpoint on `127.0.0.1`; this does not require a Python ML framework. The model is not part of the extraction path.
- Tradeoff: a 0.8B model may produce shallow or inaccurate summaries on dense reports. The two-core CPU may also make long documents slow. It must pass factuality and latency checks before the UI enables summaries.
- Approval check: confirm the exact llama.cpp release asset, model revision, file sizes, license, RAM requirements, and expected latency before downloading.

## Why Cactus Needle is not the summary model

Cactus Needle targets function calling and structured tool arguments. It is not selected for document summarization. Its separate JAX setup and model download would add another runtime without solving the current summary task.

## Approval question

Choose one path before any download:

1. Tesseract OCR only.
2. llama.cpp + Qwen3.5 summaries only.
3. Both optional capabilities.
4. Neither; keep the current deterministic local workflow.
