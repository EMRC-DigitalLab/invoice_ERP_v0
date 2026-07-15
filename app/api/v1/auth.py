import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_password_hash,
    get_user_from_refresh_token,
    verify_password,
)
from app.models.user import PasswordResetToken, User
from app.schemas.auth import (
    AuthData,
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    UserOut,
)
from app.services.email import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])

_MIN_PASSWORD_LENGTH = 8
_RESET_TOKEN_EXPIRE_MINUTES = 60
# Generic response regardless of whether the email exists — don't let this
# endpoint be used to enumerate registered accounts.
_FORGOT_PASSWORD_MESSAGE = (
    "If an account exists for that email, a password reset link has been sent."
)


def _validate_new_password(password: str) -> None:
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {_MIN_PASSWORD_LENGTH} characters.",
        )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled.",
        )
    return LoginResponse(
        data=AuthData(
            user=UserOut.model_validate(user),
            token=create_access_token({"sub": user.id}),
            refresh_token=create_refresh_token({"sub": user.id}),
        )
    )


@router.post("/refresh", response_model=LoginResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    user = get_user_from_refresh_token(body.refresh_token, db)
    return LoginResponse(
        data=AuthData(
            user=UserOut.model_validate(user),
            token=create_access_token({"sub": user.id}),
            # Rotated on every use — extends the session while it's actively used,
            # and limits how long a leaked refresh token stays valid unused.
            refresh_token=create_refresh_token({"sub": user.id}),
        )
    )


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    _validate_new_password(body.new_password)
    if verify_password(body.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=400,
            detail="New password must be different from your current password.",
        )

    current_user.password_hash = get_password_hash(body.new_password)
    current_user.must_change_password = False
    db.commit()
    db.refresh(current_user)

    return ChangePasswordResponse(data=UserOut.model_validate(current_user))


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if user is not None and user.is_active:
        now = datetime.now(timezone.utc)
        reset_token = PasswordResetToken(
            id=uuid.uuid4().hex,
            user_id=user.id,
            token=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=now + timedelta(minutes=_RESET_TOKEN_EXPIRE_MINUTES),
        )
        db.add(reset_token)
        db.commit()

        link = f"{settings.FRONTEND_URL}/reset-password/{reset_token.token}"
        try:
            send_password_reset_email(to=user.email, name=user.name, link=link)
        except Exception:  # noqa: BLE001 — don't leak send failures; the generic message below covers this either way
            pass

    return MessageResponse(message=_FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token == body.token)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=400, detail="This reset link is invalid.")
    if record.used_at is not None:
        raise HTTPException(
            status_code=400, detail="This reset link has already been used."
        )
    if record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="This reset link has expired. Please request a new one.",
        )

    _validate_new_password(body.new_password)

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="This reset link is invalid.")

    user.password_hash = get_password_hash(body.new_password)
    user.must_change_password = False
    record.used_at = datetime.now(timezone.utc)
    db.commit()

    return MessageResponse(message="Your password has been reset. You can now sign in.")
