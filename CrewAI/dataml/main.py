# -*- coding: utf-8 -*-
"""
hikmah-dataml/main.py
Full pipeline for HIKMAH DataML.

Run modes:
    python main.py --demo       # offline: synthetic payload -> HTML+PDF (no API key)
    python main.py --dry-run    # real CrewAI run, render locally, no publish/email
    python main.py --run-now    # full run: crew -> render -> publish -> email
    python main.py              # same as --run-now
"""
import sys, json, logging, os
from pathlib import Path
from datetime import datetime
import pytz
from dotenv import load_dotenv, set_key

# shared suite secrets (API keys) first, then project-specific values
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
load_dotenv("config/.env", override=True)
sys.path.insert(0, str(Path(__file__).parent.parent / "hikmah-shared"))

from db_manager       import purge_old
from html_renderer    import render_all
from pdf_generator    import generate_pdf
from email_sender     import send
from github_publisher import publish_issue
from brand            import BRAND, SECTIONS, VOLUME, EDITION

PROJECT      = "hikmah-dataml"
PRODUCT_NAME = "HIKMAH DataML"
DB_PATH      = os.getenv("DB_PATH",      "dataml_news.db")
OUTPUT_DIR   = os.getenv("OUTPUT_DIR",   "output")
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", "templates")
TEMPLATE     = os.getenv("TEMPLATE_FILE", "hikmah_dataml.html.j2")
REPO_PATH    = os.getenv("GITHUB_REPO_PATH")
PAGES_BASE   = os.getenv("GITHUB_PAGES_BASE")
SUBDIR       = os.getenv("GITHUB_SUBDIR", "")
SMTP_USER    = os.getenv("SMTP_USER")
SMTP_PASS    = os.getenv("SMTP_PASS")
RECIPIENTS   = [r.strip() for r in os.getenv("EMAIL_RECIPIENTS", "").split(",") if r]

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-22s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(f"logs/run_{datetime.now(pytz.utc).strftime('%Y%m%d_%H%M')}.log",
                            encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(PROJECT)


def _demo_payload(issue_number, issue_date):
    """Synthetic payload so the render pipeline can be exercised without an API key."""
    sections = []
    for s in SECTIONS:
        entries = []
        for i in range(6):
            entries.append({
                "title":   f"{s['title']}: Sample Headline {i + 1} - What Engineers Should Know",
                "url":     "https://example.com/article",
                "source":  s["meta"].split(" · ")[0],
                "date":    issue_date,
                "summary": ("This is placeholder copy used by --demo so you can preview the "
                            "desktop and mobile layouts without running CrewAI or spending tokens. "
                            "Replace with a real run once your ANTHROPIC_API_KEY is set."),
                "arch_impact": ("Demo signal text: the concrete decision or architectural implication "
                                "the reader should take away from this item."),
                "keywords": [w.strip() for w in s["eyebrow"].split(" · ")[:5]],
                "vendors":  [v.strip() for v in s["meta"].split(" · ")[:2]],
                "score":    95 - i * 3,
            })
        sections.append({**s, "entries": entries})
    return {
        "issue_number": issue_number,
        "issue_date":   issue_date,
        "volume":  VOLUME,
        "edition": EDITION,
        "stats": {"sources_scanned": 740, "duplicates_removed": 312,
                  "articles_published": 24, "dedup_db_total": 1840},
        "ticker_items": [f"{s['title']} - latest developments curated this week" for s in SECTIONS],
        "sections": sections,
    }


def run(dry_run=False, demo=False):
    issue_number = int(os.getenv("ISSUE_NUMBER", 1))
    issue_date   = datetime.now(pytz.timezone("Asia/Dubai")).strftime("%d %b %Y").lstrip("0")
    logger.info("=" * 60)
    logger.info(f"{PRODUCT_NAME} - Issue #{issue_number:03d} - {issue_date}  (demo={demo} dry_run={dry_run})")
    logger.info("=" * 60)

    if demo:
        payload = _demo_payload(issue_number, issue_date)
    else:
        from crew import run_crew
        logger.info("STEP 1 - CrewAI agents")
        purge_old(DB_PATH)
        payload = run_crew(issue_number, issue_date, DB_PATH)

    payload["brand"] = BRAND
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    (Path(OUTPUT_DIR) / f"payload_{issue_number:03d}.json").write_text(
        json.dumps({k: v for k, v in payload.items() if k != 'brand'}, indent=2),
        encoding="utf-8")

    logger.info("STEP 2 - Render HTML (desktop + mobile)")
    html = render_all(payload, TEMPLATE_DIR, TEMPLATE, OUTPUT_DIR)

    logger.info("STEP 3 - Generate PDF (desktop + mobile)")
    pdf = {v: generate_pdf(html[v], variant=v) for v in html}

    if demo or dry_run:
        logger.info("LOCAL RENDER COMPLETE:")
        for v in html:
            logger.info(f"  {v:8} HTML: {html[v]}")
            logger.info(f"  {v:8} PDF : {pdf[v]}")
        return {"html": html, "pdf": pdf}

    logger.info("STEP 4 - GitHub Pages push")
    urls = publish_issue(html, pdf, issue_number, issue_date, REPO_PATH, PAGES_BASE, subdir=SUBDIR)
    html = render_all(payload, TEMPLATE_DIR, TEMPLATE, OUTPUT_DIR,
                      pdf_url=urls["pdf_url"], archive_url=urls["archive_url"])
    publish_issue(html, pdf, issue_number, issue_date, REPO_PATH, PAGES_BASE, subdir=SUBDIR)

    logger.info("STEP 5 - Send email")
    send(html_path=html["desktop"], pdf_paths=pdf,
         subject=f"{PRODUCT_NAME} - Issue #{issue_number:03d} - {issue_date}",
         smtp_user=SMTP_USER, smtp_pass=SMTP_PASS, recipients=RECIPIENTS,
         html_url=urls["html_url"], pdf_url=urls["pdf_url"], archive_url=urls["archive_url"])

    set_key("config/.env", "ISSUE_NUMBER", str(issue_number + 1))
    logger.info(f"DONE - Issue #{issue_number:03d}")
    return {"html": html, "pdf": pdf, "urls": urls}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=f"{PRODUCT_NAME} pipeline")
    p.add_argument("--demo", action="store_true", help="offline synthetic render, no API")
    p.add_argument("--dry-run", action="store_true", help="real crew, local render only")
    p.add_argument("--run-now", action="store_true", help="full run + publish + email")
    a = p.parse_args()
    run(dry_run=a.dry_run, demo=a.demo)
