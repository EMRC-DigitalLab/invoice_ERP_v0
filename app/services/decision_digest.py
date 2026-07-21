import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notification import PendingDecisionEmail
from app.services.email import send_decision_digest_email

logger = logging.getLogger(__name__)

# Cap per email — matches what the CFO asked for ("list 10 requests") rather
# than one email per decision. A recipient with more than this queued gets
# multiple emails, each capped at this size.
CHUNK_SIZE = 10


@dataclass
class DigestResult:
    recipient_email: str
    queued_count: int
    emails_sent: int


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def run_decision_digest_sweep(db: Session) -> list[DigestResult]:
    """Sends every recipient with unsent queued decisions one email per
    CHUNK_SIZE-sized batch, then marks those rows sent. Shared by the
    scheduled job (app/core/scheduler.py) and the manual on-demand script
    (app/scripts/send_decision_digests.py).
    """
    pending = (
        db.query(PendingDecisionEmail)
        .filter(PendingDecisionEmail.sent_at.is_(None))
        .order_by(PendingDecisionEmail.created_at)
        .all()
    )
    if not pending:
        return []

    by_recipient: dict[str, list[PendingDecisionEmail]] = defaultdict(list)
    for row in pending:
        by_recipient[row.recipient_user_id].append(row)

    results: list[DigestResult] = []
    for rows in by_recipient.values():
        recipient_email = rows[0].recipient_email
        recipient_name = rows[0].recipient_name
        emails_sent = 0

        for batch in _chunk(rows, CHUNK_SIZE):
            try:
                send_decision_digest_email(
                    to=recipient_email,
                    recipient_name=recipient_name,
                    decisions=[
                        {
                            "reference": row.request_reference,
                            "subject": row.request_subject,
                            "decision": row.decision,
                            "decided_by": f"{row.decided_by_name} — {row.decided_by_role_label}",
                        }
                        for row in batch
                    ],
                    app_link=f"{settings.FRONTEND_URL}/dashboard/invoices",
                )
            except Exception:
                logger.exception(
                    "Failed to send decision digest to %s", recipient_email
                )
                continue

            now = datetime.now(timezone.utc)
            for row in batch:
                row.sent_at = now
            db.commit()
            emails_sent += 1

        results.append(DigestResult(recipient_email, len(rows), emails_sent))

    return results
