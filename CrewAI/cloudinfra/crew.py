"""
hikmah-cloudinfra/crew.py
3-agent CrewAI pipeline — CLOUD / CONTAINERS / DATABASES / EDGE domain
"""
import json, logging
from datetime import datetime
import feedparser
import socket
socket.setdefaulttimeout(8)  # bound each RSS fetch; dead feeds fail fast
from crewai import Agent, Crew, Process, Task
from crewai.tools import tool
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "hikmah-shared"))
from db_manager import filter_new, mark_seen

logger = logging.getLogger("hikmah-cloudinfra.crew")

RSS_FEEDS = [
    # Cloud platforms
    "https://aws.amazon.com/blogs/aws/feed/",
    "https://aws.amazon.com/blogs/containers/feed/",
    "https://techcommunity.microsoft.com/t5/azure-infrastructure-blog/rss",
    "https://cloud.google.com/blog/products/infrastructure/rss",
    "https://www.hashicorp.com/blog/rss",
    # Containers & Kubernetes
    "https://kubernetes.io/feed.xml",
    "https://www.docker.com/blog/rss/",
    "https://www.cncf.io/blog/rss/",
    "https://cilium.io/blog/rss",
    "https://argoproj.github.io/blog/index.xml",
    "https://grafana.com/blog/rss/",
    # Databases & storage
    "https://www.postgresql.org/about/newsarchive/rss/",
    "https://www.mongodb.com/blog/rss/",
    "https://redis.io/blog/rss/",
    "https://clickhouse.com/blog/rss",
    # Edge & CDN
    "https://blog.cloudflare.com/rss/",
    "https://www.fastly.com/blog/rss",
    "https://www.theregister.com/infrastructure/rss",
    "https://thenewstack.io/feed/",
]

_DB_PATH = "cloudinfra_news.db"
_LAST_FETCH = []  # latest fetch; dedup falls back to this

@tool("fetch_rss_cloud")
def fetch_rss_cloud(unused: str = "") -> str:
    """Fetch articles from cloud/infra/containers RSS feeds."""
    articles = []
    for url in RSS_FEEDS:
        try:
            p = feedparser.parse(url)
            src = p.feed.get("title", url)
            for e in p.entries[:15]:
                articles.append({
                    "title":     e.get("title","").strip(),
                    "url":       e.get("link","").strip(),
                    "summary":   e.get("summary","")[:500],
                    "published": e.get("published", datetime.utcnow().isoformat()),
                    "source":    src,
                })
        except Exception as ex:
            logger.warning(f"RSS error {url}: {ex}")
    _LAST_FETCH.clear(); _LAST_FETCH.extend(articles)
    return json.dumps(articles)

@tool("dedup_cloud")
def dedup_cloud(articles_json: str = "") -> str:
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

scout = Agent(
    role="Cloud Infrastructure Scout",
    goal=(
        "Fetch the latest cloud/infra/containers/edge news, dedup, classify into: "
        "1) Cloud Platforms  2) Containers & Kubernetes  "
        "3) Databases & Storage  4) Edge CDN & Telecom Cloud. "
        "Return JSON: {section_1:[...], section_2:[...], "
        "section_3:[...], section_4:[...], "
        "total_scanned:N, duplicates_removed:N}"
    ),
    backstory="Senior cloud architect covering AWS, Azure, GCP, containers, and edge compute.",
    tools=[fetch_rss_cloud, dedup_cloud],
    llm="anthropic/claude-haiku-4-5",
    verbose=True, max_iter=3,
)

analyst = Agent(
    role="Platform Engineering Analyst",
    goal=(
        "Score each article 0-100 for production relevance to platform engineers "
        "and cloud architects, with extra weight for GCC/telecom relevance. "
        "Drop score < 60. Write: summary (3 sentences), "
        "infra_impact (2 sentences — concrete operational or cost implication), "
        "keywords (3-5 tags), vendors (platform/tool names). "
        "Icon prefix by section: ☁️ Cloud 📦 Containers 🗃️ Database 🌐 Edge. "
        "Keep top 6 per section by score."
    ),
    backstory="Principal platform engineer, AWS SAP-C02, Kubernetes certified, GCC enterprise experience.",
    llm="anthropic/claude-sonnet-4-6",
    verbose=True, max_iter=4,
)

publisher = Agent(
    role="Intelligence Publisher",
    goal="Output ONLY valid JSON. No markdown fences. Schema must match exactly.",
    backstory="Technical editor, zero tolerance for schema violations.",
    llm="anthropic/claude-sonnet-4-6",
    verbose=True, max_iter=2,
)

SCHEMA = """
{
  "issue_number": <int>, "issue_date": "<str>",
  "volume": "I", "edition": "Global Edition",
  "stats": {"sources_scanned":<int>,"duplicates_removed":<int>,
            "articles_published":24,"dedup_db_total":<int>},
  "ticker_items": ["<str>", ...],
  "sections": [
    {"id":"s1","number":"01","title":"Cloud Platforms",
     "eyebrow":"AWS · Azure · GCP · Multi-Cloud · IaC · FinOps · Serverless",
     "meta":"AWS · Microsoft Azure · Google Cloud · HashiCorp · Pulumi",
     "color_class":"s1",
     "entries":[{"title":"","url":"","source":"","date":"",
                 "summary":"","arch_impact":"","keywords":[],"vendors":[],"score":0}]},
    {"id":"s2","number":"02","title":"Containers & Kubernetes",
     "eyebrow":"Docker · Kubernetes · Helm · Service Mesh · WASM · OCI",
     "meta":"Docker · CNCF · Istio · Cilium · Argo · Crossplane",
     "color_class":"s2","entries":[]},
    {"id":"s3","number":"03","title":"Databases & Storage",
     "eyebrow":"PostgreSQL · MongoDB · Redis · ClickHouse · S3 · Object Storage",
     "meta":"PostgreSQL · MongoDB · Redis · ClickHouse · Apache Arrow",
     "color_class":"s3","entries":[]},
    {"id":"s4","number":"04","title":"Edge, CDN & Telecom Cloud",
     "eyebrow":"Edge Compute · CDN · WASM at Edge · MEC · Telecom Cloud · vRAN",
     "meta":"Cloudflare · Fastly · AWS Outposts · Azure Edge · MEC",
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

    t1 = Task(description="Fetch cloud/infra RSS, dedup, classify into 4 sections.",
              expected_output="JSON with 4 arrays + stats.", agent=scout)
    t2 = Task(description="Score, enrich, drop <60, keep top 6 per section. "
                          "Use arch_impact field for infra_impact content.",
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
