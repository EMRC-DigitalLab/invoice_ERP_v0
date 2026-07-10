import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.request import Request
from app.models.user import User
from app.services.approval_chains import get_effective_amount
from app.services.approval_routing import filter_pending
from app.services.email import send_pending_approvals_reminder_email

logger = logging.getLogger(__name__)

# Roles checked for a pending-approval backlog. Just the CFO for now — this
# can grow to other approver roles later without changing the call sites.
REMINDER_ROLES = ["cfo"]


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
) -> int:
    """Emails `user` a digest of their pending backlog if it's at or above
    `threshold`. Returns the backlog size found (0 means nothing was sent).
    `override_email` sends to a different address than the user's own —
    used for testing this without emailing a real approver.
    """
    backlog = get_pending_backlog(db, user)
    if len(backlog) < threshold:
        return len(backlog)

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

    send_pending_approvals_reminder_email(
        to=override_email or user.email,
        recipient_name=user.name,
        requests=rows,
        app_link=f"{settings.FRONTEND_URL}/dashboard/approvals",
    )
    return len(backlog)


def run_reminder_sweep(db: Session) -> list[tuple[User, int]]:
    """Checks every REMINDER_ROLES user's backlog against the configured
    threshold and emails a digest to anyone over it. Shared by the daily
    scheduled job (app/core/scheduler.py) and the manual on-demand script
    (app/scripts/send_pending_reminders.py) so there's one code path.
    Returns (user, backlog_size) for every user checked, so callers can
    report on what was found even when nothing crossed the threshold.
    """
    approvers = db.query(User).filter(User.role.in_(REMINDER_ROLES)).all()
    results: list[tuple[User, int]] = []
    for user in approvers:
        try:
            count = send_backlog_reminder(
                db,
                user,
                settings.PENDING_REMINDER_THRESHOLD,
                override_email=settings.PENDING_REMINDER_TEST_EMAIL,
            )
        except Exception:
            logger.exception(
                "Failed to send pending-approval reminder to %s", user.email
            )
            continue
        results.append((user, count))
    return results
