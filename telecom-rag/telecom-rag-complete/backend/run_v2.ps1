# ============================================================
# run_v2.ps1 — Telecom RAG Agent v2 Launcher
# ============================================================
# One-click startup for the full v2 stack.
# Run from: C:\Working\Telecom RAG\telecom-rag-complete\backend\
#
# Usage:
#   .\run_v2.ps1              # Normal start
#   .\run_v2.ps1 -Step4       # Re-ingest HedEx with pdfplumber first
#   .\run_v2.ps1 -Step5       # Re-ingest 3GPP clause-aware first
#   .\run_v2.ps1 -Both        # Re-ingest both, then start
#   .\run_v2.ps1 -CheckOnly   # Just health-check, no start

param(
    [switch]$Step4,
    [switch]$Step5,
    [switch]$Both,
    [switch]$CheckOnly
)

# ── CONFIG ────────────────────────────────────────────────────────────────────
$PYTHON = "C:\Users\triaz\miniconda3_New\envs\rag\python.exe"
$BACKEND = "C:\Working\Telecom RAG\telecom-rag-complete\backend"
$ENV_FILE = "$BACKEND\.env.v2"

# ── ENVIRONMENT ───────────────────────────────────────────────────────────────
$env:KMP_DUPLICATE_LIB_OK = "TRUE"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Telecom Assistant :: AI RAG Agent v2" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── VERIFY FILES EXIST ────────────────────────────────────────────────────────
$required_files = @(
    "$BACKEND\api_v2.py",
    "$BACKEND\retriever_v2.py",
    "$BACKEND\llm_v2.py",
    "$BACKEND\query_expansion.py",
    "$BACKEND\hedex_ingestor_v2.py",
    "$BACKEND\ingestor_3gpp_v2.py",
)

Write-Host "Checking v2 files..." -ForegroundColor Yellow
$missing = $false
foreach ($f in $required_files) {
    if (Test-Path $f) {
        Write-Host "  [OK] $(Split-Path $f -Leaf)" -ForegroundColor Green
    } else {
        Write-Host "  [MISSING] $f" -ForegroundColor Red
        $missing = $true
    }
}

if ($missing) {
    Write-Host ""
    Write-Host "ERROR: Copy all v2 files from telecom_rag_v2\ into $BACKEND\" -ForegroundColor Red
    exit 1
}

# ── CHECK .ENV ────────────────────────────────────────────────────────────────
if (Test-Path $ENV_FILE) {
    Write-Host "  [OK] .env.v2 found — copy to .env to activate v2 settings" -ForegroundColor Yellow
} else {
    Write-Host "  [WARN] .env.v2 not found — using existing .env" -ForegroundColor Yellow
}

if ($CheckOnly) {
    Write-Host ""
    Write-Host "Check complete." -ForegroundColor Green
    exit 0
}

# ── VERIFY OLLAMA RUNNING ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "Checking Ollama..." -ForegroundColor Yellow
try {
    $ollamaResp = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  [OK] Ollama running" -ForegroundColor Green

    # Check if qwen2.5:32b is available
    $models = $ollamaResp.models | ForEach-Object { $_.name }
    if ($models -contains "qwen2.5:32b") {
        Write-Host "  [OK] qwen2.5:32b available" -ForegroundColor Green
    } elseif ($models -contains "qwen2.5:14b") {
        Write-Host "  [WARN] qwen2.5:32b not found — using qwen2.5:14b" -ForegroundColor Yellow
        Write-Host "         Run: ollama pull qwen2.5:32b   to download" -ForegroundColor Yellow
    } else {
        Write-Host "  [WARN] No qwen2.5 model found. Available: $($models -join ', ')" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  [ERROR] Ollama not running. Start it first:" -ForegroundColor Red
    Write-Host "          ollama serve" -ForegroundColor White
    Write-Host ""
    Write-Host "Starting Ollama in background..." -ForegroundColor Yellow
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Minimized
    Start-Sleep -Seconds 3
}

Set-Location $BACKEND

# ── STEP 4: HedEx pdfplumber re-ingestion ────────────────────────────────────
if ($Step4 -or $Both) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Magenta
    Write-Host "  STEP 4: HedEx pdfplumber ingestion (~20 min)" -ForegroundColor Magenta
    Write-Host "============================================================" -ForegroundColor Magenta
    Write-Host "This extracts structured parameter tables from HedEx PDFs." -ForegroundColor White
    Write-Host "Fixes: VonrAirTimeoutEpsfbTimer exact match, MO paths, defaults." -ForegroundColor White
    Write-Host ""

    $confirm = Read-Host "Proceed with HedEx re-ingestion? (y/n)"
    if ($confirm -eq "y") {
        Write-Host "Running hedex_ingestor_v2.py --reset..." -ForegroundColor Yellow
        & $PYTHON hedex_ingestor_v2.py --reset
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] HedEx ingestion complete" -ForegroundColor Green
        } else {
            Write-Host "  [ERROR] HedEx ingestion failed — check logs above" -ForegroundColor Red
        }
    } else {
        Write-Host "  Skipped." -ForegroundColor Yellow
    }
}

# ── STEP 5: 3GPP clause-aware re-ingestion ───────────────────────────────────
if ($Step5 -or $Both) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Magenta
    Write-Host "  STEP 5: 3GPP clause-aware re-ingestion (~45 min)" -ForegroundColor Magenta
    Write-Host "============================================================" -ForegroundColor Magenta
    Write-Host "Every chunk gets [TS 38.331 §5.3.5] prefix." -ForegroundColor White
    Write-Host "Fixes: citation accuracy ~50%% → ~85%%, no hallucinated §refs." -ForegroundColor White
    Write-Host ""

    $confirm = Read-Host "Proceed with 3GPP clause re-ingestion? (y/n)"
    if ($confirm -eq "y") {
        Write-Host "Running ingestor_3gpp_v2.py --reset..." -ForegroundColor Yellow
        & $PYTHON ingestor_3gpp_v2.py --reset
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] 3GPP ingestion complete" -ForegroundColor Green
        } else {
            Write-Host "  [ERROR] 3GPP ingestion failed — check logs above" -ForegroundColor Red
        }
    } else {
        Write-Host "  Skipped." -ForegroundColor Yellow
    }
}

# ── START API v2 ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Starting API v2..." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  UI:      http://localhost:8000/app" -ForegroundColor White
Write-Host "  Health:  http://localhost:8000/health" -ForegroundColor White
Write-Host "  Swagger: http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Stats:   http://localhost:8000/stats" -ForegroundColor White
Write-Host ""
Write-Host "  Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

& $PYTHON api_v2.py
