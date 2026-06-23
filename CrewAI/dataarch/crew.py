"""
hikmah-dataarch/crew.py
3-agent CrewAI pipeline — DATABASES / BIG DATA / GPUs / APIS domain
"""
import json, logging
from datetime import datetime
import feedparser
import socket
socket.setdefaulttimeout(8)  # bound each RSS fetch; dead feeds fail fast
from crewai import Agent, Crew, LLM, Process, Task
from crewai.tools import tool
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "hikmah-shared"))
from db_manager import filter_new, mark_seen

logger = logging.getLogger("hikmah-dataarch.crew")

RSS_FEEDS = [
    # Database Architecture
    "https://neon.tech/blog/rss",
    "https://supabase.com/blog/rss",
    "https://www.pingcap.com/blog/rss",
    "https://www.cockroachlabs.com/blog/rss",
    "https://planetscale.com/blog/rss.xml",
    "https://aws.amazon.com/blogs/database/feed/",
    # Big Data & Streaming
    "https://www.databricks.com/feed",
    "https://estuary.dev/blog/rss.xml",
    "https://www.decodable.co/blog/rss.xml",
    "https://www.dataengineeringweekly.com/feed",
    "https://www.getdbt.com/blog/rss.xml",
    "https://www.tinybird.co/blog-posts/rss.xml",
    "https://materializedview.io/feed",
    "https://seattledataguy.substack.com/feed",
    # GPUs & Compute
    "https://developer.nvidia.com/blog/feed",
    "https://semianalysis.com/feed/",
    "https://www.together.ai/blog/rss.xml",
    # APIs & Automation
    "https://blog.postman.com/feed/",
    "https://konghq.com/feed",
    "https://blog.bytebytego.com/feed",
    "https://martinfowler.com/feed.atom",
]

_DB_PATH = "dataarch_news.db"
_LAST_FETCH = []  # latest fetch; dedup falls back to this

@tool("fetch_rss_dataarch")
def fetch_rss_dataarch(unused: str = "") -> str:
    """Fetch articles from DB/BigData/GPU/API RSS feeds."""
    articles = []
    for url in RSS_FEEDS:
        try:
            p = feedparser.parse(url)
            src = p.feed.get("title", url)
            for e in p.entries[:4]:
                articles.append({
                    "title":     e.get("title","").strip(),
                    "url":       e.get("link","").strip(),
                    "summary":   e.get("summary","")[:300],
                    "published": e.get("published", datetime.utcnow().isoformat()),
                    "source":    src,
                })
        except Exception as ex:
            logger.warning(f"RSS error {url}: {ex}")
    _LAST_FETCH.clear(); _LAST_FETCH.extend(articles)
    return json.dumps(articles)

@tool("dedup_dataarch")
def dedup_dataarch(articles_json: str = "") -> str:
    """Remove already-seen articles via SHA-256 dedup."""
    articles = None
    if articles_json:
        try:
            parsed = json.loads(articles_json)
            if isinstance(parsed, list):
                articles = parsed
        except Exception:
            articles = None
    if not articles:
        articles = list(_LAST_FETCH)
    new, dupes = filter_new(articles, _DB_PATH)
    return json.dumps({"new_articles": new,
                       "duplicates_removed": dupes,
                       "total_scanned": len(articles)})


# Explicit token budgets so large JSON payloads are not truncated.
HAIKU  = LLM(model="anthropic/claude-haiku-4-5",  max_tokens=16000)
SONNET = LLM(model="anthropic/claude-sonnet-4-6", max_tokens=16000)

scout = Agent(
    role="Data Architecture Scout",
    goal=(
        "Fetch the latest DB/BigData/GPU/API news, dedup, classify into: "
        "1) Database Architecture  2) Big Data & Streaming  "
        "3) GPUs & Compute  4) APIs & Automation. "
        "Return JSON: {section_1:[...], section_2:[...], "
        "section_3:[...], section_4:[...], "
        "total_scanned:N, duplicates_removed:N}"
    ),
    backstory="Senior systems architect covering databases, data engineering, GPU infrastructure, and API design.",
    tools=[fetch_rss_dataarch, dedup_dataarch],
    llm=HAIKU,
    verbose=True, max_iter=3,
)

analyst = Agent(
    role="Principal Analyst & Technology Strategist",
    goal=(
        "Audience: SENIOR engineers, principal architects, technical consultants and "
        "executives (CTO/VP Engineering). Assume deep expertise -- never explain "
        "fundamentals or write for juniors. "
        "Score each article 0-100 for strategic and technical significance to that "
        "audience; DROP anything below 65. For each kept item write: "
        "summary -- exactly 3 tight sentences that lead with what actually changed and "
        "why it is significant, with no filler and no 101-level explanation. "
        "arch_impact -- 2-3 sentences of decision-grade insight fusing the architectural "
        "implication with the strategic and business consequence: adoption timing, cost, "
        "risk, competitive positioning, and the concrete move a senior leader should make. "
        "This is the headline takeaway; make it sharp, specific and non-obvious. "
        "Extract 3-5 real technical keywords and the vendors named. "
        "Keep only the strongest 6 entries per section, ordered by score."
    ),
    backstory=(
        "A principal architect and technology strategist who briefs CTOs and senior "
        "engineering leaders, turning raw technical developments into architecture "
        "decisions and business strategy."
    ),
    llm=SONNET,
    verbose=True, max_iter=4,
)

publisher = Agent(
    role="Intelligence Publisher",
    goal="Output ONLY valid JSON. No markdown fences.",
    backstory="Technical editor, zero tolerance for schema violations.",
    llm=SONNET,
    verbose=True, max_iter=2,
)

SCHEMA = """
{
  "issue_number":<int>,"issue_date":"<str>","volume":"I","edition":"Global Edition",
  "stats":{"sources_scanned":<int>,"duplicates_removed":<int>,"articles_published":24,"dedup_db_total":<int>},
  "ticker_items":["<str>",...],
  "sections":[
    {"id":"s1","number":"01","title":"Database Architecture",
     "eyebrow":"Serverless DB · HTAP · NewSQL · Multi-Model · Schema Design · Replication",
     "meta":"Neon · Supabase · TiDB · CockroachDB · Turso · PlanetScale",
     "color_class":"s1","entries":[{"title":"","url":"","source":"","date":"","summary":"","arch_impact":"","keywords":[],"vendors":[],"score":0}]},
    {"id":"s2","number":"02","title":"Big Data & Streaming",
     "eyebrow":"Kafka · Flink · Spark · Delta Lake · Data Lakehouse · CDC",
     "meta":"Apache Kafka · Flink · Spark · Databricks · Confluent",
     "color_class":"s2","entries":[]},
    {"id":"s3","number":"03","title":"GPUs & Compute",
     "eyebrow":"NVIDIA · AMD · Groq · Inference Chips · CUDA · Inference Serving",
     "meta":"NVIDIA · AMD · Groq · Cerebras · vLLM · TensorRT-LLM",
     "color_class":"s3","entries":[]},
    {"id":"s4","number":"04","title":"APIs & Automation",
     "eyebrow":"REST · GraphQL · gRPC · API Gateway · Workflow Automation · Temporal",
     "meta":"Stripe · Kong · Temporal · n8n · GraphQL · OpenAPI",
     "color_class":"s4","entries":[]}
  ]
}
"""

import re as _re

def _extract_json(text: str) -> dict:
    """Pull the first balanced JSON object from an LLM response (fenced or prose)."""
    s = (text or "").strip()
    m = _re.search(r"```(?:json)?\s*(.*?)```", s, _re.DOTALL)
    if m:
        s = m.group(1).strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("no JSON object in model output")
    return json.JSONDecoder().raw_decode(s, start)[0]


def run_crew(issue_number: int, issue_date: str, db_path: str) -> dict:
    global _DB_PATH
    _DB_PATH = db_path
    t1 = Task(description="Fetch DB/BigData/GPU/API RSS, dedup, classify into 4 sections.",
              expected_output="JSON with 4 arrays + stats.", agent=scout)
    t2 = Task(description="Score, enrich, drop <60, keep top 6 per section.",
              expected_output="Enriched JSON, 6 entries per section.",
              agent=analyst, context=[t1])
    t3 = Task(description=f"Compile payload. issue_number={issue_number}, "
                          f"issue_date={issue_date}. Schema:\n{SCHEMA}",
              expected_output="Valid JSON only.", agent=publisher, context=[t2])
    result = Crew(agents=[scout, analyst, publisher],
                  tasks=[t1, t2, t3],
                  process=Process.sequential, verbose=True).kickoff()
    raw = result.raw if hasattr(result, "raw") else str(result)
    payload = _extract_json(raw)
    for sec in payload.get("sections", []):
        for e in sec.get("entries", []):
            mark_seen(e["url"], e["title"], sec["title"], db_path)
    return payload
