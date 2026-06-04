"""
hedex_ingestor_v2.py — Step 4
==============================
HedEx pdfplumber table extraction ingestor.
Replaces basic pypdf HedEx ingestion with structured parameter extraction.

Each HedEx parameter row becomes a chunk with full metadata:
  parameter_name, mo_path, default_value, value_range, unit, description

This enables Stage 0 exact-match: "VonrAirTimeoutEpsfbTimer" hits directly.

Usage:
    $env:KMP_DUPLICATE_LIB_OK="TRUE"
    cd C:\\Working\\Telecom RAG\\telecom-rag-complete\\backend
    C:\\Users\\triaz\\miniconda3_New\\envs\\rag\\python.exe hedex_ingestor_v2.py --reset
    C:\\Users\\triaz\\miniconda3_New\\envs\\rag\\python.exe hedex_ingestor_v2.py          # incremental
    C:\\Users\\triaz\\miniconda3_New\\envs\\rag\\python.exe hedex_ingestor_v2.py --test 5  # first 5 files only
    C:\\Users\\triaz\\miniconda3_New\\envs\\rag\\python.exe hedex_ingestor_v2.py --file "NRCellDU.pdf"
"""

import argparse
import hashlib
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import chromadb
import pdfplumber
import pypdf
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
import torch

sys.path.insert(0, str(Path(__file__).parent))
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("hedex.ingestor.v2")

cfg = Config()

# ─────────────────────────────────────────────────────────────────────────────
# COLUMN DETECTION — Huawei HedEx table headers are inconsistent
# ─────────────────────────────────────────────────────────────────────────────

COLUMN_KEYWORDS: Dict[str, List[str]] = {
    "parameter_name": [
        "parameter name", "parameter", "param name", "name",
        "attribute name", "attribute", "mo attribute",
    ],
    "mo_path": [
        "mo path", "mo name", "managed object", "mo", "object path",
        "object name", "mo class", "class",
    ],
    "default_value": [
        "default value", "default", "initial value", "factory default",
        "initial", "preset value",
    ],
    "value_range": [
        "value range", "range", "valid range", "value", "values",
        "allowed values", "permitted values",
    ],
    "unit": ["unit", "units", "measurement unit"],
    "description": [
        "description", "desc", "meaning", "function description",
        "function", "remark", "note", "effect", "parameter description",
    ],
}

# MO path pattern: NRCellDU.VonrAirTimeoutEpsfbTimer
MO_PATH_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9]{2,})\s*[./]\s*([A-Za-z][A-Za-z0-9]{2,})\b"
)

# CamelCase parameter name: VonrAirTimeoutEpsfbTimer
PARAM_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z0-9]+){2,})\b")

# Numeric range: 0~127, 0-3600, 0..255
RANGE_RE = re.compile(r"\b(\d+)\s*[~\-\.]{1,2}\s*(\d+)\b")

# Section headings in HedEx text content
SECTION_RE = re.compile(r"^(\d+(?:\.\d+){0,4})\s{2,}(.{5,80})$", re.MULTILINE)


# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDER
# ─────────────────────────────────────────────────────────────────────────────

class Embedder:
    def __init__(self):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading {cfg.EMBED_MODEL} on {device}")
        self.model = SentenceTransformer(cfg.EMBED_MODEL, device=device)
        self.device = device
        logger.info(f"Embedder ready — dim={self.model.get_sentence_embedding_dimension()}")

    def embed(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        vecs = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 20,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vecs.tolist()


# ─────────────────────────────────────────────────────────────────────────────
# COLUMN MAP DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_col_map(headers: List[str]) -> Dict[str, int]:
    """Map logical column types → actual column indices."""
    col_map: Dict[str, int] = {}
    for i, h in enumerate(headers):
        if not h:
            continue
        h_lower = h.lower().strip().replace("\n", " ")
        for col_type, keywords in COLUMN_KEYWORDS.items():
            if col_type not in col_map:
                if any(kw in h_lower for kw in keywords):
                    col_map[col_type] = i
    return col_map


# ─────────────────────────────────────────────────────────────────────────────
# TABLE EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def clean_cell(val: Any) -> str:
    """Normalize a table cell value to a clean string."""
    if val is None:
        return ""
    return str(val).strip().replace("\n", " ").replace("\r", "")


def extract_tables_from_page(page) -> List[Dict[str, str]]:
    """
    Extract parameter records from a single pdfplumber page.
    Tries strict line detection first, falls back to looser settings.
    Returns list of record dicts.
    """
    records = []

    # Try strict table extraction (best for HedEx grid tables)
    settings_list = [
        {   # Strict: explicit line-based
            "vertical_strategy": "lines_strict",
            "horizontal_strategy": "lines_strict",
            "min_words_vertical": 2,
            "min_words_horizontal": 1,
            "snap_tolerance": 3,
            "intersection_tolerance": 3,
        },
        {   # Medium: regular lines
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": 5,
        },
        {   # Loose: text-based column detection
            "vertical_strategy": "text",
            "horizontal_strategy": "lines",
        },
    ]

    tables = []
    for settings in settings_list:
        try:
            tables = page.extract_tables(table_settings=settings)
            if tables:
                break
        except Exception:
            continue

    for table in tables:
        if not table or len(table) < 2:
            continue

        # Find header row — first row with multiple non-empty cells
        header_row_idx = 0
        for i, row in enumerate(table[:5]):  # Search first 5 rows
            non_empty = sum(1 for c in row if c and str(c).strip())
            if non_empty >= 2:
                header_row_idx = i
                break

        headers = [clean_cell(c) for c in table[header_row_idx]]
        col_map = detect_col_map(headers)

        # Must have at least parameter name OR description
        if "parameter_name" not in col_map and "description" not in col_map:
            continue

        for row in table[header_row_idx + 1:]:
            if not row:
                continue
            non_empty = sum(1 for c in row if c and str(c).strip())
            if non_empty < 2:
                continue  # Skip near-empty rows

            def cell(col_type: str) -> str:
                idx = col_map.get(col_type)
                if idx is None or idx >= len(row):
                    return ""
                return clean_cell(row[idx])

            param = cell("parameter_name")
            mo = cell("mo_path")
            desc = cell("description")
            default = cell("default_value")
            rng = cell("value_range")
            unit = cell("unit")

            # Require at least a real parameter name or meaningful description
            if len(param) < 3 and len(desc) < 15:
                continue

            # Try to extract MO path from description if not in its own column
            if not mo and desc:
                mo_match = MO_PATH_RE.search(desc)
                if mo_match:
                    mo = f"{mo_match.group(1)}.{mo_match.group(2)}"

            records.append({
                "parameter_name": param,
                "mo_path":        mo,
                "default_value":  default,
                "value_range":    rng,
                "unit":           unit,
                "description":    desc,
            })

    return records


def extract_text_fallback(page, page_num: int) -> List[Dict[str, str]]:
    """
    Fallback: extract narrative text sections when no tables found.
    Preserves section structure for non-table HedEx pages.
    """
    text = page.extract_text() or ""
    if len(text.strip()) < 80:
        return []

    sections = []
    parts = SECTION_RE.split(text)

    if len(parts) >= 4:
        i = 1
        while i + 2 <= len(parts):
            sec_num = parts[i].strip() if i < len(parts) else ""
            sec_title = parts[i + 1].strip() if i + 1 < len(parts) else ""
            body = parts[i + 2].strip() if i + 2 < len(parts) else ""
            if body and len(body) > 60:
                sections.append({
                    "parameter_name": "",
                    "mo_path":        "",
                    "default_value":  "",
                    "value_range":    "",
                    "unit":           "",
                    "description":    body[:2000],
                    "_section":       f"{sec_num} {sec_title}".strip(),
                })
            i += 3
    else:
        # Single block of text
        sections.append({
            "parameter_name": "",
            "mo_path":        "",
            "default_value":  "",
            "value_range":    "",
            "unit":           "",
            "description":    text.strip()[:2000],
            "_section":       f"page_{page_num}",
        })

    return sections


# ─────────────────────────────────────────────────────────────────────────────
# CHUNK BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_chunk_text(record: Dict[str, str], source_name: str) -> str:
    """
    Build the embeddable text string for a parameter record.
    Structured format maximizes both BM25 and vector search quality.
    """
    parts = []

    param = record.get("parameter_name", "").strip()
    mo = record.get("mo_path", "").strip()
    default = record.get("default_value", "").strip()
    rng = record.get("value_range", "").strip()
    unit = record.get("unit", "").strip()
    desc = record.get("description", "").strip()
    section = record.get("_section", "").strip()

    # Header line — most important for retrieval
    if param:
        parts.append(f"Parameter: {param}")
    if mo:
        parts.append(f"MO Path: {mo}")

    # Values
    if default:
        unit_str = f" {unit}" if unit else ""
        parts.append(f"Default Value: {default}{unit_str}")
    if rng:
        unit_str = f" {unit}" if unit else ""
        parts.append(f"Value Range: {rng}{unit_str}")

    # Description
    if desc:
        parts.append(f"Description: {desc}")

    # Section context
    if section:
        parts.append(f"Section: {section}")

    # Source attribution
    parts.append(f"Source: {source_name}")

    return "\n".join(parts)


def build_metadata(record: Dict[str, str], source_file: str, page_num: int) -> Dict[str, Any]:
    """Build ChromaDB metadata dict for a record."""
    meta = {
        "source":         source_file,
        "page_num":       page_num,
        "data_type":      "hedex",
        "ingested_at":    int(time.time()),
    }

    # Only add non-empty values (ChromaDB rejects None)
    for field in ["parameter_name", "mo_path", "default_value", "value_range", "unit"]:
        val = record.get(field, "").strip()
        if val:
            meta[field] = val

    # MO class (first part of mo_path before the dot)
    mo = record.get("mo_path", "")
    if mo and "." in mo:
        meta["mo_class"] = mo.split(".")[0]

    return meta


def make_chunk_id(source_file: str, page_num: int, record_idx: int, text: str) -> str:
    """Deterministic, stable chunk ID."""
    content_hash = hashlib.md5(text.encode()).hexdigest()[:10]
    safe_name = re.sub(r"[^a-zA-Z0-9]", "_", Path(source_file).stem)[:30]
    return f"hedex_{safe_name}_p{page_num:04d}_r{record_idx:03d}_{content_hash}"


# ─────────────────────────────────────────────────────────────────────────────
# PER-FILE INGESTION
# ─────────────────────────────────────────────────────────────────────────────

def ingest_pdf(
    pdf_path: Path,
    embedder: Embedder,
    collection: chromadb.Collection,
    existing_ids: set,
    max_pages: int = 0,
) -> Tuple[int, int]:
    """
    Ingest a single HedEx PDF using pdfplumber.
    Returns (chunks_added, pages_processed).
    """
    logger.info(f"\n{'─'*60}")
    logger.info(f"File: {pdf_path.name}")

    chunks_texts: List[str] = []
    chunks_metas: List[Dict] = []
    chunks_ids: List[str] = []

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            total_pages = len(pdf.pages)
            pages_to_process = total_pages if not max_pages else min(max_pages, total_pages)
            logger.info(f"Pages: {total_pages} | Processing: {pages_to_process}")

            table_count = 0
            fallback_count = 0

            for page_num, page in enumerate(pdf.pages[:pages_to_process], start=1):
                try:
                    # Primary: table extraction
                    records = extract_tables_from_page(page)

                    if records:
                        table_count += len(records)
                    else:
                        # Fallback: narrative text
                        records = extract_text_fallback(page, page_num)
                        fallback_count += len(records)

                    for rec_idx, record in enumerate(records):
                        text = build_chunk_text(record, pdf_path.name)
                        if len(text.strip()) < 40:
                            continue

                        chunk_id = make_chunk_id(pdf_path.name, page_num, rec_idx, text)
                        if chunk_id in existing_ids:
                            continue

                        meta = build_metadata(record, pdf_path.name, page_num)
                        chunks_texts.append(text)
                        chunks_metas.append(meta)
                        chunks_ids.append(chunk_id)

                except Exception as e:
                    logger.warning(f"  Page {page_num} error: {e}")
                    continue

        logger.info(f"  Table records: {table_count} | Fallback sections: {fallback_count}")

    except Exception as e:
        logger.error(f"  Failed to open {pdf_path.name}: {e}")
        return 0, 0

    if not chunks_texts:
        logger.info(f"  No new chunks — skipping")
        return 0, 0

    # Embed
    logger.info(f"  Embedding {len(chunks_texts)} chunks...")
    t0 = time.time()
    embeddings = embedder.embed(chunks_texts)
    logger.info(f"  Embedded in {time.time()-t0:.1f}s")

    # Store in batches of 500 (ChromaDB limit)
    BATCH = 500
    for start in range(0, len(chunks_texts), BATCH):
        end = min(start + BATCH, len(chunks_texts))
        collection.add(
            ids=chunks_ids[start:end],
            embeddings=embeddings[start:end],
            documents=chunks_texts[start:end],
            metadatas=chunks_metas[start:end],
        )

    logger.info(f"  ✓ Added {len(chunks_texts)} chunks from {pdf_path.name}")
    return len(chunks_texts), pages_to_process


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HedEx pdfplumber Ingestor v2")
    parser.add_argument("--reset",    action="store_true",  help="Wipe HedEx collection and rebuild")
    parser.add_argument("--file",     type=str,             help="Single PDF filename to ingest")
    parser.add_argument("--test",     type=int, default=0,  help="Only process first N files")
    parser.add_argument("--maxpages", type=int, default=0,  help="Max pages per PDF (0=all)")
    parser.add_argument("--list",     action="store_true",  help="Show collection stats and exit")
    args = parser.parse_args()

    # ChromaDB setup
    client = chromadb.PersistentClient(
        path=cfg.CHROMA_PERSIST_DIR,
        settings=ChromaSettings(anonymized_telemetry=False),
    )

    if args.reset:
        try:
            client.delete_collection(cfg.COLLECTION_HEDEX)
            logger.info(f"Deleted collection: {cfg.COLLECTION_HEDEX}")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=cfg.COLLECTION_HEDEX,
        metadata={"hnsw:space": "cosine"},
    )

    if args.list:
        count = collection.count()
        logger.info(f"Collection '{cfg.COLLECTION_HEDEX}': {count} chunks")
        if count > 0:
            sample = collection.get(limit=5, include=["metadatas"])
            for m in sample["metadatas"]:
                param = m.get("parameter_name", "")
                mo = m.get("mo_path", "")
                logger.info(f"  {m['source']} | {param} | {mo}")
        return

    # Determine files
    hedex_dir = Path(cfg.DATA_DIR_HEDEX)
    if args.file:
        pdf_paths = [hedex_dir / args.file]
    else:
        pdf_paths = sorted(hedex_dir.glob("*.pdf"))

    if args.test:
        pdf_paths = pdf_paths[:args.test]

    if not pdf_paths:
        logger.error(f"No PDFs found in {hedex_dir}")
        sys.exit(1)

    logger.info(f"Found {len(pdf_paths)} PDF(s) to process")

    # Load existing IDs for deduplication
    existing_ids = set(collection.get(include=[])["ids"])
    logger.info(f"Existing chunks in DB: {len(existing_ids)}")

    # Initialize embedder
    embedder = Embedder()

    # Ingest
    total_chunks = 0
    t_start = time.time()

    for pdf_path in pdf_paths:
        if not pdf_path.exists():
            logger.warning(f"Not found: {pdf_path}")
            continue
        chunks, pages = ingest_pdf(pdf_path, embedder, collection, existing_ids, args.maxpages)
        total_chunks += chunks

    elapsed = time.time() - t_start
    final_count = collection.count()

    logger.info(f"\n{'='*60}")
    logger.info(f"HEDEX INGESTION COMPLETE (v2 pdfplumber)")
    logger.info(f"  New chunks added   : {total_chunks}")
    logger.info(f"  Total in DB        : {final_count}")
    logger.info(f"  Time               : {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info(f"  ChromaDB path      : {cfg.CHROMA_PERSIST_DIR}")
    logger.info(f"\nNext: restart api.py to use new chunks")


if __name__ == "__main__":
    main()
