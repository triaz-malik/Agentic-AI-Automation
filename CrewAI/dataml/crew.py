"""
hikmah-dataml/crew.py
3-agent CrewAI pipeline — MLOPS / DATA SCIENCE / ANALYTICS domain
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

logger = logging.getLogger("hikmah-dataml.crew")

RSS_FEEDS = [
    # MLOps · ML · Deep Learning · Data Science · Engineering
    "https://huggingface.co/blog/feed.xml",
    "https://www.kdnuggets.com/feed",
    "https://machinelearningmastery.com/blog/feed/",
    "https://eugeneyan.com/rss/",
    "https://towardsdatascience.com/feed",
    "https://www.databricks.com/feed",
    "https://netflixtechblog.com/feed",
    "https://engineering.fb.com/feed/",
    "https://aws.amazon.com/blogs/machine-learning/feed/",
    "https://magazine.sebastianraschka.com/feed",
    "https://huyenchip.com/feed.xml",
    "https://www.dataengineeringweekly.com/feed",
]

_DB_PATH = "dataml_news.db"
_LAST_FETCH = []  # latest fetch; dedup falls back to this

@tool("fetch_rss_dataml")
def fetch_rss_dataml(unused: str = "") -> str:
    """Fetch articles from MLOps/data science RSS feeds."""
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

@tool("dedup_dataml")
def dedup_dataml(articles_json: str = "") -> str:
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
    role="MLOps & Data Science Scout",
    goal=(
        "Fetch the latest MLOps/data science news, dedup, classify into: "
        "1) MLOps & Platforms  2) ML & Deep Learning  "
        "3) RAG Vector & Data Infrastructure  4) Cloud ML: Azure & AWS. "
        "Return JSON: {section_1:[...], section_2:[...], "
        "section_3:[...], section_4:[...], "
        "total_scanned:N, duplicates_removed:N}"
    ),
    backstory="Senior ML engineer covering MLOps platforms, data infrastructure, and cloud ML.",
    tools=[fetch_rss_dataml, dedup_dataml],
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
    goal="Output ONLY valid JSON. No markdown fences. Schema must match exactly.",
    backstory="Technical editor, zero tolerance for schema violations.",
    llm=SONNET,
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
    {"id":"s1","number":"01","title":"MLOps & Platforms",
     "eyebrow":"MLflow · Kubeflow · Feature Stores · Model Registry · CI/CD · Monitoring",
     "meta":"Databricks · MLflow · dbt · Weights & Biases · Evidently AI",
     "color_class":"s1",
     "entries":[{"title":"","url":"","source":"","date":"",
                 "summary":"","arch_impact":"","keywords":[],"vendors":[],"score":0}]},
    {"id":"s2","number":"02","title":"ML & Deep Learning",
     "eyebrow":"PyTorch · Fine-Tuning · Transformers · Computer Vision · Time-Series",
     "meta":"PyTorch · HuggingFace · scikit-learn · XGBoost · TensorFlow",
     "color_class":"s2","entries":[]},
    {"id":"s3","number":"03","title":"RAG, Vector & Data Infrastructure",
     "eyebrow":"RAG Architectures · Vector DBs · Embeddings · LangChain · LlamaIndex",
     "meta":"Weaviate · Pinecone · Chroma · LangChain · Apache Iceberg",
     "color_class":"s3","entries":[]},
    {"id":"s4","number":"04","title":"Cloud ML: Azure & AWS",
     "eyebrow":"Azure ML · Prompt Flow · SageMaker · Bedrock · Vertex AI · Cost",
     "meta":"Azure ML · SageMaker · Bedrock · Vertex AI · Cost Engineering",
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

    t1 = Task(description="Fetch MLOps/DS RSS, dedup, classify into 4 sections.",
              expected_output="JSON with 4 arrays + stats.", agent=scout)
    t2 = Task(description="Score, enrich, drop <60, keep top 6 per section. "
                          "Use arch_impact field for pipeline_insight content.",
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
