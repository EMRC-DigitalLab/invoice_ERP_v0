import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.log import ReminderLog
from app.models.request import Request
from app.models.user import User
from app.services.approval_chains import get_effective_amount
from app.services.approval_routing import filter_pending
from app.services.email import send_pending_approvals_reminder_email

logger = logging.getLogger(__name__)

JOB_NAME = "pending_approval_reminder"

# Roles checked for a pending-approval backlog. Just the CFO for now — this
# can grow to other approver roles later without changing the call sites.
REMINDER_ROLES = ["cfo"]


@dataclass
class ReminderResult:
    user: User
    count: int
    sent: bool
    sent_to: str | None
    resend_id: str | None
    error: str | None


def get_pending_backlog(db: Session, user: User) -> list[Request]:
    """Everything currently sitting in this user's approval queue — same
    resolution logic as the "My Approvals" list/GET /requests?view=pending,
    minus requests they submitted themselves (can't approve your own)."""
    in_review = db.query(Request).filter(Request.status == "in_review").all()
    pending = filter_pending(db, in_review, user)
    return [r for r in pending if r.requested_by_id != user.id]


def send_backlog_reminder(
    db: Session,
    user: User,
    threshold: int,
    override_email: str | None = None,
) -> ReminderResult:
    """Emails `user` a digest of their pending backlog if it's at or above
    `threshold`. `override_email` sends to a different address than the
    user's own — used for testing this without emailing a real approver.
    """
    backlog = get_pending_backlog(db, user)
    count = len(backlog)
    if count < threshold:
        return ReminderResult(
            user, count, sent=False, sent_to=None, resend_id=None, error=None
        )

    rows = [
        {
            "reference": r.reference or r.id,
            "subject": r.subject or "",
            "requested_by": r.requested_by or "",
            "created_at": r.created_at.strftime("%d %b %Y") if r.created_at else "",
            "amount": f"{r.currency} {get_effective_amount(r):,.2f}",
        }
        for r in sorted(
            backlog,
            key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc),
        )
    ]

    sent_to = override_email or user.email
    response = send_pending_approvals_reminder_email(
        to=sent_to,
        recipient_name=user.name,
        requests=rows,
        app_link=f"{settings.FRONTEND_URL}/dashboard/approvals",
    )
    resend_id = response.get("id") if isinstance(response, dict) else None
    return ReminderResult(
        user, count, sent=True, sent_to=sent_to, resend_id=resend_id, error=None
    )


def _persist(db: Session, threshold: int, result: ReminderResult) -> None:
    db.add(
        ReminderLog(
            id=uuid.uuid4().hex,
            timestamp=datetime.now(timezone.utc),
            job=JOB_NAME,
            recipient_user_id=result.user.id,
            recipient_email=result.user.email,
            pending_count=result.count,
            threshold=threshold,
            sent=result.sent,
            sent_to=result.sent_to,
            resend_id=result.resend_id,
            error=result.error,
        )
    )
    db.commit()


def run_reminder_sweep(db: Session) -> list[ReminderResult]:
    """Checks every REMINDER_ROLES user's backlog against the configured
    threshold and emails a digest to anyone over it. Shared by the daily
    scheduled job (app/core/scheduler.py) and the manual on-demand script
    (app/scripts/send_pending_reminders.py) so there's one code path.
    Persists one ReminderLog row per user checked — including when nothing
    was sent — so this is auditable from the database, not just stdout.
    """
    approvers = db.query(User).filter(User.role.in_(REMINDER_ROLES)).all()
    threshold = settings.PENDING_REMINDER_THRESHOLD
    results: list[ReminderResult] = []
    for user in approvers:
        try:
            result = send_backlog_reminder(
                db, user, threshold, override_email=settings.PENDING_REMINDER_TEST_EMAIL
            )
        except Exception as exc:
            logger.exception(
                "Failed to send pending-approval reminder to %s", user.email
            )
            db.rollback()  # clear any failed transaction state before logging the failure
            result = ReminderResult(
                user, -1, sent=False, sent_to=None, resend_id=None, error=str(exc)[:500]
            )
        _persist(db, threshold, result)
        results.append(result)
    return results
