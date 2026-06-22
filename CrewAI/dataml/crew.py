"""
hikmah-dataml/crew.py
3-agent CrewAI pipeline — MLOPS / DATA SCIENCE / ANALYTICS domain
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

logger = logging.getLogger("hikmah-dataml.crew")

RSS_FEEDS = [
    # MLOps / DS / Analytics
    "https://huggingface.co/blog/feed.xml",
    "https://www.kdnuggets.com/feed",
    "https://machinelearningmastery.com/blog/feed/",
    "https://eugeneyan.com/rss/",
    "https://towardsdatascience.com/feed",
    "https://www.databricks.com/feed",
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
    llm="anthropic/claude-haiku-4-5",
    verbose=True, max_iter=3,
)

analyst = Agent(
    role="ML Engineering Analyst",
    goal=(
        "Score each article 0-100 for production relevance to ML engineers. "
        "Drop score < 60. Write: summary (3 sentences), "
        "pipeline_insight (2 sentences — concrete implementation action or "
        "architecture implication, icon prefix: 🔧 MLOps 📐 ML/DL 🗄️ RAG/Data ☁️ Cloud), "
        "keywords (3-5), vendors (platform/tool names). Keep top 6 per section."
    ),
    backstory="Principal ML architect, AWS SAP-C02, Azure DP-100, GCC enterprise experience.",
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
