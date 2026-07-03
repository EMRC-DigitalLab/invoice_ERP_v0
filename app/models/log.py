from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

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
