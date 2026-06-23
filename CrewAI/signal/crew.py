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
from crewai import Agent, Crew, LLM, Process, Task
from crewai.tools import tool
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "hikmah-shared"))
from db_manager import filter_new, mark_seen

logger = logging.getLogger("hikmah-signal.crew")

RSS_FEEDS = [
    # Telecom · Operators · 5G/6G · Networks · Strategy
    "https://www.lightreading.com/rss.xml",
    "https://www.fiercewireless.com/rss/xml",
    "https://www.fierce-network.com/rss/xml",
    "https://www.rcrwireless.com/feed",
    "https://www.capacitymedia.com/feed",
    "https://www.totaltele.com/rss",
    "https://www.datacenterdynamics.com/en/rss/",
    "https://www.ericsson.com/en/blog/feed",
    "https://www.theregister.com/networks/headlines.atom",
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
            for e in p.entries[:6]:
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


# Explicit token budgets so large JSON payloads are not truncated.
HAIKU  = LLM(model="anthropic/claude-haiku-4-5",  max_tokens=8000)
SONNET = LLM(model="anthropic/claude-sonnet-4-6", max_tokens=16000)

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
    role="Briefing Publisher",
    goal="Output ONLY valid JSON matching TelecomBriefingPayload schema. No markdown.",
    backstory="Meticulous technical editor with zero tolerance for schema violations.",
    llm=SONNET,
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
