from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class CfoLetter(Base):
    """A letter uploaded for the CFO to review — per the CFO's request:
    Nifesimi uploads (image/PDF), the CFO reads and replies with a comment,
    which emails + in-app-notifies Nifesimi. Private to just the CFO and the
    uploader — not visible to any other role, including other oversight
    roles that can otherwise see everything (see can_view_letter)."""

    __tablename__ = "cfo_letters"

    id = Column(String, primary_key=True)
    uploaded_by_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    uploaded_by_name = Column(String, nullable=False)
    title = Column(String, nullable=False)
    note = Column(String, nullable=True)
    # Relative path on disk (like Attachment.url elsewhere), deliberately NOT
    # served through the shared /uploads/{path} endpoint — that only checks
    # the caller is logged in, not that they're allowed to see this specific
    # file, which isn't strict enough for something meant to be private to
    # just the CFO and the uploader. Served via GET /cfo-letters/{id}/file
    # instead, which does the real access check.
    file_path = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(String, nullable=True)
    status = Column(String, default="unread", nullable=False)  # unread | read | replied
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    read_at = Column(DateTime(timezone=True), nullable=True)

    comments = relationship(
        "CfoLetterComment", backref="letter", order_by="CfoLetterComment.created_at"
    )


class CfoLetterComment(Base):
    __tablename__ = "cfo_letter_comments"

    id = Column(String, primary_key=True)
    letter_id = Column(String, ForeignKey("cfo_letters.id"), nullable=False, index=True)
    author_id = Column(String, ForeignKey("users.id"), nullable=False)
    author_name = Column(String, nullable=False)
    body = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
