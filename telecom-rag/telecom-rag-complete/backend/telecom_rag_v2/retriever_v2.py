"""
retriever_v2.py — Steps 4 + 7
================================
4-stage retrieval with BM25 hybrid search added.

Stage 0: Exact metadata match (parameter_name, mo_path, section_number)
Stage 1: BM25 + vector hybrid search with 582-term query expansion
Stage 2: CrossEncoder reranking (bge-reranker-large)
Stage 3: Score filtering (floor + dynamic bottom-30% discard)

BM25 is always hybrid (merged with vector), weighted by BM25_WEIGHT / VECTOR_WEIGHT in .env

Drop into: C:\\Working\\Telecom RAG\\telecom-rag-complete\\backend\\
Then update api.py import to: from retriever_v2 import Retriever
"""

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import chromadb
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder
import torch

sys.path.insert(0, str(Path(__file__).parent))
from config import Config
from query_expansion import expand_query, get_expansion_terms

logger = logging.getLogger("telecom.retriever.v2")
cfg = Config()

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

BM25_WEIGHT    = float(os.getenv("BM25_WEIGHT",    "0.35"))
VECTOR_WEIGHT  = float(os.getenv("VECTOR_WEIGHT",  "0.65"))
FLOOR_3GPP     = float(os.getenv("CONF_THRESHOLD_3GPP", "0.30"))
FLOOR_HEDEX    = float(os.getenv("CONF_THRESHOLD_HEDEX", "0.30"))
TOP_K          = int(os.getenv("RETRIEVAL_TOP_K",  "30"))
RERANK_TOP_N   = int(os.getenv("RERANK_TOP_N",     "8"))

# Absolute rerank score floors (CrossEncoder raw scores)
RERANK_FLOOR_3GPP  = -3.0
RERANK_FLOOR_HEDEX = -2.0

# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDER (singleton)
# ─────────────────────────────────────────────────────────────────────────────

class _EmbedderSingleton:
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading embedder: {cfg.EMBED_MODEL} on {device}")
            cls._instance = SentenceTransformer(cfg.EMBED_MODEL, device=device)
        return cls._instance


def embed_query(query: str) -> List[float]:
    model = _EmbedderSingleton.get()
    # BGE models require prefix for queries
    if "bge" in cfg.EMBED_MODEL.lower():
        query = f"Represent this sentence for searching relevant passages: {query}"
    vec = model.encode(query, normalize_embeddings=True, convert_to_numpy=True)
    return vec.tolist()


# ─────────────────────────────────────────────────────────────────────────────
# RERANKER (singleton)
# ─────────────────────────────────────────────────────────────────────────────

class _RerankerSingleton:
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading reranker: {cfg.RERANKER_MODEL} on {device}")
            try:
                cls._instance = CrossEncoder(
                    cfg.RERANKER_MODEL,
                    device=device,
                    max_length=512,
                )
            except Exception as e:
                logger.warning(f"Reranker load failed: {e} — using score-only ranking")
                cls._instance = None
        return cls._instance


# ─────────────────────────────────────────────────────────────────────────────
# BM25 INDEX (built per collection per session)
# ─────────────────────────────────────────────────────────────────────────────

class BM25Index:
    """
    Lightweight BM25 index built from ChromaDB collection.
    Rebuilt once per session (in-memory). For 60k+ chunks this takes ~5s.
    """

    def __init__(self, collection: chromadb.Collection, collection_name: str):
        self.collection_name = collection_name
        self._ids: List[str] = []
        self._texts: List[str] = []
        self._bm25: Optional[BM25Okapi] = None
        self._build(collection)

    def _tokenize(self, text: str) -> List[str]:
        # Simple whitespace + lowercase tokenizer, preserve CamelCase splits
        # CamelCase split: "VonrAirTimeout" → ["vonr", "air", "timeout"]
        text = re.sub(r"([A-Z][a-z]+)", r" \1", text)
        text = re.sub(r"([A-Z]+)([A-Z][a-z])", r" \1 \2", text)
        tokens = re.findall(r"[a-zA-Z0-9]{2,}", text.lower())
        return tokens

    def _build(self, collection: chromadb.Collection):
        logger.info(f"Building BM25 index for {self.collection_name}...")
        t0 = __import__("time").time()
        try:
            count = collection.count()
            if count == 0:
                logger.warning("Collection empty — BM25 index empty")
                return

            # Fetch all docs in batches
            BATCH = 5000
            all_ids, all_texts = [], []
            offset = 0
            while offset < count:
                result = collection.get(
                    limit=BATCH,
                    offset=offset,
                    include=["documents"],
                )
                all_ids.extend(result["ids"])
                all_texts.extend(result["documents"])
                offset += BATCH

            self._ids = all_ids
            self._texts = all_texts
            tokenized = [self._tokenize(t) for t in all_texts]
            self._bm25 = BM25Okapi(tokenized)
            elapsed = __import__("time").time() - t0
            logger.info(f"BM25 index built: {len(all_ids)} docs in {elapsed:.1f}s")

        except Exception as e:
            logger.error(f"BM25 build failed: {e}")

    def search(self, query: str, top_n: int) -> List[Tuple[str, float]]:
        """Returns list of (chunk_id, normalized_bm25_score) sorted desc."""
        if self._bm25 is None or not self._ids:
            return []

        tokens = self._tokenize(query)
        scores = self._bm25.get_scores(tokens)

        # Normalize to 0-1
        max_score = scores.max()
        if max_score > 0:
            scores = scores / max_score

        top_indices = np.argsort(scores)[::-1][:top_n]
        return [(self._ids[i], float(scores[i])) for i in top_indices if scores[i] > 0]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RETRIEVER
# ─────────────────────────────────────────────────────────────────────────────

class Retriever:
    """
    v2 Retriever — dual-collection (3GPP + HedEx) with BM25 hybrid.

    Usage:
        r = Retriever()
        results_3gpp  = r.retrieve_3gpp("VoNR call drop T310")
        results_hedex = r.retrieve_hedex("VonrAirTimeoutEpsfbTimer default value")
    """

    def __init__(self):
        logger.info("Initializing Retriever v2...")

        self.client = chromadb.PersistentClient(path=cfg.CHROMA_PERSIST_DIR)
        self.col_3gpp  = self.client.get_collection(cfg.COLLECTION_3GPP)
        self.col_hedex = self.client.get_collection(cfg.COLLECTION_HEDEX)

        logger.info(f"3GPP: {self.col_3gpp.count()} chunks | HedEx: {self.col_hedex.count()} chunks")

        # Build BM25 indexes (done once at startup)
        self.bm25_3gpp  = BM25Index(self.col_3gpp,  "3gpp")
        self.bm25_hedex = BM25Index(self.col_hedex, "hedex")

        # Reranker
        self.reranker = _RerankerSingleton.get()

        logger.info("Retriever v2 ready")

    # ── PUBLIC: retrieve from 3GPP ────────────────────────────────────────────

    def retrieve_3gpp(self, query: str) -> List[Dict[str, Any]]:
        return self._retrieve(
            query=query,
            collection=self.col_3gpp,
            bm25=self.bm25_3gpp,
            floor=RERANK_FLOOR_3GPP,
            source_label="3gpp",
        )

    # ── PUBLIC: retrieve from HedEx ───────────────────────────────────────────

    def retrieve_hedex(self, query: str) -> List[Dict[str, Any]]:
        return self._retrieve(
            query=query,
            collection=self.col_hedex,
            bm25=self.bm25_hedex,
            floor=RERANK_FLOOR_HEDEX,
            source_label="hedex",
        )

    # ── CORE PIPELINE ─────────────────────────────────────────────────────────

    def _retrieve(
        self,
        query: str,
        collection: chromadb.Collection,
        bm25: BM25Index,
        floor: float,
        source_label: str,
    ) -> List[Dict[str, Any]]:
        """Full 4-stage retrieval pipeline."""

        # Stage 0: Exact metadata match
        exact_hits = self._stage0_exact(query, collection, source_label)

        # Stage 1: BM25 + vector hybrid with query expansion
        expanded_query = expand_query(query)
        vector_hits = self._stage1_vector(expanded_query, collection)
        bm25_hits   = self._stage1_bm25(expanded_query, bm25, collection)

        # Merge: combine exact + hybrid candidates, deduplicate
        candidates = self._merge_candidates(exact_hits, vector_hits, bm25_hits)

        if not candidates:
            return []

        # Stage 2: CrossEncoder reranking
        if self.reranker and len(candidates) > 1:
            candidates = self._stage2_rerank(query, candidates)

        # Stage 3: Score filtering
        candidates = self._stage3_filter(candidates, floor)

        # Format output
        return [self._format_result(c, source_label) for c in candidates[:RERANK_TOP_N]]

    # ── STAGE 0: Exact metadata match ─────────────────────────────────────────

    def _stage0_exact(
        self,
        query: str,
        collection: chromadb.Collection,
        source_label: str,
    ) -> List[Dict]:
        """
        Look for exact parameter/MO/section matches in metadata.
        These always bypass score thresholds — if found, they go straight to reranking.
        """
        hits = []

        # Extract CamelCase tokens (likely parameter names)
        camel_tokens = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+){1,}\b", query)

        # Extract MO path patterns like NRCellDU.VonrXxx
        mo_patterns = re.findall(
            r"\b([A-Z][A-Za-z0-9]+(?:Cell|DU|CU|GNB|NR|Enb|Lte|Vo)[A-Za-z0-9]*)\b",
            query,
        )

        # Extract 3GPP section patterns: §5.3.10 or 5.3.10
        section_patterns = re.findall(r"§?(\d+(?:\.\d+){1,5})", query)

        search_targets = []

        for token in camel_tokens:
            search_targets.append(("parameter_name", token))
        for mo in mo_patterns:
            search_targets.append(("mo_class", mo))
            search_targets.append(("mo_path", mo))
        for sec in section_patterns:
            search_targets.append(("section_number", sec))

        for field, value in search_targets:
            try:
                result = collection.query(
                    query_texts=[value],
                    n_results=min(5, collection.count()),
                    where={field: {"$eq": value}},
                    include=["documents", "metadatas", "distances"],
                )
                if result["documents"] and result["documents"][0]:
                    for doc, meta, dist in zip(
                        result["documents"][0],
                        result["metadatas"][0],
                        result["distances"][0],
                    ):
                        hits.append({
                            "text": doc,
                            "metadata": meta,
                            "vector_score": 1.0 - dist,
                            "bm25_score": 1.0,      # Exact match → max BM25
                            "hybrid_score": 1.0,
                            "stage": 0,
                        })
            except Exception:
                continue

        if hits:
            logger.info(f"  Stage 0 exact match: {len(hits)} hits")

        return hits

    # ── STAGE 1a: Vector search ───────────────────────────────────────────────

    def _stage1_vector(self, query: str, collection: chromadb.Collection) -> List[Dict]:
        try:
            vec = embed_query(query)
            result = collection.query(
                query_embeddings=[vec],
                n_results=min(TOP_K, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            hits = []
            if result["documents"] and result["documents"][0]:
                for doc, meta, dist in zip(
                    result["documents"][0],
                    result["metadatas"][0],
                    result["distances"][0],
                ):
                    hits.append({
                        "text": doc,
                        "metadata": meta,
                        "vector_score": max(0.0, 1.0 - dist),
                        "bm25_score": 0.0,
                        "hybrid_score": 0.0,
                        "stage": 1,
                    })
            return hits
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    # ── STAGE 1b: BM25 search ─────────────────────────────────────────────────

    def _stage1_bm25(self, query: str, bm25: BM25Index, collection: chromadb.Collection) -> List[Dict]:
        bm25_results = bm25.search(query, top_n=TOP_K)
        if not bm25_results:
            return []

        # Fetch full documents for BM25 hits
        ids = [r[0] for r in bm25_results]
        score_map = {r[0]: r[1] for r in bm25_results}

        try:
            result = collection.get(
                ids=ids,
                include=["documents", "metadatas"],
            )
        except Exception:
            return []

        hits = []
        for doc, meta, chunk_id in zip(result["documents"], result["metadatas"], result["ids"]):
            hits.append({
                "text": doc,
                "metadata": meta,
                "vector_score": 0.0,
                "bm25_score": score_map.get(chunk_id, 0.0),
                "hybrid_score": 0.0,
                "stage": 1,
            })
        return hits

    # ── MERGE: Deduplicate + compute hybrid score ─────────────────────────────

    def _merge_candidates(
        self,
        exact: List[Dict],
        vector: List[Dict],
        bm25_hits: List[Dict],
    ) -> List[Dict]:
        """
        Merge exact + vector + BM25 candidates.
        Deduplicate by text hash.
        Compute hybrid score = VECTOR_WEIGHT * vector_score + BM25_WEIGHT * bm25_score.
        """
        seen: Dict[str, Dict] = {}  # text_hash → candidate

        def add(candidate: Dict):
            text_hash = candidate["text"][:100]  # Use text prefix as key
            if text_hash not in seen:
                seen[text_hash] = candidate
            else:
                # Update scores with max of what we've seen
                existing = seen[text_hash]
                existing["vector_score"] = max(existing["vector_score"], candidate["vector_score"])
                existing["bm25_score"]   = max(existing["bm25_score"],   candidate["bm25_score"])

        # Exact hits first (highest priority)
        for c in exact:
            add(c)

        # Build lookup of BM25 scores by text prefix for vector hits
        bm25_score_map: Dict[str, float] = {
            c["text"][:100]: c["bm25_score"] for c in bm25_hits
        }

        # Merge vector scores with BM25
        for c in vector:
            key = c["text"][:100]
            c["bm25_score"] = bm25_score_map.get(key, 0.0)
            add(c)

        # Remaining BM25-only hits
        vector_keys = {c["text"][:100] for c in vector}
        for c in bm25_hits:
            if c["text"][:100] not in vector_keys:
                add(c)

        # Compute hybrid score
        for c in seen.values():
            c["hybrid_score"] = (
                VECTOR_WEIGHT * c["vector_score"] +
                BM25_WEIGHT   * c["bm25_score"]
            )
            if c.get("stage") == 0:
                c["hybrid_score"] = max(c["hybrid_score"], 0.95)  # Exact match boost

        # Sort by hybrid score
        return sorted(seen.values(), key=lambda x: x["hybrid_score"], reverse=True)

    # ── STAGE 2: CrossEncoder reranking ───────────────────────────────────────

    def _stage2_rerank(self, query: str, candidates: List[Dict]) -> List[Dict]:
        # Only rerank top candidates (speed vs quality tradeoff)
        to_rerank = candidates[:min(len(candidates), TOP_K)]
        pairs = [(query, c["text"][:512]) for c in to_rerank]

        try:
            scores = self.reranker.predict(pairs, show_progress_bar=False)
            for c, score in zip(to_rerank, scores):
                c["rerank_score"] = float(score)
        except Exception as e:
            logger.warning(f"Reranking failed: {e}")
            for c in to_rerank:
                c["rerank_score"] = c["hybrid_score"]

        return sorted(to_rerank, key=lambda x: x.get("rerank_score", 0), reverse=True)

    # ── STAGE 3: Score filtering ───────────────────────────────────────────────

    def _stage3_filter(self, candidates: List[Dict], floor: float) -> List[Dict]:
        """
        Remove candidates below floor.
        Also discard dynamic bottom 30% if too many pass the floor.
        Exact matches (stage=0) always pass.
        """
        # Exact matches always pass
        exact = [c for c in candidates if c.get("stage") == 0]
        rest  = [c for c in candidates if c.get("stage") != 0]

        # Apply floor to non-exact
        score_key = "rerank_score" if "rerank_score" in (rest[0] if rest else {}) else "hybrid_score"
        rest = [c for c in rest if c.get(score_key, 0) >= floor]

        # Dynamic bottom-30% discard
        if len(rest) > 4:
            scores = [c.get(score_key, 0) for c in rest]
            p30 = np.percentile(scores, 30)
            rest = [c for c in rest if c.get(score_key, 0) >= p30]

        return exact + rest

    # ── FORMAT OUTPUT ──────────────────────────────────────────────────────────

    def _format_result(self, candidate: Dict, source_label: str) -> Dict[str, Any]:
        meta = candidate.get("metadata", {})

        # Build citation string
        if source_label == "3gpp":
            spec_id   = meta.get("spec_id", "3GPP")
            sec_num   = meta.get("section_number", "")
            sec_head  = meta.get("section_heading", "")
            citation  = f"{spec_id}"
            if sec_num:
                citation += f" §{sec_num}"
            if sec_head:
                citation += f" — {sec_head[:50]}"
        else:
            param = meta.get("parameter_name", "")
            mo    = meta.get("mo_path", "")
            src   = meta.get("source", "HedEx")
            citation = f"HedEx | {src}"
            if param:
                citation += f" | {param}"
            if mo:
                citation += f" | {mo}"

        # Confidence score (0-100%) from rerank or hybrid
        raw_score = candidate.get("rerank_score", candidate.get("hybrid_score", 0))
        confidence = min(100, max(0, int((raw_score + 5) / 10 * 100)))  # Normalize CrossEncoder

        return {
            "text":            candidate["text"],
            "metadata":        meta,
            "citation":        citation,
            "confidence":      confidence,
            "rerank_score":    candidate.get("rerank_score", 0),
            "hybrid_score":    candidate.get("hybrid_score", 0),
            "vector_score":    candidate.get("vector_score", 0),
            "bm25_score":      candidate.get("bm25_score", 0),
            "stage":           candidate.get("stage", 1),
            "parameter_name":  meta.get("parameter_name", ""),
            "mo_path":         meta.get("mo_path", ""),
            "default_value":   meta.get("default_value", ""),
            "value_range":     meta.get("value_range", ""),
        }

    # ── STATS ──────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, int]:
        return {
            "3gpp_chunks":  self.col_3gpp.count(),
            "hedex_chunks": self.col_hedex.count(),
        }
