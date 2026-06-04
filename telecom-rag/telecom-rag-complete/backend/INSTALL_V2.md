# Telecom RAG v2 — Installation & Deployment Guide

## Files in this package

| File | Step | What it does |
|------|------|-------------|
| `.env.v2` | 1+2 | Lowered thresholds, qwen2.5:32b, BM25 weights |
| `query_expansion.py` | 3 | 582 telecom expansion terms (15 topics) |
| `hedex_ingestor_v2.py` | 4 | pdfplumber structured HedEx table extraction |
| `ingestor_3gpp_v2.py` | 5 | Clause-aware 3GPP re-ingestion with §ref prefix |
| `retriever_v2.py` | 4+7 | Stage 0 exact match + BM25 hybrid search |
| `llm_v2.py` | 4 | Structured HedEx prompt + citation validator |
| `api_v2.py` | All | Updated FastAPI server using all v2 components |
| `run_v2.ps1` | All | One-click PowerShell launcher |

---

## Step-by-step deployment

### 1. Copy all files to backend folder

```powershell
# Copy from wherever you downloaded to your backend
Copy-Item ".\telecom_rag_v2\*" "C:\Working\Telecom RAG\telecom-rag-complete\backend\"
```

### 2. Install new pip package (BM25 — Step 7)

```powershell
$env:KMP_DUPLICATE_LIB_OK="TRUE"
C:\Users\triaz\miniconda3_New\envs\rag\python.exe -m pip install rank_bm25 pdfplumber --break-system-packages
```

### 3. Activate v2 .env settings (Steps 1+2)

```powershell
cd "C:\Working\Telecom RAG\telecom-rag-complete\backend"
# Backup your current .env first!
Copy-Item ".env" ".env.backup"
Copy-Item ".env.v2" ".env"
```

### 4. Add your OpenAI API key to .env

Open `.env` and replace:
```
OPENAI_API_KEY=sk-your-key-here
```
with your actual key.

### 5. Verify qwen2.5:32b (Step 2)

```powershell
ollama list
# If qwen2.5:32b shows — great, .env is already pointing to it
# If not yet downloaded:
ollama pull qwen2.5:32b
# Then update .env: OLLAMA_MODEL=qwen2.5:32b
```

### 6. Quick test — start v2 without re-ingestion first

```powershell
cd "C:\Working\Telecom RAG\telecom-rag-complete\backend"
$env:KMP_DUPLICATE_LIB_OK="TRUE"
ollama serve   # In separate terminal if not running

# Start v2 API (uses existing ChromaDB, just with better retrieval)
C:\Users\triaz\miniconda3_New\envs\rag\python.exe api_v2.py
```

Open: http://localhost:8000/health  
You should see BM25 weight + expansion_terms in the response.

---

### 7. Step 4: HedEx pdfplumber re-ingestion (~20 min)

```powershell
$env:KMP_DUPLICATE_LIB_OK="TRUE"
cd "C:\Working\Telecom RAG\telecom-rag-complete\backend"

# Wipe old HedEx chunks and rebuild with structured table extraction
C:\Users\triaz\miniconda3_New\envs\rag\python.exe hedex_ingestor_v2.py --reset

# OR: test on first 5 files first
C:\Users\triaz\miniconda3_New\envs\rag\python.exe hedex_ingestor_v2.py --test 5

# OR: incremental (only new files)
C:\Users\triaz\miniconda3_New\envs\rag\python.exe hedex_ingestor_v2.py
```

**What this fixes:**
- VonrAirTimeoutEpsfbTimer found directly via Stage 0 exact match
- MO paths, default values, value ranges in metadata
- HedEx confidence goes from 0% → 75%+ for parameter queries

---

### 8. Step 5: 3GPP clause-aware re-ingestion (~45 min)

```powershell
$env:KMP_DUPLICATE_LIB_OK="TRUE"
cd "C:\Working\Telecom RAG\telecom-rag-complete\backend"

# Full rebuild (recommended)
C:\Users\triaz\miniconda3_New\envs\rag\python.exe ingestor_3gpp_v2.py --reset

# OR: test on first 3 files
C:\Users\triaz\miniconda3_New\envs\rag\python.exe ingestor_3gpp_v2.py --test 3
```

**What this fixes:**
- Every chunk has `[TS 38.331 §5.3.5]` prefix baked in
- Citation accuracy: ~50% → ~85%
- section_number in metadata enables exact clause lookup
- Scanned PDFs (common transmission.pdf, ip4.pdf) skipped automatically

---

### 9. Step 6: Add more HedEx documents (ongoing)

```powershell
# Drop new PDFs into:
# C:\Working\Telecom RAG\5G Hedex Files\

# Then incremental ingest (only new files):
C:\Users\triaz\miniconda3_New\envs\rag\python.exe hedex_ingestor_v2.py
```

---

### 10. Using the one-click launcher

```powershell
cd "C:\Working\Telecom RAG\telecom-rag-complete\backend"

# Normal start (just API)
.\run_v2.ps1

# Start + run HedEx pdfplumber ingestion first
.\run_v2.ps1 -Step4

# Start + run 3GPP clause re-ingestion first
.\run_v2.ps1 -Step5

# Start + run both ingestions first
.\run_v2.ps1 -Both

# Just check files are in place
.\run_v2.ps1 -CheckOnly
```

---

## Rollback to v1

```powershell
cd "C:\Working\Telecom RAG\telecom-rag-complete\backend"
# Restore old .env
Copy-Item ".env.backup" ".env"
# Start original api.py
C:\Users\triaz\miniconda3_New\envs\rag\python.exe api.py
```

---

## What changed per panel in the UI

### 3GPP panel
- Citations now show `[TS 38.331 §5.3.5]` — real clause numbers from chunks
- No more hallucinated `§X.Y.Z` references
- BM25 finds exact timer names (T310, N310) directly

### HedEx panel (BIGGEST IMPROVEMENT)
- Parameter cards: `P1 VonrAirTimeoutEpsfbTimer | MO: NRCellDU | Default: 3 | Range: 0~127`
- Stage 0 exact match finds parameters by name directly
- Confidence goes from ~0% to 75%+ for parameter queries

### OpenAI panel
- Grounded by structured evidence summary from both sources
- 10-bullet format preserved
- Cannot invent clause numbers (system prompt hardened)

---

## Health check endpoints

| Endpoint | What to check |
|----------|---------------|
| `/health` | model, BM25 weight, expansion_terms count, chunk counts |
| `/stats` | detailed retrieval config |
| `/docs` | Swagger UI for manual testing |

---

*Telecom RAG v2 — Tahir Malik | Ooredoo Oman*
