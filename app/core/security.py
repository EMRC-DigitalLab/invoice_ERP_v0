from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

_bearer = HTTPBearer()
_bearer_optional = HTTPBearer(auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    payload["exp"] = expire
    payload["type"] = "access"
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload["type"] = "refresh"
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_user_from_raw_token(token: str, db: Session) -> User:
    """
    Decodes a raw JWT string (not wrapped in an Authorization header) into its User.
    Used for endpoints reached by <img>/<a> tags, which can't attach custom headers.
    Rejects refresh tokens — only an access token may authenticate a request.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        # Tokens issued before this field existed have no "type" — treat those
        # as access tokens too so existing sessions aren't logged out on deploy.
        if payload.get("type", "access") != "access":
            raise exc
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise exc
    except JWTError:
        raise exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise exc
    return user


def get_user_from_refresh_token(token: str, db: Session) -> User:
    """Decodes a refresh token (POST /auth/refresh only) into its User."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "refresh":
            raise exc
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise exc
    except JWTError:
        raise exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise exc
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    return get_user_from_raw_token(credentials.credentials, db)


def get_current_user_from_query(
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> User:
    """
    Same as get_current_user, but reads the JWT from a `?token=` query param
    instead of the Authorization header — for routes hit by <img>/<a> tags or
    direct browser navigation, which can't attach custom headers.
    """
    return get_user_from_raw_token(token, db)


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """Returns the current user if a valid Bearer token is present, otherwise None."""
    if credentials is None:
        return None
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            return None
        user = db.get(User, user_id)
        return user if user and user.is_active else None
    except JWTError:
        return None
