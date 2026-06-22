"""
hikmah-shared/db_manager.py
SHA-256 dedup — used by all 3 HIKMAH projects.
Each project points to its own DB file via DB_PATH env var.
"""
import hashlib, sqlite3, logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

logger = logging.getLogger("hikmah.db")

def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS seen_articles (
        url_hash TEXT PRIMARY KEY, title TEXT,
        url TEXT, section TEXT, inserted_at TEXT)""")
    conn.commit()
    return conn

def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()

def is_seen(url: str, db_path: str) -> bool:
    conn = _connect(db_path)
    row = conn.execute("SELECT 1 FROM seen_articles WHERE url_hash=?",
                       (url_hash(url),)).fetchone()
    conn.close()
    return row is not None

def mark_seen(url: str, title: str, section: str, db_path: str) -> None:
    conn = _connect(db_path)
    conn.execute("INSERT OR IGNORE INTO seen_articles VALUES (?,?,?,?,?)",
                 (url_hash(url), title, url, section,
                  datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def filter_new(articles: list, db_path: str) -> tuple:
    new, dupes = [], 0
    for a in articles:
        if is_seen(a["url"], db_path): dupes += 1
        else: new.append(a)
    return new, dupes

def purge_old(db_path: str, ttl_days: int = 90) -> int:
    conn = _connect(db_path)
    cutoff = (datetime.utcnow() - timedelta(days=ttl_days)).isoformat()
    cur = conn.execute("DELETE FROM seen_articles WHERE inserted_at<?", (cutoff,))
    removed = cur.rowcount
    conn.commit(); conn.close()
    logger.info(f"Purged {removed} entries older than {ttl_days}d from {db_path}")
    return removed

def get_stats(db_path: str) -> dict:
    conn = _connect(db_path)
    total = conn.execute("SELECT COUNT(*) FROM seen_articles").fetchone()[0]
    conn.close()
    return {"total": total}
