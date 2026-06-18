"""ClauseLens FastAPI entrypoint.

A single long-lived process (D7): it exposes the ``/api`` surface and serves the
pre-built React ``dist`` with an SPA fallback so client-side routes resolve.
Phase 2 adds the analyses API + Stage-1 ingest pipeline (LangGraph spine).
"""
from __future__ import annotations

import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# The bundled PDF.js worker ships as an ES module (.mjs). Some platforms map .mjs
# to a non-JS mime, which makes strict browsers refuse to load the module worker
# (breaking the citation viewer). Pin it to a JavaScript type before any static
# file is served. (Phase 4 — citation viewer robustness.)
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")

from .config import settings
from .routes import analyses, health
from .store import get_job_store


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Touch the SQLite store so the DB + data/ dir exist before first request.
    get_job_store()
    yield


app = FastAPI(title="ClauseLens", version="0.1.0", lifespan=lifespan)

# API routes (registered before the SPA catch-all so /api never gets shadowed).
app.include_router(health.router)
app.include_router(analyses.router)


@app.get("/api")
def api_root() -> dict:
    """API descriptor + non-secret config view (handy during the demo)."""
    return {"app": "ClauseLens", "version": app.version, "config": settings.as_safe_dict()}


# ---- Static frontend (built dist) + SPA fallback ----------------------------
# Mounted last so it does not shadow /api routes. If the dist is missing (e.g.
# backend booted before `make build-frontend`), we serve a helpful placeholder.
_dist: Path = settings.frontend_dist
_index = _dist / "index.html"


if _dist.is_dir() and _index.is_file():
    # Serve hashed asset files directly.
    assets_dir = _dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        """Serve a real file when it exists, else index.html for client routing."""
        if full_path.startswith("api"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = _dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_index))

else:

    @app.get("/{full_path:path}")
    def no_dist(full_path: str):
        if full_path.startswith("api"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return JSONResponse(
            {
                "detail": "Frontend not built. Run `make build-frontend` (or `make demo`).",
                "expected_dist": str(_dist),
            },
            status_code=503,
        )
