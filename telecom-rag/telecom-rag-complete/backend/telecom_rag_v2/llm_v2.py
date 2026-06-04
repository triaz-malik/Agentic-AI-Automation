"""
llm_v2.py — Step 4 (HedEx panel improvement)
===============================================
Improved prompt builders + LLM calls.
HedEx panel now renders structured output like the 3GPP panel:
  - Parameter cards with default/range/MO path
  - Confidence % badges
  - No hallucinated values

Drop into: C:\\Working\\Telecom RAG\\telecom-rag-complete\\backend\\
"""

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("telecom.llm.v2")

# ─────────────────────────────────────────────────────────────────────────────
# 3GPP PROMPT — unchanged from working version, kept for reference
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_3GPP_SYSTEM = """\
You are a 3GPP Technical Specifications expert.
Answer ONLY from the provided specification evidence chunks.
Never invent clause numbers — only cite §X.X.X if it appears in the evidence.
Use exact 3GPP terminology (RRC_CONNECTED, SRB1, etc.) without paraphrasing.
Distinguish normative SHALL from informative SHOULD/MAY.
Format: structured bullet points with citation refs inline."""

PROMPT_3GPP_TEMPLATE = """\
SPECIFICATION EVIDENCE:
{evidence}

QUERY: {query}

Answer from the evidence only. Structure your response as:

CALL DROP REASONS (3GPP RLF):
R1 [Reason] — [mechanism]. Ref: [TS XX.XXX §X.X.X from evidence]
R2 ...

KEY TIMERS (if relevant):
[Timer name] — [range, default]. Ref: [TS XX.XXX §X.X.X]

SUGGESTED PARAMETERS TO CHECK / TUNE:
- [parameter] — [what it controls]

If evidence is insufficient for any section, write: "Insufficient evidence for [section]."
Do NOT invent clause numbers not present in the evidence."""


# ─────────────────────────────────────────────────────────────────────────────
# HEDEX PROMPT — NEW structured format
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_HEDEX_SYSTEM = """\
You are a Huawei HedEx parameter documentation expert.
Answer ONLY from the provided HedEx evidence chunks.
Never invent parameter names, default values, or MO paths.
Only state default values and ranges if explicitly present in the evidence.
Format your response as structured parameter cards."""

PROMPT_HEDEX_TEMPLATE = """\
HEDEX EVIDENCE:
{evidence}

QUERY: {query}

Answer ONLY from the evidence. Structure your response as:

RELEVANT PARAMETERS:
P1 [ParameterName] | MO: [mo_path if in evidence] | Default: [value if in evidence] | Range: [range if in evidence]
   → [What this parameter controls — from description in evidence]

P2 ...

SWITCH PARAMETERS (if any AlgoSwitch or SW fields found):
- [SwitchName]: [bit position and meaning if in evidence]

TUNING GUIDANCE:
- [Specific actionable guidance derived from evidence only]

If any field (Default, Range, MO) is NOT in the evidence, write "—" for that field.
Never hallucinate values. Only output what is explicitly in the evidence."""


# ─────────────────────────────────────────────────────────────────────────────
# OPENAI PROMPT — 10-bullet explanation (no citations)
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_OPENAI_SYSTEM = """\
You are a senior 5G telecom consultant.
The user has already seen exact spec references from 3GPP and HedEx evidence.
Your role: provide a clean conceptual explanation for an operator engineer.
Never invent clause numbers or parameter names — this section is conceptual only.
Format: exactly 10 numbered bullets, each with a bold header and 1-2 sentence explanation."""

PROMPT_OPENAI_TEMPLATE = """\
3GPP EVIDENCE SUMMARY (for grounding — do NOT add citations beyond these):
{evidence_summary}

QUERY: {query}

Provide a 10-bullet conceptual explanation. Format:

01 **[Topic]**
   [1-2 sentence explanation]

02 **[Topic]**
   ...

(continue to 10)

Note at bottom: "Conceptual explanation only — clause numbers, defaults, and ranges are grounded in 3GPP evidence above."
"""


# ─────────────────────────────────────────────────────────────────────────────
# EVIDENCE FORMATTER
# ─────────────────────────────────────────────────────────────────────────────

def format_evidence_3gpp(chunks: List[Dict]) -> str:
    """Format 3GPP chunks for prompt injection."""
    if not chunks:
        return "No 3GPP specification evidence retrieved."
    parts = []
    for i, chunk in enumerate(chunks, 1):
        citation = chunk.get("citation", "3GPP")
        text = chunk.get("text", "").strip()
        score = chunk.get("rerank_score", chunk.get("hybrid_score", 0))
        parts.append(f"[E{i}] {citation} (score={score:.2f})\n{text[:800]}")
    return "\n\n---\n\n".join(parts)


def format_evidence_hedex(chunks: List[Dict]) -> str:
    """
    Format HedEx chunks for prompt injection.
    Extracts structured fields if present in metadata.
    """
    if not chunks:
        return "No HedEx evidence retrieved."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        text = chunk.get("text", "").strip()
        citation = chunk.get("citation", "HedEx")

        # Build structured field summary from metadata (from pdfplumber extraction)
        fields = []
        if meta.get("parameter_name"):
            fields.append(f"Parameter: {meta['parameter_name']}")
        if meta.get("mo_path"):
            fields.append(f"MO Path: {meta['mo_path']}")
        if meta.get("default_value"):
            unit = meta.get("unit", "")
            fields.append(f"Default: {meta['default_value']}{' ' + unit if unit else ''}")
        if meta.get("value_range"):
            unit = meta.get("unit", "")
            fields.append(f"Range: {meta['value_range']}{' ' + unit if unit else ''}")

        header = " | ".join(fields) if fields else citation
        parts.append(f"[E{i}] {header}\n{text[:600]}")

    return "\n\n---\n\n".join(parts)


def build_evidence_summary(chunks_3gpp: List[Dict], chunks_hedex: List[Dict]) -> str:
    """Build a short evidence summary for the OpenAI grounding prompt."""
    lines = []

    # Top 3 3GPP citations
    for chunk in chunks_3gpp[:3]:
        citation = chunk.get("citation", "3GPP")
        text_preview = chunk.get("text", "")[:150].replace("\n", " ")
        lines.append(f"• {citation}: {text_preview}")

    # Top 3 HedEx params
    for chunk in chunks_hedex[:3]:
        meta = chunk.get("metadata", {})
        param = meta.get("parameter_name", "")
        mo = meta.get("mo_path", "")
        default = meta.get("default_value", "")
        if param:
            entry = f"• HedEx param: {param}"
            if mo:
                entry += f" | MO: {mo}"
            if default:
                entry += f" | Default: {default}"
            lines.append(entry)

    return "\n".join(lines) if lines else "No evidence summary available."


# ─────────────────────────────────────────────────────────────────────────────
# CITATION VALIDATOR — strips hallucinated §X.Y numbers
# ─────────────────────────────────────────────────────────────────────────────

# Pattern: § followed by numbers not in evidence
HALLUCINATED_CLAUSE_RE = re.compile(r"§\s*\d+(?:\.\d+){2,}")

def validate_citations(
    llm_output: str,
    evidence_chunks: List[Dict],
) -> str:
    """
    Strip §X.X.X clause numbers from LLM output that don't appear in evidence.
    Legitimate clause numbers come from the evidence text or citation_prefix metadata.
    """
    # Collect legitimate clause numbers from evidence
    legitimate = set()
    for chunk in evidence_chunks:
        text = chunk.get("text", "")
        meta = chunk.get("metadata", {})
        # From chunk text
        for m in HALLUCINATED_CLAUSE_RE.finditer(text):
            legitimate.add(m.group().replace("§", "").replace(" ", "").strip())
        # From metadata
        sec_num = meta.get("section_number", "")
        if sec_num:
            legitimate.add(sec_num)

    def replace_clause(match: re.Match) -> str:
        num = match.group().replace("§", "").replace(" ", "").strip()
        if num in legitimate:
            return match.group()  # Keep legitimate
        return "[§ref]"  # Replace hallucinated with placeholder

    return HALLUCINATED_CLAUSE_RE.sub(replace_clause, llm_output)


# ─────────────────────────────────────────────────────────────────────────────
# LLM CALLER — Ollama (local) + OpenAI
# ─────────────────────────────────────────────────────────────────────────────

def call_ollama(
    prompt: str,
    system: str,
    model: str,
    base_url: str,
    timeout: int = 180,
) -> str:
    """Call local Ollama endpoint."""
    import httpx
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 1024,
            "num_ctx": 8192,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        },
    }
    try:
        t0 = time.time()
        resp = httpx.post(
            f"{base_url}/api/chat",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        elapsed = time.time() - t0
        content = resp.json()["message"]["content"]
        logger.info(f"Ollama {model}: {len(content)} chars in {elapsed:.1f}s")
        return content
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        return f"[LLM Error: {e}]"


def call_openai(
    prompt: str,
    system: str,
    api_key: str,
    model: str = "gpt-4o",
    max_tokens: int = 800,
) -> str:
    """Call OpenAI API."""
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        t0 = time.time()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        elapsed = time.time() - t0
        content = resp.choices[0].message.content
        logger.info(f"OpenAI {model}: {len(content)} chars in {elapsed:.1f}s")
        return content
    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        return f"[OpenAI Error: {e}]"


# ─────────────────────────────────────────────────────────────────────────────
# HIGH-LEVEL ANSWER BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def build_3gpp_answer(
    query: str,
    chunks: List[Dict],
    ollama_model: str,
    ollama_base_url: str,
) -> Tuple[str, float]:
    """
    Build 3GPP panel answer.
    Returns (answer_text, confidence_pct).
    """
    if not chunks:
        return "No 3GPP specification evidence found for this query.", 0.0

    evidence = format_evidence_3gpp(chunks)
    prompt = PROMPT_3GPP_TEMPLATE.format(evidence=evidence, query=query)

    raw = call_ollama(prompt, PROMPT_3GPP_SYSTEM, ollama_model, ollama_base_url)
    validated = validate_citations(raw, chunks)

    # Confidence = average of top-3 rerank scores, scaled to %
    top_scores = [c.get("rerank_score", c.get("hybrid_score", 0)) for c in chunks[:3]]
    avg_score = sum(top_scores) / len(top_scores) if top_scores else 0
    confidence = min(100.0, max(0.0, (avg_score + 5) / 10 * 100))

    return validated, confidence


def build_hedex_answer(
    query: str,
    chunks: List[Dict],
    ollama_model: str,
    ollama_base_url: str,
) -> Tuple[str, float]:
    """
    Build HedEx panel answer.
    Returns (answer_text, confidence_pct).
    """
    if not chunks:
        return "No HedEx parameter evidence found for this query.", 0.0

    evidence = format_evidence_hedex(chunks)
    prompt = PROMPT_HEDEX_TEMPLATE.format(evidence=evidence, query=query)

    raw = call_ollama(prompt, PROMPT_HEDEX_SYSTEM, ollama_model, ollama_base_url)

    # Confidence = based on Stage 0 exact hits + rerank scores
    exact_hits = sum(1 for c in chunks if c.get("stage") == 0)
    top_scores = [c.get("rerank_score", c.get("hybrid_score", 0)) for c in chunks[:3]]
    avg_score = sum(top_scores) / len(top_scores) if top_scores else 0
    confidence = min(100.0, max(0.0, (avg_score + 5) / 10 * 100))
    if exact_hits > 0:
        confidence = max(confidence, 75.0)  # Boost for exact parameter match

    return raw, confidence


def build_openai_answer(
    query: str,
    chunks_3gpp: List[Dict],
    chunks_hedex: List[Dict],
    api_key: str,
    model: str = "gpt-4o",
) -> str:
    """
    Build OpenAI general explanation panel.
    Grounded by evidence summary — no invented citations.
    """
    evidence_summary = build_evidence_summary(chunks_3gpp, chunks_hedex)
    prompt = PROMPT_OPENAI_TEMPLATE.format(
        evidence_summary=evidence_summary,
        query=query,
    )
    return call_openai(prompt, PROMPT_OPENAI_SYSTEM, api_key, model)
