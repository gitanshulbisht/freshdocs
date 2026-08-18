"""FreshDocs FastAPI app: /ask, /sources, /status + static UI."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .pipeline import Pipeline, load_registry
from .rag import Rag, RagError
from .schemas import Answer

load_dotenv()

DATA_DIR = Path(os.environ.get("FRESHDOCS_DATA_DIR", "data")).resolve()
REGISTRY_PATH = Path("collectors/collectors.json")
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="FreshDocs", version="0.1.0")

try:
    rag = Rag(data_dir=DATA_DIR)
except RagError:
    rag = None

pipeline = Pipeline(data_dir=DATA_DIR, rag=rag)
registry = load_registry(REGISTRY_PATH)


class AskRequest(BaseModel):
    question: str
    sources: list[str] | None = None  # source keys, e.g. ["docker", "kubernetes"]


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/sources")
async def sources():
    return [s.model_dump() for s in registry.sources]


@app.post("/api/ask", response_model=Answer)
async def ask(request: AskRequest) -> Answer:
    if rag is None:
        return Answer(answer="Server is not configured (LLM provider API key missing).", citations=[])
    return rag.answer(request.question, sources=request.sources)


@app.get("/api/status")
async def status():
    return pipeline.status()


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
