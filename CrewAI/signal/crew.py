"""
hikmah-signal/crew.py
3-agent CrewAI pipeline — TELECOM domain
Agents: Telecom Scout (Haiku) · RAN Analyst (Sonnet) · Publisher (Sonnet)
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

logger = logging.getLogger("hikmah-signal.crew")

RSS_FEEDS = [
    "https://www.rcrwireless.com/feed",
    "https://www.lightreading.com/rss.xml",
    "https://www.fiercewireless.com/rss.xml",
    "https://telecomtv.com/feed/",
    "https://www.telecomreview.com/feed/",
    "https://www.mobileworldlive.com/feed/",
    "https://www.3gpp.org/news-events/3gpp-news/rss",
    "https://www.gsma.com/newsroom/feed/",
    "https://www.ericsson.com/en/blog/rss",
    "https://www.nokia.com/blog/feed/",
    "https://spacenews.com/feed/",
    "https://www.telecomreviewarabia.com/feed/",
    "https://www.arabianbusiness.com/rss/technology",
]

SECTION_NAMES = [
    "Market & Operators",
    "Network Infrastructure",
    "AI, Standards & Analytics",
    "Spectrum, Satellite & Regulation",
]

_DB_PATH = "telecom_news.db"   # overridden by run_crew()

@tool("fetch_rss")
def fetch_rss(unused: str = "") -> str:
    """Fetch articles from telecom RSS feeds."""
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

@tool("dedup")
def dedup(articles_json: str = "") -> str:
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
    role="Telecom Scout",
    goal=(
        "Fetch the latest telecom news, remove duplicates, then classify each "
        "article into exactly one section: "
        "1) Market & Operators  2) Network Infrastructure  "
        "3) AI Standards & Analytics  4) Spectrum Satellite & Regulation. "
        "Return JSON: {section_1:[...], section_2:[...], "
        "section_3:[...], section_4:[...], "
        "total_scanned:N, duplicates_removed:N}"
    ),
    backstory="Senior telecom journalist, 15 years covering global mobile networks.",
    tools=[fetch_rss, dedup],
    llm="anthropic/claude-haiku-4-5",
    verbose=True, max_iter=3,
)

analyst = Agent(
    role="RAN Analyst",
    goal=(
        "Score each article 0-100 for technical relevance to GCC RAN engineers. "
        "Drop score < 60. Write: technical_summary (3 sentences), "
        "arch_impact (2 sentences on why it matters for network architects), "
        "keywords (3-5 tags), vendors (company names). "
        "Keep top 6 per section by score."
    ),
    backstory="Principal RAN architect, Huawei/Ericsson/Nokia multi-vendor GCC experience.",
    llm="anthropic/claude-sonnet-4-6",
    verbose=True, max_iter=4,
)

publisher = Agent(
    role="Briefing Publisher",
    goal="Output ONLY valid JSON matching TelecomBriefingPayload schema. No markdown.",
    backstory="Meticulous technical editor with zero tolerance for schema violations.",
    llm="anthropic/claude-sonnet-4-6",
    verbose=True, max_iter=2,
)

SCHEMA = """
{
  "issue_number": <int>,
  "issue_date": "<str>",
  "volume": "II",
  "edition": "GCC & Global Edition",
  "stats": {
    "sources_scanned": <int>,
    "duplicates_removed": <int>,
    "articles_published": 24,
    "dedup_db_total": <int>
  },
  "ticker_items": ["<headline>", ...],
  "sections": [
    {
      "id": "s1",
      "number": "01",
      "title": "Market & Operators",
      "eyebrow": "Coverage · M&A · Spectrum Deals · Vendor Financials",
      "meta": "Ericsson · Nokia · Huawei · ZTE · Regional Operators",
      "color_class": "s1",
      "entries": [
        {
          "title": "<str>",
          "url": "<str>",
          "source": "<str>",
          "date": "<str>",
          "summary": "<str>",
          "arch_impact": "<str>",
          "keywords": ["<str>"],
          "vendors": ["<str>"],
          "score": <int>
        }
      ]
    },
    {"id":"s2","number":"02","title":"Network Infrastructure",
     "eyebrow":"5G-Adv · 6G · O-RAN · CU/DU · CloudRAN · Private 5G",
     "meta":"RAN Architecture · Transport · Core · Edge","color_class":"s2","entries":[]},
    {"id":"s3","number":"03","title":"AI, Standards & Analytics",
     "eyebrow":"3GPP Rel-18/19 · GSMA APIs · AI/ML RAN · Ookla",
     "meta":"Machine Learning · Automation · Performance Intelligence","color_class":"s3","entries":[]},
    {"id":"s4","number":"04","title":"Spectrum, Satellite & Regulation",
     "eyebrow":"NTN · ITU · Cybersec · Fiber · Satellite · Regulation",
     "meta":"Policy · Licensing · NTN Integration · Critical Infrastructure","color_class":"s4","entries":[]}
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

    scout_task = Task(
        description="Fetch RSS, dedup, classify into 4 telecom sections. "
                    "Include total_scanned and duplicates_removed at top level.",
        expected_output="JSON with 4 section arrays + stats.",
        agent=scout,
    )
    analyst_task = Task(
        description=f"Score articles, drop <60, enrich with summary/arch_impact/"
                    f"keywords/vendors, keep top 6 per section.",
        expected_output="Enriched JSON same structure, 6 entries per section.",
        agent=analyst,
        context=[scout_task],
    )
    publisher_task = Task(
        description=f"Compile TelecomBriefingPayload. Output ONLY JSON.\n"
                    f"issue_number={issue_number}, issue_date={issue_date}\n"
                    f"Schema:\n{SCHEMA}",
        expected_output="Valid JSON string matching schema exactly.",
        agent=publisher,
        context=[analyst_task],
    )

    result = Crew(
        agents=[scout, analyst, publisher],
        tasks=[scout_task, analyst_task, publisher_task],
        process=Process.sequential, verbose=True,
    ).kickoff()

    raw = result.raw if hasattr(result, "raw") else str(result)
    payload = _extract_json(raw)
    # Mark all published entries as seen
    for sec in payload.get("sections", []):
        for e in sec.get("entries", []):
            mark_seen(e["url"], e["title"], sec["title"], db_path)
    return payload
