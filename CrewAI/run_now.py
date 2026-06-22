# -*- coding: utf-8 -*-
"""
hikmah-suite/run_now.py
MANUAL mode — trigger any project (or all) on demand, no scheduler.

    python run_now.py                       # full run of ALL 5 (publish + email)
    python run_now.py signal                # full run of one project
    python run_now.py signal --demo         # offline render (no API key needed)
    python run_now.py signal --dry-run      # real crew, local render only
    python run_now.py all --demo            # offline render every project

Each project still writes desktop + mobile HTML and desktop + mobile PDF
into its own output/ folder.
"""
import sys, os, argparse, importlib
from pathlib import Path

BASE = Path(__file__).parent
PROJECTS = ["signal", "intelligence", "dataml", "cloudinfra", "dataarch"]


def run_one(project: str, demo: bool, dry_run: bool):
    pdir = str(BASE / project)
    if not Path(pdir).is_dir():
        sys.exit(f"Unknown project '{project}'. Choose: {', '.join(PROJECTS)} | all")
    orig = os.getcwd()
    try:
        os.chdir(pdir)
        sys.path.insert(0, pdir)
        from dotenv import load_dotenv
        load_dotenv("config/.env", override=True)
        import main as m
        importlib.reload(m)
        print(f"\n===== HIKMAH {project} (demo={demo} dry_run={dry_run}) =====")
        m.run(dry_run=dry_run, demo=demo)
    finally:
        os.chdir(orig)
        # let the next project re-import its own main.py cleanly
        sys.modules.pop("main", None)
        sys.modules.pop("brand", None)
        sys.modules.pop("crew", None)
        if pdir in sys.path:
            sys.path.remove(pdir)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="HIKMAH — manual run trigger")
    ap.add_argument("project", nargs="?", default="all",
                    help="signal | intelligence | dataml | cloudinfra | dataarch | all")
    ap.add_argument("--demo", action="store_true", help="offline synthetic render, no API")
    ap.add_argument("--dry-run", action="store_true", help="real crew, local render only")
    a = ap.parse_args()

    targets = PROJECTS if a.project == "all" else [a.project]
    for p in targets:
        run_one(p, demo=a.demo, dry_run=a.dry_run)
