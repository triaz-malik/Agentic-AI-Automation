"""
hikmah-intelligence/crew.py
3-agent CrewAI pipeline — AI / AGENTIC / LLM domain
"""
import json, logging
from datetime import datetime
import feedparser
from crewai import Agent, Crew, Process, Task
from crewai.tools import tool
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "hikmah-shared"))
from db_manager import filter_new, mark_seen

logger = logging.getLogger("hikmah-intelligence.crew")

RSS_FEEDS = [
    "https://www.anthropic.com/news/rss",
    "https://openai.com/blog/rss",
    "https://deepmind.google/blog/rss",
    "https://ai.meta.com/blog/rss",
    "https://mistral.ai/news/rss",
    "https://huggingface.co/blog/feed.xml",
    "https://www.deeplearning.ai/the-batch/rss",
    "https://newsletter.theaiedge.io/feed",
    "https://www.interconnects.ai/feed",
    "https://aiweekly.co/issues.rss",
    "https://arxiv.org/rss/cs.AI",
    "https://arxiv.org/rss/cs.LG",
    "https://techcrunch.com/tag/artificial-intelligence/feed/",
    "https://www.wired.com/feed/tag/artificial-intelligence/rss",
    "https://venturebeat.com/category/ai/feed/",
]

_DB_PATH = "ai_news.db"

@tool("fetch_rss_ai")
def fetch_rss_ai(unused: str = "") -> str:
    """Fetch articles from AI/ML/agentic RSS feeds."""
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
    return json.dumps(articles)

@tool("dedup_ai")
def dedup_ai(articles_json: str) -> str:
    """Remove already-seen articles via SHA-256 dedup."""
    articles = json.loads(articles_json)
    new, dupes = filter_new(articles, _DB_PATH)
    return json.dumps({"new_articles": new,
                       "duplicates_removed": dupes,
                       "total_scanned": len(articles)})

scout = Agent(
    role="AI Intelligence Scout",
    goal=(
        "Fetch the latest AI/ML/agentic news, remove duplicates, classify into: "
        "1) Models & Research  2) Agentic & Tools  "
        "3) Industry & Deployments  4) Policy Safety & Infrastructure. "
        "Return JSON: {section_1:[...], section_2:[...], "
        "section_3:[...], section_4:[...], "
        "total_scanned:N, duplicates_removed:N}"
    ),
    backstory="Senior AI research journalist covering frontier models and agentic systems.",
    tools=[fetch_rss_ai, dedup_ai],
    llm="claude-haiku-4-5",
    verbose=True, max_iter=3,
)

analyst = Agent(
    role="AI Research Analyst",
    goal=(
        "Score each article 0-100 for strategic importance to GCC AI leads. "
        "Drop score < 60. Write: summary (3 sentences), "
        "strategic_signal (2 sentences — concrete implication for AI architects), "
        "keywords (3-5), vendors/orgs (names). Keep top 6 per section."
    ),
    backstory="AI solutions architect with GCC enterprise deployment experience.",
    llm="claude-sonnet-4-6",
    verbose=True, max_iter=4,
)

publisher = Agent(
    role="Intelligence Publisher",
    goal="Output ONLY valid JSON matching schema. No markdown fences.",
    backstory="Technical editor, zero tolerance for schema violations.",
    llm="claude-sonnet-4-6",
    verbose=True, max_iter=2,
)

SCHEMA = """
{
  "issue_number": <int>, "issue_date": "<str>",
  "volume": "I", "edition": "GCC & Global Edition",
  "stats": {"sources_scanned":<int>,"duplicates_removed":<int>,
            "articles_published":24,"dedup_db_total":<int>},
  "ticker_items": ["<str>", ...],
  "sections": [
    {"id":"s1","number":"01","title":"Models & Research",
     "eyebrow":"Foundation Models · Benchmarks · Architecture · Multimodal",
     "meta":"Anthropic · OpenAI · Google DeepMind · Meta · Mistral",
     "color_class":"s1",
     "entries":[{"title":"","url":"","source":"","date":"",
                 "summary":"","arch_impact":"","keywords":[],"vendors":[],"score":0}]},
    {"id":"s2","number":"02","title":"Agentic & Tools",
     "eyebrow":"Agentic Frameworks · MCP · Orchestration · CrewAI · LangGraph",
     "meta":"Multi-Agent Systems · Workflow Automation · Developer Tooling",
     "color_class":"s2","entries":[]},
    {"id":"s3","number":"03","title":"Industry & Deployments",
     "eyebrow":"Enterprise AI · GCC Deployments · Telecom AI · Healthcare",
     "meta":"Real-World Implementations · ROI · Use Cases · MENA Region",
     "color_class":"s3","entries":[]},
    {"id":"s4","number":"04","title":"Policy, Safety & Infrastructure",
     "eyebrow":"AI Safety · Regulation · GPU Infrastructure · Open Source",
     "meta":"EU AI Act · NIST · Compute · Alignment",
     "color_class":"s4","entries":[]}
  ]
}
"""

def run_crew(issue_number: int, issue_date: str, db_path: str) -> dict:
    global _DB_PATH
    _DB_PATH = db_path

    t1 = Task(description="Fetch AI RSS, dedup, classify into 4 sections.",
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
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    payload = json.loads(raw)
    for sec in payload.get("sections", []):
        for e in sec.get("entries", []):
            mark_seen(e["url"], e["title"], sec["title"], db_path)
    return payload
