#!/usr/bin/env bash
# ============================================================
#  start.sh — start the full TelecomRAG stack
#  Run from project root: bash scripts/start.sh
# ============================================================
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   TelecomRAG — Startup                   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Check .env
if [ ! -f ".env" ]; then
  echo "→ No .env found. Copying .env.example → .env"
  cp .env.example .env
  echo "  Edit .env and add your OPENAI_API_KEY, then re-run."
fi

# ── 2. Check venv
if [ ! -d "venv" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate
echo "→ Installing dependencies..."
pip install -q -r requirements.txt

# ── 3. Check Ollama
echo ""
echo "→ Checking Ollama..."
if ! command -v ollama &>/dev/null; then
  echo "  ⚠  Ollama not found. Install from https://ollama.com"
else
  if ! ollama list 2>/dev/null | grep -q "qwen2.5"; then
    echo "  → Pulling qwen2.5:14b (first time only — this takes a while)..."
    ollama pull qwen2.5:14b
  else
    echo "  ✓ qwen2.5:14b found"
  fi
fi

# ── 4. Start Ollama server in background if not running
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "→ Starting Ollama server..."
  ollama serve &
  sleep 3
else
  echo "  ✓ Ollama already running"
fi

# ── 5. Ingest documents if collections are empty
echo ""
echo "→ Checking collections..."
cd backend
python3 - <<'EOF'
import sys, chromadb
from pathlib import Path
sys.path.insert(0, '.')
from config import cfg

cfg.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
client = chromadb.PersistentClient(path=str(cfg.CHROMA_PERSIST_DIR))
cols = {c.name: c.count() for c in client.list_collections()}
print(f"  Collections: {cols}")

needs_ingest = []
if cols.get(cfg.COLLECTION_3GPP, 0) == 0: needs_ingest.append('3gpp')
if cols.get(cfg.COLLECTION_HEDEX, 0) == 0: needs_ingest.append('hedex')

if needs_ingest:
    print(f"  → Empty collections: {needs_ingest}")
    print(f"    Drop PDFs into data/3gpp/ and data/hedex/ then run:")
    print(f"    python backend/ingestor.py --source both")
else:
    print("  ✓ Collections ready")
EOF

# ── 6. Start FastAPI
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Starting TelecomRAG API on :8000        ║"
echo "║  Chat UI → http://localhost:8000/app     ║"
echo "║  API docs → http://localhost:8000/docs   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

uvicorn api:app --host 0.0.0.0 --port 8000 --reload
