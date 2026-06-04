"""
api.py — FastAPI server
Returns all 3 source answers for every query.
"""

import sys, os
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
sys.path.insert(0, str(Path(__file__).parent))

from config import cfg
from orchestrator import get_orchestrator

try:
    import chromadb
    _chroma_available = True
except ImportError:
    _chroma_available = False

app = FastAPI(title="TelecomRAG API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ── Models
class QueryRequest(BaseModel):
    query: str

class HopInfo(BaseModel):
    hop:    int
    label:  str
    cls:    str
    detail: str

class SourceAnswer(BaseModel):
    source:     str        # '3gpp' | 'hedex' | 'openai'
    answer:     str
    score:      float
    has_answer: bool

class QueryResponse(BaseModel):
    query:          str
    answers:        List[SourceAnswer]   # always 3 items
    pipeline_trace: List[HopInfo]
    error:          Optional[str] = None


# ── Endpoints

@app.get("/", response_class=HTMLResponse)
async def root():
    return """<html><body style="font-family:monospace;padding:2rem;background:#0d1117;color:#c9d1d9">
    <h2>TelecomRAG API v2</h2>
    <p>POST /query — all 3 sources every time</p>
    <p><a href="/docs" style="color:#58a6ff">Swagger UI →</a></p>
    <p><a href="/app" style="color:#58a6ff">Chat UI →</a></p>
    </body></html>"""


@app.get("/health")
async def health():
    checks = {"api": "ok", "ollama": "unknown", "chroma": "unknown"}
    try:
        import ollama
        models     = ollama.list()
        # ollama.list() returns a ListResponse object — iterate models attribute
        model_list = models.models if hasattr(models, 'models') else models.get("models", [])
        names      = []
        for m in model_list:
            # model objects may be dicts or have .model / .name attributes
            if isinstance(m, dict):
                names.append(m.get("name", m.get("model", "")))
            else:
                names.append(getattr(m, "name", getattr(m, "model", "")))
        checks["ollama"] = "ok" if any(cfg.OLLAMA_MODEL in n for n in names) else f"model '{cfg.OLLAMA_MODEL}' not found — available: {names[:4]}"
    except Exception as e:
        checks["ollama"] = f"error: {e}"

    if _chroma_available:
        try:
            cfg.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(cfg.CHROMA_PERSIST_DIR))
            cols   = [c.name for c in client.list_collections()]
            checks["chroma"]            = "ok"
            checks["collections_found"] = cols
        except Exception as e:
            checks["chroma"] = f"error: {e}"
    return checks


@app.get("/collections")
async def collections():
    if not _chroma_available:
        raise HTTPException(500, "chromadb not installed")
    try:
        cfg.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(cfg.CHROMA_PERSIST_DIR))
        result = {}
        for name in [cfg.COLLECTION_3GPP, cfg.COLLECTION_HEDEX]:
            try:
                col = client.get_collection(name)
                result[name] = {"chunks": col.count(), "status": "ready"}
            except Exception:
                result[name] = {"chunks": 0, "status": "not_ingested"}
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")

    logger.info(f"Query: {req.query[:80]}")

    try:
        orch   = get_orchestrator()
        result = orch.query(req.query)

        answers = [
            SourceAnswer(
                source     = r.source,
                answer     = r.answer,
                score      = round(r.score, 3),
                has_answer = r.has_answer,
            )
            for r in result.results
        ]

        return QueryResponse(
            query          = result.query,
            answers        = answers,
            pipeline_trace = [HopInfo(**h) for h in result.pipeline_trace],
        )

    except Exception as e:
        logger.exception(f"Query failed: {e}")
        raise HTTPException(500, str(e))


@app.post("/ingest")
async def ingest_endpoint(source: str = "both", reset: bool = False):
    try:
        from ingestor import ingest_directory
        results = {}
        if source in ("3gpp", "both"):
            results["3gpp"]  = ingest_directory(cfg.DATA_DIR_3GPP,  cfg.COLLECTION_3GPP,  reset=reset)
        if source in ("hedex", "both"):
            results["hedex"] = ingest_directory(cfg.DATA_DIR_HEDEX, cfg.COLLECTION_HEDEX, reset=reset)
        return {"status": "done", "chunks_ingested": results}
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    uvicorn.run("api:app", host=cfg.API_HOST, port=cfg.API_PORT, reload=True, log_level="info")
