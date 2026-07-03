import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, get_optional_current_user
from app.models.log import LogAccessKey, RequestLog
from app.models.user import User
from app.schemas.log import (
    CreateKeyPayload,
    CreateKeyResponse,
    KeyListResponse,
    LogAccessKeyOut,
    LogListResponse,
    LogMeta,
    RequestLogOut,
)

router = APIRouter(prefix="/logs", tags=["logs"])


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _resolve_auth(
    api_key: str | None,
    db: Session,
    current_user: User | None,
) -> None:
    """Allow access via Bearer token (admin) OR valid api_key query param."""
    if current_user is not None:
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required.")
        return

    if not api_key:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    key_hash = _hash_key(api_key)
    record = (
        db.query(LogAccessKey)
        .filter(LogAccessKey.key_hash == key_hash, LogAccessKey.is_active.is_(True))
        .first()
    )
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key.")

    record.last_used_at = datetime.now(timezone.utc)
    db.commit()


# ── View logs ──────────────────────────────────────────────────────────────────


@router.get("", response_model=LogListResponse)
def list_logs(
    api_key: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    errors_only: bool = Query(False),
    method: str | None = Query(None),
    path: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    _resolve_auth(api_key, db, current_user)

    query = db.query(RequestLog)
    if errors_only:
        query = query.filter(RequestLog.status_code >= 400)
    if method:
        query = query.filter(RequestLog.method == method.upper())
    if path:
        query = query.filter(RequestLog.path.contains(path))

    total = query.count()
    logs = (
        query.order_by(RequestLog.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return LogListResponse(
        data=[RequestLogOut.model_validate(log) for log in logs],
        meta=LogMeta(
            total=total,
            page=page,
            page_size=page_size,
            errors_only=errors_only,
        ),
    )


# ── Manage API keys (admin Bearer token only) ──────────────────────────────────


@router.post("/keys", response_model=CreateKeyResponse, status_code=201)
def create_key(
    payload: CreateKeyPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")

    raw_key = secrets.token_urlsafe(32)
    record = LogAccessKey(
        id=uuid.uuid4().hex,
        label=payload.label,
        key_hash=_hash_key(raw_key),
        created_by_id=current_user.id,
        created_by_name=current_user.name,
        created_at=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return CreateKeyResponse(
        data=LogAccessKeyOut.model_validate(record),
        api_key=raw_key,
    )


@router.get("/keys", response_model=KeyListResponse)
def list_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")

    keys = db.query(LogAccessKey).order_by(LogAccessKey.created_at.desc()).all()
    return KeyListResponse(data=[LogAccessKeyOut.model_validate(k) for k in keys])


@router.delete("/keys/{key_id}", status_code=204)
def revoke_key(
    key_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")

    record = db.get(LogAccessKey, key_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Key not found.")

    record.is_active = False
    db.commit()
