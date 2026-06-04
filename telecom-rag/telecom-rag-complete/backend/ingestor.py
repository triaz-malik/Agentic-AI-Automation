"""
ingestor.py — Production ingestion

3GPP:  pdfplumber extraction + clause-aware chunking
       spec number + release from filename
       section_number + section_title in every chunk metadata

HedEx: pypdf extraction (no pdfplumber needed)
       normalise switch names (underscores lost in PDF)
       4 regex patterns extract: parameter_name, mo_path,
       switch_name, counter_name into metadata
       enables exact match search in Stage 0 retrieval

Both:  chunk_size=1200, overlap=200
       section title prefixed in chunk text

Usage:
    python ingestor.py --source 3gpp
    python ingestor.py --source hedex
    python ingestor.py --source both --reset
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

from pypdf import PdfReader
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from loguru import logger
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from config import cfg

# ── Chunk settings (update .env to change these)
CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE",    1200))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP",  200))


# ══════════════════════════════════════════════════════════
#  SPEC NUMBER PARSER — from 3GPP filename
#  ts_138214v170300p.pdf → TS 38.214, release 17, v17.3.0
# ══════════════════════════════════════════════════════════

def parse_3gpp_filename(filename: str) -> Dict[str, str]:
    name = filename.lower().replace("-", "_")
    m = re.match(r'ts[_\s]?1(\d{2})(\d{3})v(\d{2})(\d{2})(\d{2})', name)
    if m:
        return {
            "spec_number": f"TS {m.group(1)}.{m.group(2)}",
            "release":     str(int(m.group(3))),
            "version":     f"{int(m.group(3))}.{int(m.group(4))}.{int(m.group(5))}",
            "vendor":      "3GPP",
            "source_type": "3gpp",
        }
    m2 = re.search(r'(\d{2})[\._](\d{3})', name)
    if m2:
        return {
            "spec_number": f"TS {m2.group(1)}.{m2.group(2)}",
            "release":     "unknown",
            "version":     "unknown",
            "vendor":      "3GPP",
            "source_type": "3gpp",
        }
    return {
        "spec_number": Path(filename).stem,
        "release":     "unknown",
        "version":     "unknown",
        "vendor":      "3GPP",
        "source_type": "3gpp",
    }


def parse_hedex_filename(filename: str) -> Dict[str, str]:
    return {
        "spec_number": Path(filename).stem,
        "release":     "unknown",
        "version":     "unknown",
        "vendor":      "Huawei",
        "source_type": "hedex",
    }


# ══════════════════════════════════════════════════════════
#  PDF TEXT EXTRACTION
# ══════════════════════════════════════════════════════════

def extract_text(pdf_path: Path, use_pdfplumber: bool = True) -> str:
    """Extract text from PDF. Uses pdfplumber if available, falls back to pypdf."""
    if use_pdfplumber and HAS_PDFPLUMBER:
        try:
            pages = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text(layout=True)
                    if text and text.strip():
                        pages.append(text)
            if pages:
                return "\n\n".join(pages)
        except Exception as e:
            logger.warning(f"pdfplumber failed for {pdf_path.name}: {e} — falling back to pypdf")

    # pypdf fallback
    try:
        reader = PdfReader(str(pdf_path))
        pages  = [p.extract_text() or "" for p in reader.pages]
        return "\n\n".join(p for p in pages if p.strip())
    except Exception as e:
        logger.error(f"Both extractors failed for {pdf_path.name}: {e}")
        return ""


# ══════════════════════════════════════════════════════════
#  3GPP — CLAUSE-AWARE CHUNKING
# ══════════════════════════════════════════════════════════

# Matches: "6.1.2 Title of the section" or "A.1 Annex title"
CLAUSE_RE = re.compile(
    r'^([A-Z]?\d+(?:\.\d+){0,3})\s{1,4}([A-Z][^\n]{2,80})$',
    re.MULTILINE,
)

def chunk_3gpp(text: str, spec_meta: Dict) -> List[Dict]:
    """
    Split 3GPP text on clause headings.
    Every chunk carries section_number and section_title.
    Long clauses are sub-split with overlap, keeping header in each sub-chunk.
    Falls back to sliding window if no clause structure detected.
    """
    matches = list(CLAUSE_RE.finditer(text))
    if not matches:
        logger.warning(f"No clause structure in {spec_meta.get('spec_number','?')} — using sliding window")
        return _sliding_window(text, spec_meta)

    chunks = []
    for i, m in enumerate(matches):
        clause_num   = m.group(1).strip()
        clause_title = m.group(2).strip()
        start        = m.start()
        end          = matches[i+1].start() if i + 1 < len(matches) else len(text)
        body         = text[start:end].strip()

        if len(body) < 50:
            continue

        # Prefix every chunk with spec + clause so embedding captures identity
        prefix = f"[{spec_meta.get('spec_number','')} §{clause_num}] {clause_title}\n\n"

        if len(body) <= CHUNK_SIZE:
            chunks.append({
                "text":            prefix + body,
                "chunk_type":      "clause",
                "section_number":  clause_num,
                "section_title":   clause_title,
                **spec_meta,
            })
        else:
            # Sub-split long clause, keep prefix in each sub-chunk
            sub_start = 0
            sub_idx   = 0
            while sub_start < len(body):
                sub_end  = min(sub_start + CHUNK_SIZE, len(body))
                sub_text = body[sub_start:sub_end].strip()
                if len(sub_text) > 50:
                    chunks.append({
                        "text":           prefix + sub_text,
                        "chunk_type":     "clause" if sub_idx == 0 else "clause_continued",
                        "section_number": clause_num,
                        "section_title":  clause_title,
                        **spec_meta,
                    })
                sub_start += CHUNK_SIZE - CHUNK_OVERLAP
                sub_idx   += 1

    logger.debug(f"3GPP: {len(matches)} clauses → {len(chunks)} chunks")
    return chunks


def _sliding_window(text: str, meta: Dict) -> List[Dict]:
    """Fallback chunker when no clause structure detected."""
    text   = re.sub(r'\s+', ' ', text).strip()
    chunks = []
    start  = 0
    while start < len(text):
        end   = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()
        if len(chunk) > 50:
            chunks.append({"text": chunk, "chunk_type": "body", **meta})
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ══════════════════════════════════════════════════════════
#  HEDEX — REGEX PATTERN EXTRACTION
#  No pdfplumber needed — post-processes pypdf text
# ══════════════════════════════════════════════════════════

def normalise_switch_names(text: str) -> str:
    """
    HedEx switch names lose underscores in PDF extraction.
    CONN VONR EPS FB ADAPT SW → CONN_VONR_EPS_FB_ADAPT_SW
    Detects sequences of 3+ ALL_CAPS words and joins with underscore.
    """
    return re.sub(
        r'\b([A-Z]{2,}(?:\s+[A-Z]{2,}){2,})\b',
        lambda m: m.group(1).replace(' ', '_'),
        text,
    )


# Pattern 1: SWITCH_NAME option of [the] MO.ParameterName [parameter]
SWITCH_IN_SENTENCE = re.compile(
    r'([A-Z][A-Z0-9_]{4,60})\s+option of (?:the\s+)?'
    r'([A-Za-z][A-Za-z0-9]{2,30})\.([A-Za-z][A-Za-z0-9]{3,40})',
)

# Pattern 2: CamelCase parameter name (min 3 humps, 8+ chars)
CAMEL_PARAM = re.compile(
    r'\b([A-Z][a-z0-9]{1,20}(?:[A-Z][a-z0-9]{1,20}){2,})\b'
)

# Pattern 3: Counter name N.Something.Something.Something
COUNTER_NAME = re.compile(
    r'\b(N\.[A-Za-z0-9]+(?:\.[A-Za-z0-9]+){2,})\b'
)

# Pattern 4: MO.Parameter inline reference (UPPERCASE_MO.CamelParam)
MO_PARAM_INLINE = re.compile(
    r'\b([A-Z][A-Za-z0-9]{3,30})\.([A-Z][A-Za-z][A-Za-z0-9]{3,40})\b'
)

# Known Huawei MO names to reduce false positives in Pattern 4
KNOWN_MOS = {
    "NRCellDU", "NRCellCU", "NRCellAlgoSwitch", "NRDUCellDlSch",
    "NRDUCellRac", "gNBDUFunction", "gNBCUCPFunction", "gNBRlcParamGroup",
    "gNBDUQciAlgoParamGrp", "NRCELLSERVEXP", "ENodeBFunction",
    "NRCellRelation", "gNBUeCompatibleCtrl", "NRCellDURach",
}


def extract_hedex_metadata(text: str) -> Dict[str, str]:
    """
    Run all 4 patterns on a HedEx chunk text.
    Returns metadata dict with extracted fields.
    First match wins for each field.
    """
    meta: Dict[str, str] = {
        "parameter_name": "",
        "mo_path":        "",
        "switch_name":    "",
        "counter_name":   "",
    }

    # Normalise first
    norm_text = normalise_switch_names(text)

    # Pattern 1 — switch in sentence (highest confidence)
    m = SWITCH_IN_SENTENCE.search(norm_text)
    if m:
        meta["switch_name"]    = m.group(1)
        meta["mo_path"]        = m.group(2)
        meta["parameter_name"] = m.group(3)

    # Pattern 3 — counter name
    m = COUNTER_NAME.search(text)
    if m and not meta["counter_name"]:
        meta["counter_name"] = m.group(1)
        # Counter name often implies a KPI parameter name
        if not meta["parameter_name"]:
            # e.g. N.CallDrop.CU.VoNR.Rate → CallDropCUVoNRRate
            parts = m.group(1).split('.')
            if len(parts) > 2:
                meta["parameter_name"] = '.'.join(parts[1:])  # drop leading "N."

    # Pattern 4 — MO.Parameter inline (only for known MOs)
    if not meta["mo_path"]:
        for m in MO_PARAM_INLINE.finditer(norm_text):
            if m.group(1) in KNOWN_MOS:
                meta["mo_path"]        = m.group(1)
                meta["parameter_name"] = meta["parameter_name"] or m.group(2)
                break

    # Pattern 2 — CamelCase param (lowest priority, fills gaps)
    if not meta["parameter_name"]:
        for m in CAMEL_PARAM.finditer(text):
            name = m.group(1)
            # Skip short common words
            if len(name) >= 8 and name not in {"Description","Function","Network","Default"}:
                meta["parameter_name"] = name
                break

    return meta


def chunk_hedex(text: str, hedex_meta: Dict) -> List[Dict]:
    """
    Chunk HedEx text with paragraph-aware splitting.
    Each chunk gets regex-extracted metadata attached.
    """
    # Normalise switch names before chunking
    text = normalise_switch_names(text)

    # Split on blank lines (paragraph boundaries)
    paragraphs = re.split(r'\n{2,}', text)
    chunks     = []
    buffer     = ""
    buf_paras  = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(buffer) + len(para) <= CHUNK_SIZE:
            buffer     += "\n\n" + para if buffer else para
            buf_paras.append(para)
        else:
            if buffer and len(buffer) > 50:
                meta = extract_hedex_metadata(buffer)
                chunks.append({
                    "text":       buffer,
                    "chunk_type": "body",
                    **hedex_meta,
                    **{k: v for k, v in meta.items() if v},
                })
            buffer    = para
            buf_paras = [para]

    if buffer and len(buffer) > 50:
        meta = extract_hedex_metadata(buffer)
        chunks.append({
            "text":       buffer,
            "chunk_type": "body",
            **hedex_meta,
            **{k: v for k, v in meta.items() if v},
        })

    return chunks


# ══════════════════════════════════════════════════════════
#  CHROMADB HELPERS
# ══════════════════════════════════════════════════════════

def get_chroma_client():
    cfg.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(cfg.CHROMA_PERSIST_DIR))

def get_embed_fn():
    return SentenceTransformerEmbeddingFunction(
        model_name=cfg.EMBED_MODEL, device="cuda", normalize_embeddings=True)

def get_or_create_collection(client, name: str, reset: bool = False):
    if reset:
        try:
            client.delete_collection(name)
            logger.info(f"Deleted collection: {name}")
        except Exception:
            pass
    return client.get_or_create_collection(
        name=name,
        embedding_function=get_embed_fn(),
        metadata={"hnsw:space": "cosine"},
    )


# ══════════════════════════════════════════════════════════
#  INGEST — 3GPP
# ══════════════════════════════════════════════════════════

def ingest_3gpp(data_dir: Path, collection_name: str, reset: bool = False) -> int:
    data_dir.mkdir(parents=True, exist_ok=True)
    files = list(data_dir.glob("*.pdf")) + list(data_dir.glob("*.txt"))
    if not files:
        logger.warning(f"No files in {data_dir}")
        return 0

    logger.info(f"3GPP: {len(files)} files in {data_dir}")
    if not HAS_PDFPLUMBER:
        logger.warning("pdfplumber not installed — install with: pip install pdfplumber")
        logger.warning("Falling back to pypdf (heading detection may be weaker)")

    client     = get_chroma_client()
    collection = get_or_create_collection(client, collection_name, reset=reset)

    total = 0
    BATCH = 32
    b_docs, b_ids, b_metas = [], [], []

    def flush():
        nonlocal total
        if b_docs:
            collection.add(documents=b_docs, ids=b_ids, metadatas=b_metas)
            total += len(b_docs)
            b_docs.clear(); b_ids.clear(); b_metas.clear()

    def add(chunk: Dict, stem: str, idx: int) -> bool:
        cid = f"{stem}_chunk_{idx:06d}"
        try:
            if collection.get(ids=[cid])["ids"]:
                return False
        except Exception:
            pass
        meta = {
            "source":         chunk.get("doc_name", stem + ".pdf"),
            "source_type":    "3gpp",
            "spec_number":    chunk.get("spec_number",    ""),
            "release":        chunk.get("release",        ""),
            "version":        chunk.get("version",        ""),
            "vendor":         chunk.get("vendor",         "3GPP"),
            "section_number": chunk.get("section_number", ""),
            "section_title":  chunk.get("section_title",  ""),
            "chunk_type":     chunk.get("chunk_type",     "body"),
            "page":           int(chunk.get("page", 0)),
            "chunk_idx":      idx,
            "parameter_name": "",
            "mo_path":        "",
            "switch_name":    "",
            "counter_name":   "",
        }
        b_docs.append(chunk["text"]); b_ids.append(cid); b_metas.append(meta)
        return True

    for fp in tqdm(files, desc="Ingesting 3GPP"):
        spec_meta = parse_3gpp_filename(fp.name)
        spec_meta["doc_name"] = fp.name

        raw = extract_text(fp, use_pdfplumber=True)
        if not raw.strip():
            logger.warning(f"Empty: {fp.name}")
            continue

        idx = 0
        for chunk in chunk_3gpp(raw, spec_meta):
            if add(chunk, fp.stem, idx):
                idx += 1
            if len(b_docs) >= BATCH:
                flush()

    flush()
    logger.success(f"3GPP: {total} new chunks → '{collection_name}'")
    return total


# ══════════════════════════════════════════════════════════
#  INGEST — HedEx
# ══════════════════════════════════════════════════════════

def ingest_hedex(data_dir: Path, collection_name: str, reset: bool = False) -> int:
    data_dir.mkdir(parents=True, exist_ok=True)
    files = list(data_dir.glob("*.pdf")) + list(data_dir.glob("*.txt"))
    if not files:
        logger.warning(f"No files in {data_dir}")
        return 0

    logger.info(f"HedEx: {len(files)} files in {data_dir}")

    client     = get_chroma_client()
    collection = get_or_create_collection(client, collection_name, reset=reset)

    total = 0
    BATCH = 32
    b_docs, b_ids, b_metas = [], [], []

    def flush():
        nonlocal total
        if b_docs:
            collection.add(documents=b_docs, ids=b_ids, metadatas=b_metas)
            total += len(b_docs)
            b_docs.clear(); b_ids.clear(); b_metas.clear()

    def add(chunk: Dict, stem: str, idx: int) -> bool:
        cid = f"{stem}_chunk_{idx:06d}"
        try:
            if collection.get(ids=[cid])["ids"]:
                return False
        except Exception:
            pass
        meta = {
            "source":         chunk.get("doc_name", stem + ".pdf"),
            "source_type":    "hedex",
            "spec_number":    chunk.get("spec_number",    ""),
            "release":        chunk.get("release",        ""),
            "version":        chunk.get("version",        ""),
            "vendor":         chunk.get("vendor",         "Huawei"),
            "section_number": chunk.get("section_number", ""),
            "section_title":  chunk.get("section_title",  ""),
            "chunk_type":     chunk.get("chunk_type",     "body"),
            "page":           int(chunk.get("page", 0)),
            "chunk_idx":      idx,
            # HedEx-specific — critical for exact match search
            "parameter_name": chunk.get("parameter_name", ""),
            "mo_path":        chunk.get("mo_path",         ""),
            "switch_name":    chunk.get("switch_name",     ""),
            "counter_name":   chunk.get("counter_name",    ""),
            "default_value":  chunk.get("default_value",   ""),
            "value_range":    chunk.get("value_range",     ""),
            "feature_dep":    chunk.get("feature_dep",     ""),
        }
        b_docs.append(chunk["text"]); b_ids.append(cid); b_metas.append(meta)
        return True

    for fp in tqdm(files, desc="Ingesting HedEx"):
        hedex_meta = parse_hedex_filename(fp.name)
        hedex_meta["doc_name"] = fp.name

        # Use pypdf for HedEx — no pdfplumber needed
        raw = extract_text(fp, use_pdfplumber=False)
        if not raw.strip():
            logger.warning(f"Empty: {fp.name}")
            continue

        idx = 0
        for chunk in chunk_hedex(raw, hedex_meta):
            if add(chunk, fp.stem, idx):
                idx += 1
            if len(b_docs) >= BATCH:
                flush()

    flush()
    logger.success(f"HedEx: {total} new chunks → '{collection_name}'")
    return total


# ══════════════════════════════════════════════════════════
#  UNIFIED ENTRY POINT (backward compat)
# ══════════════════════════════════════════════════════════

def ingest_directory(data_dir: Path, collection_name: str, reset: bool = False) -> int:
    if "hedex" in collection_name.lower():
        return ingest_hedex(data_dir, collection_name, reset)
    return ingest_3gpp(data_dir, collection_name, reset)


# ══════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TelecomRAG production ingestion")
    parser.add_argument("--source", choices=["3gpp","hedex","both"], default="both")
    parser.add_argument("--reset",  action="store_true",
                        help="Wipe collection and re-ingest from scratch")
    args = parser.parse_args()

    if args.source in ("3gpp", "both"):
        ingest_3gpp(cfg.DATA_DIR_3GPP, cfg.COLLECTION_3GPP, reset=args.reset)
    if args.source in ("hedex", "both"):
        ingest_hedex(cfg.DATA_DIR_HEDEX, cfg.COLLECTION_HEDEX, reset=args.reset)
