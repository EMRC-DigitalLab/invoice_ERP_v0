import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import SessionLocal
from app.services.pending_reminders import run_reminder_sweep

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


def _run_pending_approval_reminders() -> None:
    db = SessionLocal()
    try:
        for user, count in run_reminder_sweep(db):
            if count >= 1:
                logger.info(
                    "Pending-approval sweep: %s has %d pending", user.email, count
                )
    finally:
        db.close()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        _run_pending_approval_reminders,
        trigger=CronTrigger(hour=7, minute=0),  # 07:00 UTC daily
        id="pending_approval_reminders",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
