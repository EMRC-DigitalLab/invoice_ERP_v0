from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    department = Column(String, nullable=False)
    title = Column(String, nullable=False)
    department_id = Column(String, ForeignKey("departments.id"), nullable=True)
    region_id = Column(String, ForeignKey("regions.id"), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # True for a newly-onboarded user (their password was set by an admin,
    # not chosen by them) until they successfully change it — see
    # POST /auth/change-password. Cleared by both change-password and
    # reset-password so either path counts as "now their own password".
    must_change_password = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class PasswordResetToken(Base):
    """ "Forgot password" tokens — one-time use, short-lived, emailed as a
    link. Modeled the same way as ClarificationRequest's token (secure
    random string, not a JWT, since it needs to be revocable/single-use)."""

    __tablename__ = "password_reset_tokens"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
