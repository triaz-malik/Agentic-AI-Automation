"""
retriever.py — Production hybrid retrieval

Filtering policy:
  Exact metadata match  → always pass, bypass all score thresholds
  Non-exact matches     → source-aware floor + dynamic bottom-30% discard
"""

from __future__ import annotations
import os, re, math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from sentence_transformers import CrossEncoder
from loguru import logger

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import cfg


# ══════════════════════════════════════════════════════════
#  DATA CLASS
# ══════════════════════════════════════════════════════════

@dataclass
class RetrievedChunk:
    text:           str
    source_file:    str
    chunk_idx:      int
    embed_distance: float
    rerank_score:   float
    metadata:       Dict[str, Any] = field(default_factory=dict)
    match_type:     str = "vector"  # exact | exact_contains | vector

    @property
    def normalised_score(self) -> float:
        return 1 / (1 + math.exp(-self.rerank_score * 0.6))

    @property
    def spec_number(self)    -> str: return self.metadata.get("spec_number",    "")
    @property
    def section_number(self) -> str: return self.metadata.get("section_number", "")
    @property
    def parameter_name(self) -> str: return self.metadata.get("parameter_name", "")
    @property
    def mo_path(self)        -> str: return self.metadata.get("mo_path",        "")
    @property
    def chunk_type(self)     -> str: return self.metadata.get("chunk_type",     "body")
    @property
    def is_exact(self)       -> bool: return self.match_type in ("exact", "exact_contains")


# ══════════════════════════════════════════════════════════
#  SCORE FLOORS — per source, raw CrossEncoder logits
#  Exact metadata matches bypass these entirely
# ══════════════════════════════════════════════════════════

SCORE_FLOOR: Dict[str, float] = {
    "3gpp":    -3.0,   # formal spec language → lower floor
    "hedex":   -2.0,   # keyword-dense tables → tighter floor
    "default": -2.5,
}
DYNAMIC_DISCARD_PERCENTILE = 30   # discard bottom 30% of non-exact candidates


def _compute_effective_floor(
    raw_scores: List[float],
    exact_mask: List[bool],
    source:     str,
) -> float:
    """
    Compute effective score floor for non-exact chunks only.
    Uses the HIGHER (stricter) of:
      - absolute source-aware floor
      - dynamic bottom-30th-percentile floor
    Exact match chunks are excluded from this calculation and bypass it entirely.
    """
    abs_floor = SCORE_FLOOR.get(source, SCORE_FLOOR["default"])

    non_exact = [s for s, ex in zip(raw_scores, exact_mask) if not ex]
    if not non_exact:
        return abs_floor

    sorted_s      = sorted(non_exact)
    idx           = max(0, int(len(sorted_s) * DYNAMIC_DISCARD_PERCENTILE / 100) - 1)
    dynamic_floor = sorted_s[idx]

    effective = max(abs_floor, dynamic_floor)
    logger.debug(
        f"Floor [{source}]: abs={abs_floor:.2f} "
        f"dynamic={dynamic_floor:.2f} effective={effective:.2f}"
    )
    return effective


# ══════════════════════════════════════════════════════════
#  TELECOM QUERY EXPANSION
# ══════════════════════════════════════════════════════════

TELCO_EXPANSION = {
    "vonr":        ["ims","5qi 1","rlc am","pdcp discard","rrc reestablishment",
                    "srvcc","epsfb","voice bearer","qci 1","gbr","vonr switch",
                    "VonrSwitch","CallDropRate","VonrAirTimeoutEpsfbTimer"],
    "call drop":   ["rlf","radio link failure","t310","n310","reestablishment",
                    "rrc release","bearer release","CallDropRate","N.CallDrop"],
    "handover":    ["a3","a4","a5","ttt","time to trigger","hysteresis",
                    "ho preparation","ho execution","A3Offset","HandoverSuccessRate"],
    "endc":        ["en-dc","nsa","scg","sgnb","x2","dual connectivity",
                    "secondary node","isEndcAllowed","EnDcSetupSucc"],
    "beamforming": ["csi-rs","ssb","bfr","cri","beam failure recovery",
                    "numOfBeams","analogBeamNum","SMART_BEAM_MGT"],
    "pdcp":        ["sdu discard","rohc","header compression","sn reorder",
                    "PdcpSduDiscardTimer","DrxConfig"],
    "rlf":         ["t310","n310","n311","out of sync","in sync",
                    "reestablishment","radio link failure","RlfCount"],
    "prb":         ["physical resource block","utilization","cqi","mcs","tbs",
                    "PrbUtilDl","PrbUtilUl"],
    "qos":         ["5qi","qci","gbr","ambr","gfbr","mfbr",
                    "bearer binding","QosFlow","QciAlgoSwitch"],
    "paging":      ["drx","paging cycle","nb","subframe","imsi",
                    "discontinuous reception","PagingSuccessRate"],
    "drx":         ["on duration timer","inactivity timer","drx cycle",
                    "DrxOnDurationTimer","DrxInactTimer","DrxConfig"],
    "kpi":         ["counter","measurement","performance","pm","statistics",
                    "success rate","attempt","failure","N.VoNR","N.HO"],
    "srvcc":       ["single radio","voice continuity","ps handover",
                    "ims centralized","MOBILITY_TO_EUTRAN_SW"],
}

SOURCE_PRIORITY_KEYWORDS = {
    "hedex_first": {"parameter","param","hedex","mo path","managed object",
                    "default value","configuration","feature","switch",
                    "nrcell","algo switch","gnb","option of"},
    "3gpp_first":  {"ts ","3gpp","clause","section","standard","specification",
                    "protocol","procedure","timer definition","spec"},
}

def get_source_priority(query: str) -> str:
    q = query.lower()
    h = sum(1 for kw in SOURCE_PRIORITY_KEYWORDS["hedex_first"] if kw in q)
    g = sum(1 for kw in SOURCE_PRIORITY_KEYWORDS["3gpp_first"]  if kw in q)
    if h > g: return "hedex"
    if g > h: return "3gpp"
    return "both"

def expand_query(query: str, source: str) -> str:
    q_lower = query.lower()
    extras  = []
    for keyword, expansions in TELCO_EXPANSION.items():
        kw_words    = set(keyword.split())
        query_words = set(q_lower.split())
        if len(kw_words & query_words) >= min(1, len(kw_words)):
            extras.extend(expansions)
    if extras:
        return f"{query} {' '.join(set(extras))}"
    return query


# ══════════════════════════════════════════════════════════
#  SINGLETONS
# ══════════════════════════════════════════════════════════

_chroma_client: Optional[chromadb.PersistentClient]            = None
_embed_fn:      Optional[SentenceTransformerEmbeddingFunction] = None
_reranker:      Optional[CrossEncoder]                         = None

def _get_client():
    global _chroma_client
    if _chroma_client is None:
        cfg.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(cfg.CHROMA_PERSIST_DIR))
        logger.info(f"ChromaDB → {cfg.CHROMA_PERSIST_DIR}")
    return _chroma_client

def _get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = SentenceTransformerEmbeddingFunction(
            model_name=cfg.EMBED_MODEL, device="cuda", normalize_embeddings=True)
        logger.info(f"Embedder: {cfg.EMBED_MODEL}")
    return _embed_fn

def _get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(cfg.RERANKER_MODEL, device="cuda", max_length=512)
        logger.info(f"Reranker: {cfg.RERANKER_MODEL}")
    return _reranker


# ══════════════════════════════════════════════════════════
#  STAGE 0 — EXACT METADATA MATCH
#  Searches parameter_name, mo_path, section_number, spec_number
#  These chunks always pass through — bypass reranker threshold
# ══════════════════════════════════════════════════════════

def exact_match_search(query: str, collection) -> List[Dict]:
    results = []
    seen    = set()
    q       = query.strip()

    field_scores = [
        ("parameter_name", "$eq",       10.0),
        ("parameter_name", "$contains",  9.0),
        ("mo_path",        "$eq",        9.0),
        ("mo_path",        "$contains",  8.5),
        ("section_number", "$eq",        8.0),
        ("spec_number",    "$contains",  7.5),
    ]

    for field_name, op, score in field_scores:
        try:
            res = collection.get(
                where={field_name: {op: q}},
                include=["documents", "metadatas"],
                limit=5,
            )
            if res and res.get("ids"):
                for i, doc_id in enumerate(res["ids"]):
                    if doc_id not in seen:
                        seen.add(doc_id)
                        results.append({
                            "id":       doc_id,
                            "text":     res["documents"][i],
                            "metadata": res["metadatas"][i],
                            "distance": 0.0,
                            "type":     "exact" if op == "$eq" else "exact_contains",
                        })
        except Exception:
            pass

    if results:
        logger.info(f"Exact match: {len(results)} hits for '{q}'")
    return results


# ══════════════════════════════════════════════════════════
#  STAGE 1 — VECTOR SEARCH
# ══════════════════════════════════════════════════════════

def vector_search(query: str, collection, top_k: int) -> List[tuple]:
    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    out = []
    if not results["ids"][0]:
        return out
    for i, doc_id in enumerate(results["ids"][0]):
        out.append((doc_id, {
            "text":     results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
            "type":     "vector",
        }))
    return out


# ══════════════════════════════════════════════════════════
#  STAGE 2 — RERANK WITH CALIBRATED FILTERING
# ══════════════════════════════════════════════════════════

def rerank_and_filter(
    query:      str,
    candidates: Dict[str, dict],
    top_n:      int,
    source:     str,
) -> List[RetrievedChunk]:
    """
    Rerank all candidates. Apply filtering policy:
    - Exact match chunks: always pass regardless of score
    - Non-exact chunks:
        Step 1 — source-aware absolute floor
        Step 2 — dynamic bottom-30% discard
    """
    if not candidates:
        return []

    reranker       = _get_reranker()
    cand_list      = list(candidates.items())
    texts          = [data["text"]                        for _, data in cand_list]
    exact_mask     = [data.get("type","vector") in
                      ("exact","exact_contains")          for _, data in cand_list]
    pairs          = [[query, t]                          for t in texts]
    raw_scores     = [float(s) for s in reranker.predict(pairs)]

    # Compute effective floor for non-exact chunks
    effective_floor = _compute_effective_floor(raw_scores, exact_mask, source)

    chunks = []
    for i, (doc_id, data) in enumerate(cand_list):
        score    = raw_scores[i]
        is_exact = exact_mask[i]

        # Policy: exact always passes; non-exact must beat floor
        if not is_exact and score < effective_floor:
            logger.debug(f"Discarded: score={score:.2f} < floor={effective_floor:.2f}")
            continue

        meta = data.get("metadata", {})
        chunks.append(RetrievedChunk(
            text           = data["text"],
            source_file    = meta.get("source", meta.get("doc_name", "unknown")),
            chunk_idx      = meta.get("chunk_idx", i),
            embed_distance = data.get("distance", 0.0),
            rerank_score   = score,
            metadata       = meta,
            match_type     = data.get("type", "vector"),
        ))

    chunks.sort(key=lambda c: c.rerank_score, reverse=True)

    passed_exact  = sum(1 for c in chunks if c.is_exact)
    passed_vector = sum(1 for c in chunks if not c.is_exact)
    logger.info(
        f"{source.upper()}: {len(cand_list)} candidates → "
        f"{passed_exact} exact + {passed_vector} vector passed → "
        f"returning top {min(top_n, len(chunks))}"
    )
    return chunks[:top_n]


# ══════════════════════════════════════════════════════════
#  MAIN RETRIEVE
# ══════════════════════════════════════════════════════════

def retrieve(
    query:           str,
    collection_name: str,
    top_k:           int = cfg.RETRIEVAL_TOP_K,
    top_n:           int = cfg.RERANK_TOP_N,
) -> List[RetrievedChunk]:
    """
    Full retrieval pipeline:
      Stage 0: exact metadata match  → always pass
      Stage 1: vector search         → top-k candidates
      Stage 2: merge + dedup
      Stage 3: rerank + filter
    """
    client   = _get_client()
    embed_fn = _get_embed_fn()

    try:
        collection = client.get_collection(
            name=collection_name, embedding_function=embed_fn)
    except Exception:
        logger.warning(f"Collection '{collection_name}' not found")
        return []

    if collection.count() == 0:
        logger.warning(f"Collection '{collection_name}' is empty")
        return []

    # Determine source for floor selection
    source = "hedex" if "hedex" in collection_name.lower() else "3gpp"

    # Build candidate dict — exact matches first (highest priority)
    candidates: Dict[str, dict] = {}

    for r in exact_match_search(query, collection):
        candidates[r["id"]] = {
            "text":     r["text"],
            "metadata": r["metadata"],
            "distance": 0.0,
            "type":     r["type"],
        }

    # Vector search with expanded query
    expanded = expand_query(query, source)
    for doc_id, data in vector_search(expanded, collection, top_k=max(top_k, 15)):
        if doc_id not in candidates:
            candidates[doc_id] = data

    return rerank_and_filter(query, candidates, top_n=max(top_n, 5), source=source)


def best_score(chunks: List[RetrievedChunk]) -> float:
    if not chunks:
        return 0.0
    return chunks[0].normalised_score


# ══════════════════════════════════════════════════════════
#  CITATION VALIDATOR
# ══════════════════════════════════════════════════════════

def extract_allowed_citations(chunks: List[RetrievedChunk]) -> set:
    """Extract all real spec refs from retrieved chunks for validation."""
    allowed   = set()
    clause_re = re.compile(r'\b(\d+\.\d+(?:\.\d+)*)\b')
    spec_re   = re.compile(r'TS\s*(\d+\.\d+)', re.IGNORECASE)

    for c in chunks:
        if c.section_number: allowed.add(c.section_number)
        if c.spec_number:    allowed.add(c.spec_number)
        for m in clause_re.finditer(c.text): allowed.add(m.group(1))
        for m in spec_re.finditer(c.text):   allowed.add(f"TS {m.group(1)}")
    return allowed


def validate_citations(answer: str, allowed: set) -> str:
    """Replace citations not found in retrieved chunks."""
    answer = re.sub(r'§\s*[A-Z]\.[\dA-Z]', '[section not in retrieved docs]', answer)
    spec_p = re.compile(r'(TS\s*\d+\.\d+(?:\s*§\s*[\d\.]+)?)', re.IGNORECASE)

    def check(m):
        ref   = m.group(1).strip()
        clean = re.sub(r'\s+', '', ref.upper())
        for a in allowed:
            if re.sub(r'\s+', '', a.upper()) in clean or \
               clean in re.sub(r'\s+', '', a.upper()):
                return ref
        return f"[{ref} — not in retrieved docs]"

    return spec_p.sub(check, answer)


def build_evidence_summary(
    chunks_3gpp:  List[RetrievedChunk],
    chunks_hedex: List[RetrievedChunk],
) -> str:
    """
    Build a concise evidence summary from retrieved chunks.
    Passed to OpenAI so it can reference confirmed findings without inventing.
    """
    lines = []

    for c in chunks_3gpp:
        if c.spec_number and c.section_number:
            lines.append(f"3GPP: {c.spec_number} §{c.section_number} — {c.metadata.get('section_title','')}")
        elif c.spec_number:
            lines.append(f"3GPP: {c.spec_number} — {c.source_file}")

    for c in chunks_hedex:
        if c.parameter_name and c.mo_path:
            lines.append(f"HedEx: {c.mo_path} → {c.parameter_name}")
        elif c.parameter_name:
            lines.append(f"HedEx param: {c.parameter_name}")
        elif c.mo_path:
            lines.append(f"HedEx MO: {c.mo_path}")

    return "\n".join(lines) if lines else ""
