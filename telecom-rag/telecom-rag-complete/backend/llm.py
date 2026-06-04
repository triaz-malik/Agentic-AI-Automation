"""
llm.py — Production LLM layer

Answer format:
  3GPP:   4-20 lines, technical brief, exact evidence only
  HedEx:  4-20 lines, MO path + parameter + value, exact evidence only
  OpenAI: always exactly 10 bullets, EXPLANATION ONLY
          cannot output clause numbers / defaults / ranges / MO paths
          unless passed in confirmed evidence block
"""

from __future__ import annotations
import os
import ollama as _ollama
from loguru import logger
from openai import OpenAI

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from config import cfg


# ══════════════════════════════════════════════════════════
#  LOCAL PROMPT — 3GPP
# ══════════════════════════════════════════════════════════

def build_3gpp_prompt(query: str, chunks: list) -> str:
    ctx_parts = []
    for i, c in enumerate(chunks):
        meta_lines = []
        if c.spec_number:    meta_lines.append(f"Spec: {c.spec_number}")
        if c.section_number: meta_lines.append(f"Clause: §{c.section_number}")
        if c.metadata.get("section_title"): meta_lines.append(f"Title: {c.metadata['section_title']}")
        meta_str = " | ".join(meta_lines) if meta_lines else f"Source: {c.source_file}"
        ctx_parts.append(
            f"[Chunk {i+1} | {meta_str} | match={c.match_type}]\n{c.text}"
        )

    context = "\n\n---\n\n".join(ctx_parts)

    return f"""You are a senior 5G/LTE RAN engineer. Answer from retrieved 3GPP chunks ONLY.

STRICT RULES:
1. Only cite clause numbers that appear VERBATIM in chunk metadata or text above
2. Never write §X.Y, §N.M or any placeholder — if clause not in chunks write "ref not in retrieved docs"
3. Never invent parameter values or ranges — omit if not in chunks
4. No intro sentence. No "based on context" phrase. Answer directly.
5. Length: 4 lines minimum, 20 lines maximum. Adaptive to complexity.

FORMAT:
- **Spec:** TS XX.XXX §Y.Z  (only if exact ref is in chunks above)
- **Param/Timer:** name = value  (only if value is in chunks)
- **Procedure:** what the standard defines
- End with: **→ Related:** [1-2 lines on related clauses or parameters]

RETRIEVED 3GPP CHUNKS:
{context}

QUESTION: {query}

ANSWER:"""


# ══════════════════════════════════════════════════════════
#  LOCAL PROMPT — HedEx
# ══════════════════════════════════════════════════════════

def build_hedex_prompt(query: str, chunks: list) -> str:
    ctx_parts = []
    for i, c in enumerate(chunks):
        meta_lines = []
        if c.parameter_name:              meta_lines.append(f"Parameter: {c.parameter_name}")
        if c.mo_path:                     meta_lines.append(f"MO: {c.mo_path}")
        if c.metadata.get("default_value"):  meta_lines.append(f"Default: {c.metadata['default_value']}")
        if c.metadata.get("value_range"):    meta_lines.append(f"Range: {c.metadata['value_range']}")
        if c.metadata.get("switch_name"):    meta_lines.append(f"Switch: {c.metadata['switch_name']}")
        if c.metadata.get("feature_dep"):    meta_lines.append(f"Feature: {c.metadata['feature_dep']}")
        meta_str = " | ".join(meta_lines) if meta_lines else f"Source: {c.source_file}"
        ctx_parts.append(
            f"[Chunk {i+1} | {meta_str} | match={c.match_type}]\n{c.text}"
        )

    context = "\n\n---\n\n".join(ctx_parts)

    return f"""You are a senior Huawei RAN engineer. Answer from retrieved HedEx chunks ONLY.

STRICT RULES:
1. Only use MO paths that appear in chunk metadata or text above
2. Only use default values and ranges that appear in chunks — never guess
3. Never invent a 3GPP clause number — write "3GPP ref not in retrieved docs" if not found
4. No intro sentence. Answer directly.
5. Length: 4 lines minimum, 20 lines maximum. Adaptive to complexity.

FORMAT:
- **HedEx MO:** ManagedObject → parameterName  (only from chunk metadata)
- **Default:** value unit  (only if in chunks)
- **Range:** min–max  (only if in chunks)
- **Switch:** SWITCH_NAME  (only if in chunks)
- **Feature:** dependency  (only if in chunks)
- **Function:** what this parameter/KPI controls
- End with: **→ Related:** [1-2 lines on related HedEx parameters, counters, or KPIs]

RETRIEVED HEDEX CHUNKS:
{context}

QUESTION: {query}

ANSWER:"""


# ══════════════════════════════════════════════════════════
#  UNIFIED LOCAL PROMPT BUILDER
# ══════════════════════════════════════════════════════════

def build_prompt(query: str, chunks: list, label: str) -> str:
    if "hedex" in label.lower():
        return build_hedex_prompt(query, chunks)
    return build_3gpp_prompt(query, chunks)

def build_split_prompt(query: str, chunks: list, label: str, source: str) -> str:
    if source == "hedex":
        return build_hedex_prompt(query, chunks)
    return build_3gpp_prompt(query, chunks)


# ══════════════════════════════════════════════════════════
#  LOCAL — Ollama
# ══════════════════════════════════════════════════════════

def generate_local(prompt: str) -> str:
    try:
        response = _ollama.chat(
            model=cfg.OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature":    0.05,
                "num_predict":    1200,
                "top_p":          0.9,
                "repeat_penalty": 1.1,
            },
        )
        return response["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        raise RuntimeError(f"Local LLM unavailable: {e}")


# ══════════════════════════════════════════════════════════
#  OPENAI — EXPLANATION ONLY
#  Cannot output clause numbers, defaults, ranges, MO paths
#  unless confirmed evidence is passed in
# ══════════════════════════════════════════════════════════

_openai_client: OpenAI | None = None

def _get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        if not cfg.OPENAI_API_KEY or cfg.OPENAI_API_KEY.startswith("sk-your"):
            raise RuntimeError("OPENAI_API_KEY not set in .env")
        _openai_client = OpenAI(api_key=cfg.OPENAI_API_KEY)
    return _openai_client


def generate_openai(query: str, evidence_summary: str = "") -> str:
    """
    OpenAI general explanation.
    Role: explain the concept, procedure, and engineering rationale.
    Cannot invent citations — only reference confirmed evidence if provided.
    Always exactly 10 bullets + Related line.
    """
    # Build evidence block
    if evidence_summary.strip():
        evidence_block = f"""
CONFIRMED EVIDENCE FROM LOCAL RETRIEVAL (you MAY reference these):
{evidence_summary}

"""
    else:
        evidence_block = """
CONFIRMED EVIDENCE FROM LOCAL RETRIEVAL: None

"""

    system = f"""You are a senior 5G/LTE RAN engineer providing a general explanation.

YOUR ROLE: Explanation only — engineering concepts, procedures, and rationale.
{evidence_block}
STRICT OUTPUT RULES — no exceptions:
1. Give EXACTLY 10 bullet points using • symbol, one per line
2. Each bullet = one specific technical fact, concept, or engineering insight
3. You MAY reference items from the CONFIRMED EVIDENCE block above
4. You MUST NOT output any of the following unless they appear in CONFIRMED EVIDENCE:
   - Clause numbers (e.g. TS 38.331 §5.3.5)
   - Parameter default values (e.g. default: 2000ms)
   - Parameter value ranges (e.g. range: 0–7200ms)
   - MO paths (e.g. NRCELLSERVEXP → VonrAirTimeoutEpsfbTimer)
5. If you want to mention a parameter name as a concept — you may, but do NOT add values/ranges
6. No introduction line before the bullets
7. No conclusion line after the bullets
8. After exactly 10 bullets, add one final line:
   → Related: [1-2 sentences naming related features, KPIs, or parameters to check]"""

    try:
        resp = _get_openai().chat.completions.create(
            model       = cfg.OPENAI_MODEL,
            max_tokens  = 1200,
            temperature = 0.05,
            messages    = [
                {"role": "system", "content": system},
                {"role": "user",   "content": query},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        raise RuntimeError(f"OpenAI unavailable: {e}")
