from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String

from app.core.database import Base


class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(String, primary_key=True)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    method = Column(String, nullable=False)
    path = Column(String, nullable=False, index=True)
    query = Column(String, nullable=True)
    status_code = Column(Integer, nullable=False, index=True)
    duration_ms = Column(Float, nullable=False)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    error = Column(String, nullable=True)


class ReminderLog(Base):
    """One row per (job, recipient) check on every scheduled/manual sweep —
    including when nothing was sent — so "did the reminder job run and what
    did it decide" is answerable from the database the same way HTTP request
    history already is, instead of only living in container stdout."""

    __tablename__ = "reminder_logs"

    id = Column(String, primary_key=True)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    job = Column(String, nullable=False, index=True)
    recipient_user_id = Column(String, nullable=False, index=True)
    recipient_email = Column(String, nullable=False)
    pending_count = Column(Integer, nullable=False)
    threshold = Column(Integer, nullable=False)
    sent = Column(Boolean, nullable=False, index=True)
    sent_to = Column(String, nullable=True)
    resend_id = Column(String, nullable=True)
    error = Column(String, nullable=True)


class LogAccessKey(Base):
    __tablename__ = "log_access_keys"

    id = Column(String, primary_key=True)
    label = Column(String, nullable=False)
    key_hash = Column(String, nullable=False, unique=True)
    created_by_id = Column(String, nullable=False)
    created_by_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
