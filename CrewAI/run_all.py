# -*- coding: utf-8 -*-
"""
hikmah-suite/run_all.py
AUTO mode — start all 5 weekly schedulers in a single process.

    python run_all.py                 # start all schedulers (blocks)
    python run_all.py --test signal   # real dry-run of one project now
    python run_all.py --demo dataarch # offline demo render of one project now

Weekly cadence (06:00 GST / Asia-Dubai):
    Tue  HIKMAH Signal        (telecom / 5G / RAN)
    Wed  HIKMAH Intelligence  (AI / agentic / LLM)
    Thu  HIKMAH DataML        (MLOps / DS / analytics)
    Fri  HIKMAH CloudInfra    (cloud / containers / edge)
    Sat  HIKMAH DataArch      (databases / big data / GPU / API)

Keep alive on a server:
    tmux new -s hikmah ; python run_all.py ; Ctrl+B D   (detach)
"""
import sys, os, logging, argparse
from pathlib import Path
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-22s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler("run_all.log", encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("hikmah.suite")
GST = pytz.timezone("Asia/Dubai")
BASE = Path(__file__).parent

# project -> (dir, weekday)
PROJECTS = {
    "signal":       ("signal",       "tue"),
    "intelligence": ("intelligence", "wed"),
    "dataml":       ("dataml",       "thu"),
    "cloudinfra":   ("cloudinfra",   "fri"),
    "dataarch":     ("dataarch",     "sat"),
}


def make_job(project_dir: str, project_name: str):
    def job():
        orig = os.getcwd()
        try:
            os.chdir(project_dir)
            sys.path.insert(0, project_dir)
            import importlib, main as m
            importlib.reload(m)
            m.run(dry_run=False)
        except Exception as e:
            logger.error(f"{project_name} job failed: {e}", exc_info=True)
        finally:
            os.chdir(orig)
    job.__name__ = project_name
    return job


def run_one(project: str, demo: bool):
    if project not in PROJECTS:
        sys.exit(f"Unknown project '{project}'. Choose: {', '.join(PROJECTS)}")
    pdir = str(BASE / PROJECTS[project][0])
    os.chdir(pdir)
    sys.path.insert(0, pdir)
    from dotenv import load_dotenv
    load_dotenv("config/.env", override=True)
    import main
    main.run(dry_run=not demo, demo=demo)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="HIKMAH Suite — all schedulers / one-off runs")
    ap.add_argument("--test", metavar="PROJECT", help="real dry-run one project now")
    ap.add_argument("--demo", metavar="PROJECT", help="offline demo render one project now")
    args = ap.parse_args()

    if args.demo:
        run_one(args.demo, demo=True)
        sys.exit(0)
    if args.test:
        run_one(args.test, demo=False)
        sys.exit(0)

    scheduler = BlockingScheduler(timezone=GST)
    for name, (pdir, dow) in PROJECTS.items():
        scheduler.add_job(
            make_job(str(BASE / pdir), f"hikmah-{name}"),
            CronTrigger(day_of_week=dow, hour=6, minute=0, timezone=GST),
            id=f"hikmah-{name}", misfire_grace_time=3600,
        )

    logger.info("=" * 60)
    logger.info("HIKMAH Suite — 5 weekly schedulers running (06:00 GST)")
    logger.info("  Tue Signal | Wed Intelligence | Thu DataML | Fri CloudInfra | Sat DataArch")
    logger.info("Stop: Ctrl+C")
    logger.info("=" * 60)
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Suite stopped.")
        scheduler.shutdown()
