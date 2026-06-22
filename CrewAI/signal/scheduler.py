"""
hikmah-signal/scheduler.py — Tuesday 06:00 GST
Run: python scheduler.py
Keep alive: nohup python scheduler.py > logs/scheduler.log 2>&1 &
"""
import logging, sys
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from dotenv import load_dotenv
load_dotenv("config/.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler("logs/scheduler.log"),
              logging.StreamHandler(sys.stdout)],
)
GST = pytz.timezone("Asia/Dubai")

def job():
    from main import run
    run(dry_run=False)

scheduler = BlockingScheduler(timezone=GST)
scheduler.add_job(job, CronTrigger(day_of_week="tue", hour=6, minute=0,
                  timezone=GST), misfire_grace_time=3600)

if __name__ == "__main__":
    print("HIKMAH Signal Scheduler — Tuesday 06:00 GST — Ctrl+C to stop")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown()
