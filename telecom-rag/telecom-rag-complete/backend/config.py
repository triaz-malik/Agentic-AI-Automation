"""
config.py — loads all settings from .env
Import `cfg` anywhere: from config import cfg
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Paths
    DATA_DIR_3GPP        = Path(os.getenv("DATA_DIR_3GPP",   "./data/3gpp"))
    DATA_DIR_HEDEX       = Path(os.getenv("DATA_DIR_HEDEX",  "./data/hedex"))
    CHROMA_PERSIST_DIR   = Path(os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"))

    # Collections
    COLLECTION_3GPP      = os.getenv("COLLECTION_3GPP",  "telecom_3gpp")
    COLLECTION_HEDEX     = os.getenv("COLLECTION_HEDEX",  "telecom_hedex")

    # Embedding / Reranker
    EMBED_MODEL          = os.getenv("EMBED_MODEL",    "BAAI/bge-large-en-v1.5")
    RERANKER_MODEL       = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-large")

    # Ollama
    OLLAMA_BASE_URL      = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL         = os.getenv("OLLAMA_MODEL",    "qwen2.5:14b")
    OLLAMA_TIMEOUT       = int(os.getenv("OLLAMA_TIMEOUT", 120))

    # Confidence thresholds
    CONF_THRESHOLD_3GPP  = float(os.getenv("CONF_THRESHOLD_3GPP", 0.60))
    CONF_THRESHOLD_HEDEX = float(os.getenv("CONF_THRESHOLD_HEDEX", 0.60))

    # Retrieval
    RETRIEVAL_TOP_K      = int(os.getenv("RETRIEVAL_TOP_K", 10))
    RERANK_TOP_N         = int(os.getenv("RERANK_TOP_N",    3))

    # Chunking
    CHUNK_SIZE           = int(os.getenv("CHUNK_SIZE",    600))
    CHUNK_OVERLAP        = int(os.getenv("CHUNK_OVERLAP", 100))

    # OpenAI
    OPENAI_API_KEY       = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL         = os.getenv("OPENAI_MODEL",   "gpt-4o")
    OPENAI_MAX_TOKENS    = int(os.getenv("OPENAI_MAX_TOKENS", 800))

    # Server
    API_HOST             = os.getenv("API_HOST", "0.0.0.0")
    API_PORT             = int(os.getenv("API_PORT", 8000))

cfg = Config()
