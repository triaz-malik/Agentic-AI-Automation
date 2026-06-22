# CrewAI — HIKMAH Suite · 5 Independent Newsletter Projects

Owner: **Muhammad Tahir Riaz** · trmtelcocloudai.com
Repo: https://github.com/triaz-malik/Agentic-AI-Automation (this folder: `CrewAI/`)

Five self-contained CrewAI pipelines. Each fetches RSS, deduplicates (SHA-256),
scores **24 articles/week** with Claude agents (4 sections × 6), and renders a
branded newsletter as **separate desktop + mobile HTML and desktop + mobile
PDF**, then commits that week's issue into its own folder in this repo and emails it.

| Folder | Domain | Brand | Auto day (06:00 GST) |
|---|---|---|---|
| `signal/` | Telecom / 5G / RAN | cyan | **Tue** |
| `intelligence/` | AI / Agentic / LLM | indigo | **Wed** |
| `dataml/` | MLOps / DS / Analytics | emerald | **Thu** |
| `cloudinfra/` | Cloud / Containers / Edge | sky | **Fri** |
| `dataarch/` | Databases / Big Data / GPU / API | purple | **Sat** |

Each weekly run writes to two places inside the project folder:

```
<project>/output/   working render (git-ignored, regenerated each run)
<project>/issues/   PUBLISHED archive, committed to GitHub each week:
                      issue-NNN.html          (desktop)
                      issue-NNN-mobile.html   (mobile)
                      issue-NNN.pdf           (desktop A4)
                      issue-NNN-mobile.pdf    (mobile roll)
                    + index.html  (this project's issue archive page)
```

---

## 1. Install

```powershell
cd CrewAI
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium     # one-time, for PDFs
```

> **PDF note:** PDFs are rendered with **Playwright (headless Chromium)** — no
> GTK or native libraries required, works the same on Windows / macOS / Linux /
> WSL2. The one-time `playwright install chromium` downloads the browser. If
> Playwright or Chromium is missing, the pipeline still produces all HTML and
> just logs a warning for the PDF step.

## 2. Configure

**Shared secrets** live in `CrewAI/.env` (git-ignored) — the Anthropic key the
agents use, plus OpenAI/Google/Groq/etc. Every project loads it automatically.

**Per-project** settings live in `<project>/config/.env` (git-ignored):

```
SMTP_USER=you@gmail.com
SMTP_PASS=<gmail app password>            # or switch email_sender.py to SendGrid
EMAIL_RECIPIENTS=a@x.com,b@y.com
GITHUB_REPO_PATH=C:/Working/Agentic-AI-Automation   # this repo's local clone
GITHUB_SUBDIR=CrewAI/<project>                       # where the issue is committed
GITHUB_PAGES_BASE=https://triaz-malik.github.io/Agentic-AI-Automation
ISSUE_NUMBER=1                                        # auto-increments each full run
```

`<project>/brand.py` holds colours, wordmark, tagline and the section taxonomy.

---

## 3. Run

### Preview, no API key (offline demo)
```powershell
python run_now.py dataarch --demo      # one project
python run_now.py all --demo           # all five
```

### Manual (on demand)
```powershell
python run_now.py signal --dry-run     # real CrewAI, local render only
python run_now.py signal               # full: crew -> render -> commit to repo -> email
python run_now.py all                  # full run of all five
```

### Auto (weekly)
```powershell
python run_all.py                      # blocks; Tue..Sat 06:00 GST, commits each week
python run_all.py --test dataarch      # real dry-run one project now
python run_all.py --demo dataarch      # offline demo one project now
```
Single project on its own cron: `cd dataarch ; python scheduler.py`.

**Keep auto running (Windows):** add `run_all.py` to Task Scheduler (trigger
*At log on*, action `python` with arg `<path>\CrewAI\run_all.py`).
WSL2/Linux: `tmux new -s hikmah ; python run_all.py ; Ctrl+B D`.

> The weekly publish stages **only** `CrewAI/<project>` (never `git add --all`),
> so unrelated repo changes are never committed. Pushing uses your local git
> credentials for `origin`.

---

## Layout

```
CrewAI/
├── hikmah-shared/                 reused by all 5
│   ├── html_renderer.py           render_all() -> desktop + mobile
│   ├── pdf_generator.py           A4 + mobile geometry (graceful if WeasyPrint absent)
│   ├── github_publisher.py        commits <subdir>/issues/ + archive index, scoped push
│   ├── email_sender.py            desktop body + all PDFs attached
│   ├── db_manager.py              SHA-256 dedup (per-project SQLite)
│   └── templates/base.html.j2     shared, brand-parameterised design
├── signal/ intelligence/ dataml/ cloudinfra/ dataarch/
│   ├── main.py                    pipeline (--demo / --dry-run / --run-now)
│   ├── crew.py                    domain agents + RSS feeds (24 articles, 6/section)
│   ├── brand.py                   colours, wordmark, section taxonomy
│   ├── scheduler.py               this project's weekly cron
│   ├── templates/hikmah_*.html.j2 thin stub: {% extends "base.html.j2" %}
│   ├── config/.env                per-project settings (git-ignored)
│   ├── issues/                    PUBLISHED weekly archive (committed)
│   ├── output/                    working render (git-ignored)
│   └── logs/
├── run_all.py                     AUTO — all 5 weekly schedulers
├── run_now.py                     MANUAL — trigger any/all on demand
├── .env                           SHARED secrets (git-ignored)
└── requirements.txt
```
