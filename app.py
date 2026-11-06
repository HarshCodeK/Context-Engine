from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from context_studio.api import app

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

if DIST.is_dir():
    app.mount("/studio-assets", StaticFiles(directory=DIST), name="studio-assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def index():
        return HTMLResponse(
            "<main><h1>Context Studio API is running</h1>"
            "<p>Build the frontend with <code>cd frontend; npm run build</code>.</p></main>"
        )
