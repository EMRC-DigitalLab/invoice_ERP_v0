from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.request import Attachment, Request
from app.models.user import User
from app.schemas.attachment import AttachmentListResponse, AttachmentWithRequestOut
from app.services.approval_routing import OVERSIGHT_ROLES

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.get("", response_model=AttachmentListResponse)
def list_attachments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Flat list of every attachment plus its parent request's key fields,
    for the sidebar Files tree (grouped client-side by upload year/month).
    Scoped the same way `GET /requests?view=all` is: oversight roles and
    admins see everything, everyone else only sees files on their own
    requests."""
    is_oversight = current_user.is_admin or current_user.role in OVERSIGHT_ROLES

    query = db.query(Attachment, Request).join(
        Request, Attachment.request_id == Request.id
    )
    if not is_oversight:
        query = query.filter(Request.requested_by_id == current_user.id)

    rows = query.order_by(Attachment.uploaded_at.desc()).all()

    items = [
        AttachmentWithRequestOut(
            id=attachment.id,
            name=attachment.name,
            size=attachment.size,
            type=attachment.type,
            uploaded_at=attachment.uploaded_at,
            url=attachment.url,
            request_id=req.id,
            request_reference=req.reference or req.id,
            request_type=req.type,
            request_subject=req.subject,
            request_status=req.status,
            department=req.department,
        )
        for attachment, req in rows
    ]
    return AttachmentListResponse(data=items)
