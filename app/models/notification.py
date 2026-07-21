from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.core.database import Base


class PendingDecisionEmail(Base):
    """A queued "your request was approved/rejected" notification — one row
    per (request, recipient). Populated the moment a decision is made, but
    NOT sent immediately; app/services/decision_digest.py sweeps these on a
    schedule and batches everything for the same recipient into one email
    (up to CHUNK_SIZE requests per email), instead of firing an individual
    email per decision. Exists specifically to keep transactional email
    volume down on Resend's free tier, especially now that bulk-approving
    many requests at once is a normal action."""

    __tablename__ = "pending_decision_emails"

    id = Column(String, primary_key=True)
    request_id = Column(String, ForeignKey("requests.id"), nullable=False, index=True)
    request_reference = Column(String, nullable=False)
    request_subject = Column(String, nullable=False)
    decision = Column(String, nullable=False)  # "approved" | "rejected"
    decided_by_name = Column(String, nullable=False)
    decided_by_role_label = Column(String, nullable=False)
    comment = Column(String, nullable=True)
    recipient_user_id = Column(String, nullable=False, index=True)
    recipient_email = Column(String, nullable=False)
    recipient_name = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    sent_at = Column(DateTime(timezone=True), nullable=True, index=True)
