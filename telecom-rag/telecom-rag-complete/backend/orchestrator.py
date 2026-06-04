"""
orchestrator.py — Production parallel orchestrator
All 3 sources every query.
Evidence from local sources passed to OpenAI.
Confidence scoring. Fail-safe mode.
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List, Optional

from loguru import logger
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config import cfg
from retriever import (
    retrieve, best_score, RetrievedChunk,
    get_source_priority,
    extract_allowed_citations, validate_citations,
    build_evidence_summary,
)
from llm import build_3gpp_prompt, build_hedex_prompt, generate_local, generate_openai


# ══════════════════════════════════════════════════════════
#  CONFIDENCE SCORING
# ══════════════════════════════════════════════════════════

def score_to_confidence(score: float) -> str:
    if score >= 0.80: return "High"
    if score >= 0.65: return "Medium"
    if score >= 0.45: return "Low"
    return "Not found"


# ══════════════════════════════════════════════════════════
#  DATA CLASSES
# ══════════════════════════════════════════════════════════

@dataclass
class SourceResult:
    source:      str
    answer:      str
    score:       float
    confidence:  str
    chunks_used: List[RetrievedChunk] = field(default_factory=list)
    error:       str = ""

    @property
    def has_answer(self) -> bool:
        return bool(self.answer.strip()) and self.confidence != "Not found"


@dataclass
class OrchestratorResult:
    query:    str
    results:  List[SourceResult]   # always 3: 3gpp, hedex, openai
    priority: str

    def get(self, source: str) -> Optional[SourceResult]:
        return next((r for r in self.results if r.source == source), None)

    @property
    def pipeline_trace(self) -> List[dict]:
        trace = []
        for i, r in enumerate(self.results):
            if r.source == "openai":
                cls    = "fb" if r.has_answer else "miss"
                detail = "gpt-4o — explanation with confirmed evidence" if r.has_answer else r.error
            else:
                cls    = "hit" if r.has_answer else "miss"
                files  = ', '.join(
                    set(c.source_file for c in r.chunks_used[:2])
                ) if r.chunks_used else ""
                match_types = ', '.join(
                    set(c.match_type for c in r.chunks_used)
                ) if r.chunks_used else ""
                detail = (
                    f"score {r.score:.2f} | {r.confidence} | "
                    f"match={match_types} | {files}"
                    if files else r.error or f"score {r.score:.2f}"
                )
            trace.append({
                "hop":    i + 1,
                "label":  f"{r.source.upper()} — {r.confidence}",
                "cls":    cls,
                "detail": detail,
            })
        return trace


# ══════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ══════════════════════════════════════════════════════════

class Orchestrator:

    def query(self, user_query: str) -> OrchestratorResult:
        priority = get_source_priority(user_query)
        logger.info(f"Query priority: {priority}")

        # ── Local sources
        r_3gpp  = self._query_local(
            user_query, "3gpp",  cfg.COLLECTION_3GPP,  cfg.CONF_THRESHOLD_3GPP)
        r_hedex = self._query_local(
            user_query, "hedex", cfg.COLLECTION_HEDEX, cfg.CONF_THRESHOLD_HEDEX)

        # ── Build evidence summary from confirmed local findings
        # Pass to OpenAI so it can reference real results without inventing
        evidence = build_evidence_summary(
            r_3gpp.chunks_used  if r_3gpp.has_answer  else [],
            r_hedex.chunks_used if r_hedex.has_answer else [],
        )

        # ── OpenAI — always, with evidence context
        r_openai = self._query_openai(user_query, evidence)

        return OrchestratorResult(
            query    = user_query,
            results  = [r_3gpp, r_hedex, r_openai],
            priority = priority,
        )


    def _query_local(
        self,
        query:           str,
        source:          str,
        collection_name: str,
        threshold:       float,
    ) -> SourceResult:
        try:
            chunks = retrieve(query, collection_name)
            score  = best_score(chunks)
            conf   = score_to_confidence(score)

            logger.info(f"{source.upper()}: score={score:.3f} confidence={conf}")

            if score < threshold:
                return SourceResult(
                    source      = source,
                    answer      = "",
                    score       = score,
                    confidence  = "Not found",
                    chunks_used = chunks,
                    error       = f"Score {score:.2f} below threshold — not found in retrieved docs",
                )

            # Build source-specific prompt
            if source == "hedex":
                prompt = build_hedex_prompt(query, chunks)
            else:
                prompt = build_3gpp_prompt(query, chunks)

            answer = generate_local(prompt)

            # Citation validation — strip hallucinated refs
            allowed = extract_allowed_citations(chunks)
            answer  = validate_citations(answer, allowed)

            return SourceResult(
                source      = source,
                answer      = answer,
                score       = score,
                confidence  = conf,
                chunks_used = chunks,
            )

        except Exception as e:
            logger.error(f"{source} error: {e}")
            return SourceResult(
                source     = source,
                answer     = "",
                score      = 0.0,
                confidence = "Error",
                error      = str(e),
            )


    def _query_openai(self, query: str, evidence: str) -> SourceResult:
        try:
            answer = generate_openai(query, evidence_summary=evidence)
            return SourceResult(
                source     = "openai",
                answer     = answer,
                score      = 0.5,
                confidence = "General Knowledge",
            )
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return SourceResult(
                source     = "openai",
                answer     = f"OpenAI unavailable: {e}",
                score      = 0.0,
                confidence = "Error",
                error      = str(e),
            )


_orchestrator: Optional[Orchestrator] = None

def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
