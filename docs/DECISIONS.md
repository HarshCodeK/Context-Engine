# Engineering decisions

## Keep the first release local and deterministic

Document extraction must work without a model server, network access, API key, or hosted storage. Native parsers are predictable and retain structure that a model might paraphrase or omit. Semantic summarization is a separate optional stage and must never replace the source extraction.

## Keep dependencies explicit and isolated

The development workstation's project environment was recreated with access to its pre-existing system Python packages, so its full `pip list` includes many unrelated tools. That list is not the project's dependency manifest and must not be copied into requirements files. A fresh clone creates an isolated `.venv` and installs only the pinned application dependencies in `requirements.txt`. `requirements-dev.txt` adds `httpx` for FastAPI's test client. The frontend is independently declared in `frontend/package.json` and exactly resolved by `frontend/package-lock.json`.

The application imports FastAPI, Pydantic, Uvicorn, python-multipart, PyMuPDF 1.x, python-docx, python-pptx, openpyxl, and Pillow. It does not import `pymupdf4llm`, `pymupdf-layout`, `onnxruntime`, `networkx`, `numpy`, `pytesseract`, or an ML framework. The unrelated `httpx2` package is not required; the development manifest correctly uses `httpx`.

The setup script installs dependencies only when explicitly run with `-InstallDependencies`. It installs only the declared Python requirements and the npm lockfile. No installation was run as part of this dependency audit.

## OCR is an optional system executable

The application invokes the Tesseract command-line program directly with a timeout and page/pixel limits. It does not need a Python OCR wrapper. Without Tesseract, native PDF text and Office extraction continue to work and scanned content is reported honestly.

Candidate: Tesseract 5.5.x using the Windows installer maintained by UB Mannheim. Tesseract's own documentation notes that current Windows installers are third-party builds. Do not download or install it without user approval.

## Do not use Cactus Needle as the summarizer

Cactus Needle is documented as a function-calling model for tool selection and structured argument generation. Its Windows setup also creates a separate environment, installs JAX CPU dependencies, and downloads model weights. That adds a second runtime while solving the wrong task. It is not selected for document summarization.

Candidate for an optional local summary stage: `llama.cpp` Windows x64 CPU runtime with a quantized Qwen3.5 0.8B chat model (Q4_K_M model card reports about 505 MB). The current machine has about 7.8 GB RAM and an Intel i3-10110U with 2 cores / 4 threads. This candidate must be tested for factuality, latency, and long-document behavior before enabling it. No runtime or model weights have been downloaded.

References:

- Cactus Needle: https://github.com/cactus-compute/needle
- Tesseract Windows guidance: https://tesseract-ocr.github.io/tessdoc/Downloads
- llama.cpp releases: https://github.com/ggml-org/llama.cpp/releases
- Qwen3.5 0.8B Q4_K_M model card: https://developer.arm.com/ai/models/hugging-face/Arm/qwen3-5-0-8b-q4-k-m-llamacpp-vivo-x300/qwen3.5-0.8b-q4_k_m-gguf

## Use the existing frontend foundation

The frontend remains React + TypeScript + Vite with Tailwind CSS v4 and the generated shadcn/ui components. The UI uses the existing Base UI primitives, Tabler icons, Geist fonts, and CSS transitions. Unused `motion`, `@phosphor-icons/react`, and `sonner` packages were removed. The notification surface uses the shadcn Alert component because Sonner injects a runtime style element that conflicts with the strict local Content Security Policy.

The interface has no left sidebar. Its primary path is upload → source queue → Markdown review → context pack. Context rules are available as a secondary panel. Desktop uses a two-column workbench; narrow screens stack the same content vertically. Native select and progress elements are used where a popup-positioning primitive would require inline styles, keeping the strict Content Security Policy intact.

## Keep the backend small

FastAPI, SQLite, standard-library utilities, and the existing format parsers are enough for the current scope. Do not add Redis, Celery, a hosted database, a vector database, a framework for agents, or a separate orchestration service without measured need.

## Keep provenance visible

The source SHA-256, block locators, Markdown ranges, extraction method, route decision, and warnings travel with each successful extraction. User edits are tracked in the browser session and clearly distinguished from original source evidence.

## Treat agent context as a separate contract

The agent endpoint returns only saved, explicitly authored rules. It does not silently include uploaded documents or browser-session content. The endpoint is read-only and must remain loopback-only because the local rule store has no authentication or tenant isolation.
