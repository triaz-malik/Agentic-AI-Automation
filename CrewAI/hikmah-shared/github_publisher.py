"""
hikmah-shared/github_publisher.py
Git push to GitHub Pages — shared by all 5 HIKMAH projects.

Publishes both the desktop and mobile variants per issue:
    issues/issue-NNN.html          (desktop — canonical)
    issues/issue-NNN-mobile.html   (mobile)
    issues/issue-NNN.pdf           (desktop A4)
    issues/issue-NNN-mobile.pdf    (mobile roll)
Each project passes its own repo_path and pages_base.
"""
import logging, shutil
from datetime import datetime
from pathlib import Path
import git
from jinja2 import Environment

logger = logging.getLogger("hikmah.github")


def publish_issue(html_paths: dict, pdf_paths: dict, issue_number: int,
                  issue_date: str, repo_path: str, pages_base: str,
                  subdir: str = "", push: bool = True) -> dict:
    """Copy this week's variants into <repo>/<subdir>/issues/, commit & push.

    html_paths / pdf_paths are {'desktop': path, 'mobile': path|None}.
    subdir scopes the project inside a shared repo, e.g. 'CrewAI/signal'.
    Only that subdir is staged, so unrelated repo changes are never committed.
    """
    repo = Path(repo_path)
    base = repo / subdir if subdir else repo
    slug = f"issue-{issue_number:03d}"
    dest = base / "issues"
    dest.mkdir(parents=True, exist_ok=True)

    # desktop = canonical slug; mobile = slug-mobile
    name = {"desktop": slug, "mobile": f"{slug}-mobile"}
    for variant, src in (html_paths or {}).items():
        if src:
            shutil.copy2(src, dest / f"{name[variant]}.html")
    for variant, src in (pdf_paths or {}).items():
        if src:
            shutil.copy2(src, dest / f"{name[variant]}.pdf")

    _write_index(base)

    if push:
        g = git.Repo(repo_path)
        add_path = (subdir or ".").replace("\\", "/")
        g.git.add(add_path)               # scoped — never `--all`
        if g.is_dirty(index=True):
            g.index.commit(f"{subdir or 'issue'}: Issue #{issue_number:03d} - {issue_date}")
            g.remotes.origin.push()
            logger.info(f"Pushed Issue #{issue_number:03d} ({subdir}) to {repo_path}")
        else:
            logger.info(f"No changes to push for Issue #{issue_number:03d} ({subdir})")

    rel = f"{subdir}/" if subdir else ""
    return {
        "html_url":        f"{pages_base}/{rel}issues/{slug}.html",
        "html_mobile_url": f"{pages_base}/{rel}issues/{slug}-mobile.html",
        "pdf_url":         f"{pages_base}/{rel}issues/{slug}.pdf",
        "pdf_mobile_url":  f"{pages_base}/{rel}issues/{slug}-mobile.pdf",
        "archive_url":     f"{pages_base}/{rel}index.html",
    }


def _write_index(repo: Path) -> None:
    # one row per desktop issue file; mobile/pdf links derived by name
    issues = sorted((repo / "issues").glob("issue-[0-9][0-9][0-9].html"), reverse=True)
    rows = []
    for f in issues:
        num = int(f.stem.replace("issue-", ""))
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%d %b %Y").lstrip("0")
        rows.append({
            "number": num, "slug": f.stem, "date": mtime,
            "has_pdf":    (f.parent / f"{f.stem}.pdf").exists(),
            "has_mobile": (f.parent / f"{f.stem}-mobile.html").exists(),
        })

    html = Environment().from_string("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>HIKMAH Archive</title>
<style>
body{background:#0A0E17;font-family:'Space Grotesk',sans-serif;color:#F4F6FA;padding:48px 32px;}
h1{font-size:36px;margin-bottom:8px;}h1 span{color:#10B981;font-style:italic;}
.sub{color:#8892A4;font-size:12px;letter-spacing:.1em;text-transform:uppercase;margin-bottom:40px;}
.row{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;
     background:#111827;border:1px solid #1C2535;border-radius:6px;margin-bottom:8px;flex-wrap:wrap;gap:8px;}
.num{font-size:10px;color:#10B981;font-family:monospace;letter-spacing:.14em;}
.date{font-size:13px;font-weight:600;}
.btn{font-size:11px;padding:6px 14px;border-radius:3px;border:1px solid;margin-left:8px;text-decoration:none;}
.bh{color:#10B981;border-color:#065F46;}.bm{color:#38BDF8;border-color:#0369A1;}.bp{color:#F43F5E;border-color:#9F1239;}
</style></head><body>
<h1>HIKMAH <span>Archive</span></h1>
<div class="sub">All Issues &middot; trmtelcocloudai.com</div>
{% for i in issues %}
<div class="row">
  <div><div class="num">Issue #{{ "%03d"|format(i.number) }}</div><div class="date">{{ i.date }}</div></div>
  <div>
    <a class="btn bh" href="issues/{{ i.slug }}.html">&#8599; Desktop</a>
    {% if i.has_mobile %}<a class="btn bm" href="issues/{{ i.slug }}-mobile.html">&#9742; Mobile</a>{% endif %}
    {% if i.has_pdf %}<a class="btn bp" href="issues/{{ i.slug }}.pdf" download>&#8595; PDF</a>{% endif %}
  </div>
</div>{% endfor %}
</body></html>""").render(issues=rows)
    (repo / "index.html").write_text(html, encoding="utf-8")
