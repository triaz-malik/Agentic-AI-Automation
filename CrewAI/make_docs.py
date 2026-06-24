# -*- coding: utf-8 -*-
"""
Generate a branded Architecture & Operations PDF for each HIKMAH project.
Pulls real data from each project's brand.py and crew.py, renders HTML, then
converts to A4 PDF with Playwright (Chromium). Output -> CrewAI/docs/.
"""
import sys, re, html
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"; DOCS.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "hikmah-shared"))
from pdf_generator import generate_pdf

DAY = {"signal": "Tuesday", "intelligence": "Wednesday", "dataml": "Thursday",
       "cloudinfra": "Friday", "dataarch": "Saturday"}
PROJECTS = ["signal", "intelligence", "dataml", "cloudinfra", "dataarch"]


def load_brand(proj):
    ns = {}
    exec((ROOT / proj / "brand.py").read_text(encoding="utf-8"), ns)
    return ns["BRAND"], ns["SECTIONS"], ns["VOLUME"], ns["EDITION"]


def feeds_of(proj):
    t = (ROOT / proj / "crew.py").read_text(encoding="utf-8")
    m = re.search(r"RSS_FEEDS = \[(.*?)\n\]", t, re.DOTALL)
    return re.findall(r'"(https?://[^"]+)"', m.group(1)) if m else []


def host(u):
    return re.sub(r"^https?://(www\.)?", "", u).split("/")[0]


AGENTS = [
    ("01", "Data Scout", "claude-haiku-4-5", "fetch_rss, dedup",
     "Fetches every RSS feed, removes already-seen articles via SHA-256 dedup "
     "(persisted in a per-project SQLite DB), and classifies the rest into the 4 sections."),
    ("02", "Principal Analyst &amp; Strategist", "claude-sonnet-4-6", "(reasoning only)",
     "Scores each article 0-100 for senior-audience significance, drops anything below 65, "
     "and writes the 3-sentence summary plus the decision-grade 'Signal'. Keeps the top 6 per section."),
    ("03", "Intelligence Publisher", "claude-sonnet-4-6", "(reasoning only)",
     "Compiles the final, schema-valid JSON payload (issue metadata, stats, ticker, 4 sections "
     "x 6 entries) that drives the templates. Emits JSON only."),
]

CSS = """
*{box-sizing:border-box;margin:0;padding:0;}
@page{size:A4;margin:16mm 16mm;}
body{font-family:'Segoe UI',Arial,sans-serif;color:#1A2233;line-height:1.55;font-size:12px;}
h1{font-family:Georgia,serif;font-size:30px;line-height:1.1;color:#0A0E17;}
h2{font-size:16px;margin:22px 0 8px;padding-bottom:5px;border-bottom:2px solid var(--pu);color:#0A0E17;
   page-break-after:avoid;}
h2 .n{font-family:'Courier New',monospace;font-size:12px;color:var(--pu);margin-right:8px;}
p{margin:6px 0;}
.cover{background:#0A0E17;color:#fff;padding:34px 30px;border-radius:8px;margin-bottom:8px;
   page-break-inside:avoid;}
.eyebrow{font-family:'Courier New',monospace;font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:var(--pu);}
.wm{font-family:Georgia,serif;font-weight:900;font-size:40px;margin:8px 0 4px;}
.wm .ac{font-style:italic;color:var(--pu);}
.tag{color:#B8C2CF;font-size:12px;}
.meta-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px;}
.chip{font-size:10px;background:rgba(255,255,255,.08);border:1px solid #232E42;border-radius:4px;
   padding:5px 10px;color:#cfd6e0;}
.lead{font-size:12.5px;color:#3D4C63;}
table{width:100%;border-collapse:collapse;margin:8px 0;font-size:11px;}
th,td{text-align:left;padding:7px 9px;border:1px solid #E3E8F0;vertical-align:top;}
th{background:var(--bg);color:#0A0E17;font-size:10px;letter-spacing:.04em;text-transform:uppercase;}
td .mono{font-family:'Courier New',monospace;color:var(--pu2);}
.flow{display:flex;align-items:stretch;gap:0;margin:10px 0;flex-wrap:wrap;}
.step{flex:1;min-width:90px;background:var(--bg);border:1px solid var(--pu);border-radius:6px;
   padding:9px;text-align:center;font-size:10px;}
.step .t{font-weight:700;color:var(--pu2);display:block;margin-bottom:2px;font-size:11px;}
.arrow{display:flex;align-items:center;color:var(--pu);font-weight:700;padding:0 4px;}
.cols{column-count:2;column-gap:16px;font-size:10.5px;}
.cols div{break-inside:avoid;padding:2px 0;}
.sec-card{border:1px solid #E3E8F0;border-left:4px solid var(--pu);border-radius:5px;padding:8px 11px;margin:6px 0;}
.sec-card .st{font-weight:700;}
.sec-card .se{font-size:10px;color:#3D4C63;}
.foot{margin-top:24px;padding-top:10px;border-top:1px solid #E3E8F0;font-size:10px;color:#8892A4;}
.callout{background:var(--bg);border-radius:6px;padding:10px 12px;margin:8px 0;font-size:11px;}
ul{margin:6px 0 6px 18px;} li{margin:3px 0;}
"""


def build_html(proj):
    brand, sections, vol, edition = load_brand(proj)
    feeds = feeds_of(proj)
    pu, pu2, bg = brand["primary"], brand["primary_dark"], brand["primary_bg"]

    agent_rows = "".join(
        f"<tr><td class='mono'>{n}</td><td><b>{role}</b></td>"
        f"<td class='mono'>{model}</td><td class='mono'>{tools}</td><td>{desc}</td></tr>"
        for n, role, model, tools, desc in AGENTS)

    sec_cards = "".join(
        f"<div class='sec-card'><div class='st'>{s['number']} &middot; {html.escape(s['title'])}</div>"
        f"<div class='se'>{html.escape(s['eyebrow'])}<br><b>Watching:</b> {html.escape(s['meta'])}</div></div>"
        for s in sections)

    feed_items = "".join(f"<div>&bull; {html.escape(host(u))}</div>" for u in feeds)

    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'><style>
:root{{--pu:{pu};--pu2:{pu2};--bg:{bg};}}{CSS}</style></head><body>

<div class='cover'>
  <div class='eyebrow'>{html.escape(brand['eyebrow'])}</div>
  <div class='wm'>{brand['wordmark_main']} <span class='ac'>{brand['wordmark_accent']}</span></div>
  <div class='tag'>Architecture &amp; Operations &mdash; how this autonomous newsletter is built and run</div>
  <div class='meta-row'>
    <span class='chip'>Domain: {html.escape(brand['tagline'])}</span>
    <span class='chip'>Auto: {DAY[proj]} 06:00 GST</span>
    <span class='chip'>Vol. {vol} &middot; {html.escape(edition)}</span>
    <span class='chip'>Owner: {html.escape(brand['owner'])}</span>
  </div>
</div>

<h2><span class='n'>01</span>What this does</h2>
<p class='lead'>{brand['product_name']} is a fully autonomous weekly intelligence newsletter. Every week a
CrewAI agent crew reads {len(feeds)} curated industry sources, removes anything already covered,
scores what remains for a <b>senior audience</b> (engineers, architects, consultants, executives),
and publishes the strongest <b>24 stories</b> &mdash; 6 in each of 4 sections &mdash; as desktop and
mobile web pages and PDFs, archived on GitHub Pages.</p>
<div class='callout'>It is not written for juniors: each story carries a decision-grade <b>"Signal"</b>
that fuses the architectural implication with the strategic/business consequence &mdash; adoption
timing, cost, risk, and the move a senior leader should make.</div>

<h2><span class='n'>02</span>How CrewAI works here</h2>
<p>CrewAI orchestrates a small team of role-specialised LLM agents that hand work to each other in a
fixed sequence (a "crew"). Each agent has a role, a goal, a model, and optionally tools it can call.
Output of one task becomes the context of the next.</p>
<div class='flow'>
  <div class='step'><span class='t'>RSS Sources</span>{len(feeds)} feeds</div>
  <div class='arrow'>&rarr;</div>
  <div class='step'><span class='t'>Scout</span>fetch &middot; dedup &middot; classify</div>
  <div class='arrow'>&rarr;</div>
  <div class='step'><span class='t'>Analyst</span>score &middot; write Signal</div>
  <div class='arrow'>&rarr;</div>
  <div class='step'><span class='t'>Publisher</span>compile JSON</div>
  <div class='arrow'>&rarr;</div>
  <div class='step'><span class='t'>Render</span>HTML + PDF</div>
  <div class='arrow'>&rarr;</div>
  <div class='step'><span class='t'>Publish</span>GitHub + email</div>
</div>

<h2><span class='n'>03</span>The agents</h2>
<table><tr><th>#</th><th>Agent</th><th>Model</th><th>Tools</th><th>Responsibility</th></tr>
{agent_rows}</table>
<p style='font-size:10.5px;color:#3D4C63'>Models are addressed as <span class='mono'>anthropic/claude-*</span>
so CrewAI routes them to Anthropic. The Scout uses the fast Haiku model for high-volume triage; the
Analyst and Publisher use Sonnet for judgement and strict formatting.</p>

<h2><span class='n'>04</span>Context &amp; data flow</h2>
<ul>
  <li><b>Tools as context:</b> the Scout's <span class='mono'>fetch_rss</span> tool returns raw articles; its
  <span class='mono'>dedup</span> tool checks each URL's SHA-256 against a per-project SQLite DB so a story is
  never repeated across issues.</li>
  <li><b>Task chaining:</b> each agent's output is passed as the <i>context</i> of the next task &mdash;
  Scout&rarr;Analyst&rarr;Publisher &mdash; so the Analyst sees the classified set and the Publisher sees the scored set.</li>
  <li><b>Structured payload:</b> the Publisher emits one JSON object &mdash; issue metadata, stats, ticker
  headlines, and 4 sections x 6 entries (title, url, source, date, summary, signal, keywords, vendors, score).</li>
  <li><b>Branding merged in code:</b> the project's colours, wordmark and section taxonomy
  (from <span class='mono'>brand.py</span>) are merged into the payload before a shared Jinja2 template renders it.</li>
</ul>

<h2><span class='n'>05</span>Coverage &mdash; the 4 sections</h2>
{sec_cards}

<h2><span class='n'>06</span>The suite it belongs to</h2>
<p>This is one of <b>five independent projects</b> in the HIKMAH suite, each with its own crew, sources,
dedup DB, brand and weekly slot, all sharing one library (<span class='mono'>hikmah-shared</span>: renderer,
PDF generator, GitHub publisher, email sender, dedup):</p>
<table><tr><th>Project</th><th>Domain</th><th>Day (06:00 GST)</th></tr>
<tr><td>signal</td><td>Telecom / 5G / RAN</td><td>Tuesday</td></tr>
<tr><td>intelligence</td><td>AI / Agentic / LLM</td><td>Wednesday</td></tr>
<tr><td>dataml</td><td>MLOps / Data Science</td><td>Thursday</td></tr>
<tr><td>cloudinfra</td><td>Cloud / Containers / Edge</td><td>Friday</td></tr>
<tr><td>dataarch</td><td>Databases / Big Data / GPU / API</td><td>Saturday</td></tr></table>

<h2><span class='n'>07</span>What an "issue" is</h2>
<p>Each run produces one numbered issue with <b>4 deliverables</b> &mdash; published to
<span class='mono'>CrewAI/{proj}/issues/</span> and served on GitHub Pages:</p>
<ul>
  <li><span class='mono'>issue-NNN.html</span> &mdash; desktop edition (multi-column)</li>
  <li><span class='mono'>issue-NNN-mobile.html</span> &mdash; phone edition (single column)</li>
  <li><span class='mono'>issue-NNN.pdf</span> &mdash; A4 print/archive PDF</li>
  <li><span class='mono'>issue-NNN-mobile.pdf</span> &mdash; phone-format PDF</li>
</ul>
<p>An issue number auto-increments each full run. Runs can be <b>manual</b>
(<span class='mono'>run_now.py {proj}</span>) or <b>automatic</b> (the weekly scheduler), with an offline
<span class='mono'>--demo</span> mode for previewing without an API key.</p>

<h2><span class='n'>08</span>Sources ({len(feeds)})</h2>
<div class='cols'>{feed_items}</div>

<div class='foot'>{brand['product_name']} &middot; {html.escape(brand['owner'])} &middot; {html.escape(brand['website'])}
&middot; Autonomous CrewAI pipeline &middot; Generated architecture brief.</div>
</body></html>"""


for proj in PROJECTS:
    hp = DOCS / f"{proj}_architecture.html"
    hp.write_text(build_html(proj), encoding="utf-8")
    pdf = generate_pdf(str(hp), variant="desktop", pdf_path=str(DOCS / f"HIKMAH_{proj}_architecture.pdf"))
    print(f"{proj}: {pdf}")
print("done ->", DOCS)
