# TelecomRAG — Complete System

3GPP specs + Huawei HedEx + OpenAI fallback, running on your local GPU.

```
User query
    ↓
Agent orchestrator
    ↓          ↓           ↓
3GPP RAG   HedEx RAG   OpenAI fallback
(1st)      (2nd)       (3rd — only if local fails)
    ↓
Confidence gate  (score ≥ threshold → accept)
    ↓
Answer synthesiser
    ↓
Final answer + source label + pipeline trace
```

---

## Project Structure

```
telecom-rag-complete/
├── .env.example              ← copy to .env, fill in keys
├── requirements.txt
├── backend/
│   ├── config.py             ← all settings from .env
│   ├── ingestor.py           ← PDF → chunks → ChromaDB
│   ├── retriever.py          ← ANN search + BAAI reranker
│   ├── llm.py                ← Ollama local + OpenAI fallback
│   ├── orchestrator.py       ← 3-hop routing logic
│   └── api.py                ← FastAPI server
├── frontend/
│   └── index.html            ← spicy chatbot UI
├── data/
│   ├── 3gpp/                 ← drop 3GPP spec PDFs here
│   └── hedex/                ← drop HedEx PDFs here
└── scripts/
    └── start.sh              ← one-command startup
```

---

## Quick Start

### 1. Prerequisites

```bash
# Python 3.10+
python3 --version

# Ollama (for local LLM on RTX 5080)
# Install from https://ollama.com
ollama pull qwen2.5:14b
```

### 2. Install

```bash
cd telecom-rag-complete
python3 -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env:
#   OPENAI_API_KEY=sk-your-key    (only needed for fallback)
#   Adjust CONF_THRESHOLD_3GPP / CONF_THRESHOLD_HEDEX if needed
```

### 4. Add your documents

```bash
# Drop 3GPP spec PDFs (TS 38.xxx, TS 24.xxx, etc.)
cp /path/to/3gpp_specs/*.pdf data/3gpp/

# Drop Huawei HedEx PDFs
cp /path/to/hedex_docs/*.pdf data/hedex/
```

### 5. Ingest

```bash
cd backend
python ingestor.py --source both
# First run takes time — embedding all chunks on GPU
# Subsequent runs are resumable (skips already-ingested chunks)
```

### 6. Start

```bash
# Option A — one command
bash scripts/start.sh

# Option B — manual
ollama serve &              # in one terminal
cd backend
uvicorn api:app --port 8000 --reload
```

Open: **http://localhost:8000/app**

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/query` | Submit a RAG query |
| GET  | `/health` | Check Ollama + ChromaDB status |
| GET  | `/collections` | View chunk counts |
| POST | `/ingest?source=both` | Trigger ingestion |
| GET  | `/docs` | Swagger UI |

### /query request

```json
{ "query": "What are the VoNR call drop parameters?" }
```

### /query response

```json
{
  "query":        "What are the VoNR call drop parameters?",
  "answer":       "For VoNR call drop, 3GPP TS 24.301...",
  "source":       "3gpp",
  "score":        0.882,
  "pipeline_trace": [
    {"hop":1, "label":"3GPP hit",   "cls":"hit",  "detail":"score 0.88 → TS 24.301"},
    {"hop":2, "label":"HedEx skip", "cls":"miss", "detail":"not needed"},
    {"hop":3, "label":"OpenAI",     "cls":"miss", "detail":"not called"}
  ],
  "sources_tried": ["3gpp"]
}
```

---

## Tuning Guide

| Setting | File | Effect |
|---------|------|--------|
| `CONF_THRESHOLD_3GPP` | `.env` | Raise → stricter (more HedEx/OpenAI hits) |
| `CONF_THRESHOLD_HEDEX` | `.env` | Raise → more OpenAI fallback |
| `RETRIEVAL_TOP_K` | `.env` | More candidates before reranking |
| `RERANK_TOP_N` | `.env` | More context chunks sent to LLM |
| `CHUNK_SIZE` | `.env` | Smaller = more precise retrieval |
| `OLLAMA_MODEL` | `.env` | Swap to any model you have pulled |

---

## Re-ingesting after adding new docs

```bash
# Add new files to data/3gpp/ or data/hedex/, then:
python backend/ingestor.py --source 3gpp     # only new chunks added
python backend/ingestor.py --source 3gpp --reset   # wipe and re-ingest all
```

---

## Connecting the UI to a remote backend

Edit the first line of `frontend/index.html`:

```js
const API_BASE = 'http://your-server-ip:8000';
```

The UI also works in demo/offline mode — it shows mock answers
when the backend is unreachable.
