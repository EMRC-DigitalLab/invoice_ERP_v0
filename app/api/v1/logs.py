from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.log import RequestLog
from app.models.user import User
from app.schemas.log import LogListResponse, LogMeta, RequestLogOut

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=LogListResponse)
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    errors_only: bool = Query(False),
    method: str | None = Query(None),
    path: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")

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
