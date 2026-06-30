from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.agents.master.agent import MasterAgent
from backend.app.core.cache import CacheStore
from backend.app.schemas import AnalysisResponse, HealthResponse


cache = CacheStore()
master_agent = MasterAgent(cache=cache)

app = FastAPI(
    title="Multi-Agent Document Processing PoC",
    version="1.0.0",
    description="Generalized master-agent/sub-agent system for enterprise document analysis.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="multi-agent-document-processing", cache_backend=cache.backend)


@app.get("/api/cache/stats")
async def cache_stats() -> dict:
    return cache.stats()


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze(request: Request) -> AnalysisResponse:
    try:
        text = ""
        file_bytes = None
        filename = None
        content_type = None
        request_content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in request_content_type:
            form = await request.form()
            text = str(form.get("text") or "")
            uploaded = form.get("file")
            if uploaded is not None and getattr(uploaded, "filename", ""):
                file_bytes = await uploaded.read()
                filename = uploaded.filename
                content_type = uploaded.content_type
        elif "application/json" in request_content_type:
            payload = await request.json()
            text = str(payload.get("text") or "")
        else:
            text = (await request.body()).decode("utf-8", errors="ignore")

        return master_agent.analyze(text=text, file_bytes=file_bytes, filename=filename, content_type=content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
samples_dir = Path(__file__).resolve().parents[2] / "samples"
if samples_dir.exists():
    app.mount("/samples", StaticFiles(directory=samples_dir), name="samples")

if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")

    @app.get("/styles.css", include_in_schema=False)
    async def styles() -> FileResponse:
        return FileResponse(frontend_dir / "styles.css")

    @app.get("/app.js", include_in_schema=False)
    async def frontend_app() -> FileResponse:
        return FileResponse(frontend_dir / "app.js")
