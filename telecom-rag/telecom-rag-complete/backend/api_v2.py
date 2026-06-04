"""
api_v2.py — Steps 4 + 5 + 7
==============================
Updated FastAPI server using:
  - retriever_v2 (BM25 hybrid + Stage 0 exact match)
  - llm_v2 (structured HedEx panel + citation validator)
  - query_expansion (582 terms)

Drop into: C:\\Working\\Telecom RAG\\telecom-rag-complete\\backend\\

Start:
    $env:KMP_DUPLICATE_LIB_OK="TRUE"
    cd C:\\Working\\Telecom RAG\\telecom-rag-complete\\backend
    C:\\Users\\triaz\\miniconda3_New\\envs\\rag\\python.exe api_v2.py
"""

import asyncio
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

sys.path.insert(0, str(Path(__file__).parent))
from config import Config
from retriever_v2 import Retriever
from llm_v2 import build_3gpp_answer, build_hedex_answer, build_openai_answer
from query_expansion import expand_query, get_expansion_terms, count_terms

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telecom.api.v2")

cfg = Config()
app = FastAPI(
    title="Telecom Assistant :: AI RAG Agent v2",
    description="5G Telecom RAG — 3GPP + HedEx + OpenAI | BM25 Hybrid | Clause-Aware",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for parallel LLM calls
_executor = ThreadPoolExecutor(max_workers=3)

# ── Lazy-loaded retriever (initialized on first request) ──────────────────────
_retriever: Optional[Retriever] = None

def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        logger.info("Initializing Retriever v2...")
        _retriever = Retriever()
        logger.info("Retriever v2 ready")
    return _retriever


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    sources: List[str] = ["3gpp", "hedex", "openai"]  # Which sources to query
    debug: bool = False


class ChunkResult(BaseModel):
    text: str
    citation: str
    confidence: float
    rerank_score: float
    hybrid_score: float
    vector_score: float
    bm25_score: float
    stage: int
    parameter_name: str = ""
    mo_path: str = ""
    default_value: str = ""
    value_range: str = ""


class SourceAnswer(BaseModel):
    source: str                    # "3gpp" | "hedex" | "openai"
    answer: str
    confidence: float
    chunks_used: int
    expansion_terms_used: int = 0
    retrieved_chunks: List[ChunkResult] = []  # Only in debug mode


class QueryResponse(BaseModel):
    query: str
    expanded_query: str
    sources: List[SourceAnswer]
    total_latency_ms: float
    pipeline_trace: Dict[str, Any] = {}


# ─────────────────────────────────────────────────────────────────────────────
# CORE QUERY PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def run_3gpp_pipeline(query: str, debug: bool) -> SourceAnswer:
    """3GPP retrieval + generation (runs in thread)."""
    t0 = time.time()
    retriever = get_retriever()

    chunks = retriever.retrieve_3gpp(query)
    logger.info(f"3GPP: {len(chunks)} chunks retrieved in {time.time()-t0:.2f}s")

    answer, confidence = build_3gpp_answer(
        query=query,
        chunks=chunks,
        ollama_model=cfg.OLLAMA_MODEL,
        ollama_base_url=cfg.OLLAMA_BASE_URL,
    )

    result = SourceAnswer(
        source="3gpp",
        answer=answer,
        confidence=confidence,
        chunks_used=len(chunks),
        expansion_terms_used=len(get_expansion_terms(query)),
    )

    if debug:
        result.retrieved_chunks = [
            ChunkResult(
                text=c["text"][:300],
                citation=c["citation"],
                confidence=c["confidence"],
                rerank_score=c.get("rerank_score", 0),
                hybrid_score=c.get("hybrid_score", 0),
                vector_score=c.get("vector_score", 0),
                bm25_score=c.get("bm25_score", 0),
                stage=c.get("stage", 1),
                parameter_name=c.get("parameter_name", ""),
                mo_path=c.get("mo_path", ""),
                default_value=c.get("default_value", ""),
                value_range=c.get("value_range", ""),
            )
            for c in chunks
        ]

    return result


def run_hedex_pipeline(query: str, debug: bool) -> SourceAnswer:
    """HedEx retrieval + generation (runs in thread)."""
    t0 = time.time()
    retriever = get_retriever()

    chunks = retriever.retrieve_hedex(query)
    logger.info(f"HedEx: {len(chunks)} chunks retrieved in {time.time()-t0:.2f}s")

    answer, confidence = build_hedex_answer(
        query=query,
        chunks=chunks,
        ollama_model=cfg.OLLAMA_MODEL,
        ollama_base_url=cfg.OLLAMA_BASE_URL,
    )

    result = SourceAnswer(
        source="hedex",
        answer=answer,
        confidence=confidence,
        chunks_used=len(chunks),
        expansion_terms_used=len(get_expansion_terms(query)),
    )

    if debug:
        result.retrieved_chunks = [
            ChunkResult(
                text=c["text"][:300],
                citation=c["citation"],
                confidence=c["confidence"],
                rerank_score=c.get("rerank_score", 0),
                hybrid_score=c.get("hybrid_score", 0),
                vector_score=c.get("vector_score", 0),
                bm25_score=c.get("bm25_score", 0),
                stage=c.get("stage", 1),
                parameter_name=c.get("parameter_name", ""),
                mo_path=c.get("mo_path", ""),
                default_value=c.get("default_value", ""),
                value_range=c.get("value_range", ""),
            )
            for c in chunks
        ]

    return result


def run_openai_pipeline(
    query: str,
    chunks_3gpp: List[Dict],
    chunks_hedex: List[Dict],
) -> SourceAnswer:
    """OpenAI explanation panel (runs in thread)."""
    answer = build_openai_answer(
        query=query,
        chunks_3gpp=chunks_3gpp,
        chunks_hedex=chunks_hedex,
        api_key=cfg.OPENAI_API_KEY,
        model=cfg.OPENAI_MODEL,
    )
    return SourceAnswer(
        source="openai",
        answer=answer,
        confidence=100.0,  # OpenAI always returns something
        chunks_used=0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    retriever = get_retriever()
    stats = retriever.stats()
    return {
        "status": "ok",
        "version": "2.0.0",
        "model": cfg.OLLAMA_MODEL,
        "embed_model": cfg.EMBED_MODEL,
        "reranker": cfg.RERANKER_MODEL,
        "expansion_terms": count_terms(),
        "bm25_weight": float(os.getenv("BM25_WEIGHT", "0.35")),
        "vector_weight": float(os.getenv("VECTOR_WEIGHT", "0.65")),
        **stats,
    }


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    t_start = time.time()
    query = request.query.strip()
    expanded = expand_query(query)
    expansion_terms = get_expansion_terms(query)

    logger.info(f"Query: {query}")
    logger.info(f"Expansion: {len(expansion_terms)} terms added")

    retriever = get_retriever()
    source_answers: List[SourceAnswer] = []

    # Retrieve from both local sources first (needed for OpenAI grounding)
    chunks_3gpp, chunks_hedex = [], []
    loop = asyncio.get_event_loop()

    if "3gpp" in request.sources or "openai" in request.sources:
        chunks_3gpp = await loop.run_in_executor(
            _executor, retriever.retrieve_3gpp, query
        )

    if "hedex" in request.sources or "openai" in request.sources:
        chunks_hedex = await loop.run_in_executor(
            _executor, retriever.retrieve_hedex, query
        )

    # Build 3GPP answer
    if "3gpp" in request.sources:
        ans_3gpp = await loop.run_in_executor(
            _executor,
            lambda: build_3gpp_answer(query, chunks_3gpp, cfg.OLLAMA_MODEL, cfg.OLLAMA_BASE_URL)
        )
        source_answers.append(SourceAnswer(
            source="3gpp",
            answer=ans_3gpp[0],
            confidence=ans_3gpp[1],
            chunks_used=len(chunks_3gpp),
            expansion_terms_used=len(expansion_terms),
            retrieved_chunks=[
                ChunkResult(
                    text=c["text"][:300],
                    citation=c["citation"],
                    confidence=c["confidence"],
                    rerank_score=c.get("rerank_score", 0),
                    hybrid_score=c.get("hybrid_score", 0),
                    vector_score=c.get("vector_score", 0),
                    bm25_score=c.get("bm25_score", 0),
                    stage=c.get("stage", 1),
                    parameter_name=c.get("parameter_name", ""),
                    mo_path=c.get("mo_path", ""),
                    default_value=c.get("default_value", ""),
                    value_range=c.get("value_range", ""),
                )
                for c in chunks_3gpp
            ] if request.debug else [],
        ))

    # Build HedEx answer
    if "hedex" in request.sources:
        ans_hedex = await loop.run_in_executor(
            _executor,
            lambda: build_hedex_answer(query, chunks_hedex, cfg.OLLAMA_MODEL, cfg.OLLAMA_BASE_URL)
        )
        source_answers.append(SourceAnswer(
            source="hedex",
            answer=ans_hedex[0],
            confidence=ans_hedex[1],
            chunks_used=len(chunks_hedex),
            expansion_terms_used=len(expansion_terms),
            retrieved_chunks=[
                ChunkResult(
                    text=c["text"][:300],
                    citation=c["citation"],
                    confidence=c["confidence"],
                    rerank_score=c.get("rerank_score", 0),
                    hybrid_score=c.get("hybrid_score", 0),
                    vector_score=c.get("vector_score", 0),
                    bm25_score=c.get("bm25_score", 0),
                    stage=c.get("stage", 1),
                    parameter_name=c.get("parameter_name", ""),
                    mo_path=c.get("mo_path", ""),
                    default_value=c.get("default_value", ""),
                    value_range=c.get("value_range", ""),
                )
                for c in chunks_hedex
            ] if request.debug else [],
        ))

    # Build OpenAI answer (uses both evidence sets for grounding)
    if "openai" in request.sources:
        ans_openai = await loop.run_in_executor(
            _executor,
            lambda: build_openai_answer(query, chunks_3gpp, chunks_hedex, cfg.OPENAI_API_KEY, cfg.OPENAI_MODEL)
        )
        source_answers.append(SourceAnswer(
            source="openai",
            answer=ans_openai,
            confidence=100.0,
            chunks_used=0,
        ))

    total_ms = (time.time() - t_start) * 1000

    return QueryResponse(
        query=query,
        expanded_query=expanded[:200] + "..." if len(expanded) > 200 else expanded,
        sources=source_answers,
        total_latency_ms=round(total_ms, 1),
        pipeline_trace={
            "3gpp_chunks": len(chunks_3gpp),
            "hedex_chunks": len(chunks_hedex),
            "expansion_terms": len(expansion_terms),
            "model": cfg.OLLAMA_MODEL,
            "bm25_weight": float(os.getenv("BM25_WEIGHT", "0.35")),
        },
    )


@app.get("/stats")
async def stats():
    retriever = get_retriever()
    return {
        **retriever.stats(),
        "expansion_term_count": count_terms(),
        "ollama_model": cfg.OLLAMA_MODEL,
        "embed_model": cfg.EMBED_MODEL,
        "reranker_model": cfg.RERANKER_MODEL,
        "thresholds": {
            "3gpp": float(os.getenv("CONF_THRESHOLD_3GPP", "0.30")),
            "hedex": float(os.getenv("CONF_THRESHOLD_HEDEX", "0.30")),
        },
        "retrieval": {
            "top_k": int(os.getenv("RETRIEVAL_TOP_K", "30")),
            "rerank_top_n": int(os.getenv("RERANK_TOP_N", "8")),
            "bm25_weight": float(os.getenv("BM25_WEIGHT", "0.35")),
            "vector_weight": float(os.getenv("VECTOR_WEIGHT", "0.65")),
        },
    }


@app.get("/app", response_class=HTMLResponse)
async def serve_ui():
    """Serve the frontend from the existing frontend/index.html."""
    frontend_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if frontend_path.exists():
        return HTMLResponse(content=frontend_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Frontend not found. Check frontend/index.html</h1>", status_code=404)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("="*60)
    logger.info("Telecom Assistant :: AI RAG Agent v2")
    logger.info(f"Model: {cfg.OLLAMA_MODEL}")
    logger.info(f"BM25 hybrid: {os.getenv('BM25_WEIGHT', '0.35')} BM25 / {os.getenv('VECTOR_WEIGHT', '0.65')} Vector")
    logger.info(f"Expansion terms: {count_terms()}")
    logger.info("="*60)

    uvicorn.run(
        app,
        host=cfg.API_HOST,
        port=cfg.API_PORT,
        log_level="info",
    )
