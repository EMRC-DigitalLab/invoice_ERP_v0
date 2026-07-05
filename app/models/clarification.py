from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.core.database import Base


class ClarificationRequest(Base):
    """An external, email-based request for clarification sent by the CFO —
    the recipient never logs in; they respond via a token-linked public page."""

    __tablename__ = "clarification_requests"

    id = Column(String, primary_key=True)
    request_id = Column(String, ForeignKey("requests.id"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    requested_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    recipient_email = Column(String, nullable=False)
    cc_emails = Column(String, nullable=True)  # comma-separated
    status = Column(String, default="pending", nullable=False)  # pending | responded
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    responded_at = Column(DateTime(timezone=True), nullable=True)
    respondent_name = Column(String, nullable=True)
    respondent_email = Column(String, nullable=True)
    respondent_position = Column(String, nullable=True)
    clarification_text = Column(String, nullable=True)
    attachment_url = Column(String, nullable=True)
    attachment_name = Column(String, nullable=True)
