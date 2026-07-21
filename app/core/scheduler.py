import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database import SessionLocal
from app.services.decision_digest import run_decision_digest_sweep
from app.services.pending_reminders import run_reminder_sweep

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


def _run_pending_approval_reminders() -> None:
    db = SessionLocal()
    try:
        for result in run_reminder_sweep(db):
            if result.sent:
                logger.info(
                    "Pending-approval reminder sent to %s (%d pending, resend_id=%s)",
                    result.sent_to,
                    result.count,
                    result.resend_id,
                )
            elif result.error:
                logger.warning(
                    "Pending-approval reminder failed for %s: %s",
                    result.user.email,
                    result.error,
                )
    finally:
        db.close()


def _run_decision_digest_sweep() -> None:
    db = SessionLocal()
    try:
        for result in run_decision_digest_sweep(db):
            logger.info(
                "Decision digest: %s queued=%d emails_sent=%d",
                result.recipient_email,
                result.queued_count,
                result.emails_sent,
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
    scheduler.add_job(
        _run_decision_digest_sweep,
        trigger=IntervalTrigger(hours=3),
        id="decision_digest_sweep",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
