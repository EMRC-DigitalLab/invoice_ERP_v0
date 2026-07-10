import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.v1.requests._shared import (
    EDITABLE_STATUSES,
    UPLOAD_URL_PREFIX,
    add_audit,
    get_or_404,
)
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.request import Attachment
from app.models.user import User
from app.schemas.request import AttachmentDetailResponse, AttachmentOut
from app.services.file_upload import delete_upload, save_upload

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post(
    "/{request_id}/attachments",
    response_model=AttachmentDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_attachment(
    request_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = get_or_404(db, request_id)

    if req.requested_by_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You cannot add attachments to this request."
        )
    if req.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Attachments can only be added to draft or returned requests.",
        )

    result = await save_upload(file, subfolder=f"requests/{request_id}")
    now = datetime.now(timezone.utc)
    att = Attachment(
        id=uuid.uuid4().hex,
        request_id=request_id,
        name=file.filename or "file",
        size=str(result["size"]),
        type=result["content_type"],
        uploaded_at=now,
        url=f"{UPLOAD_URL_PREFIX}/{result['path']}",
    )
    db.add(att)
    add_audit(db, request_id, "Attachment Added", current_user, note=att.name)
    db.commit()
    db.refresh(att)
    return AttachmentDetailResponse(data=AttachmentOut.model_validate(att))


@router.delete("/{request_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(
    request_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = get_or_404(db, request_id)

    if req.requested_by_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="You cannot delete attachments from this request."
        )
    if req.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Attachments can only be deleted from draft or returned requests.",
        )

    att = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.request_id == request_id)
        .first()
    )
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    if att.url and att.url.startswith(UPLOAD_URL_PREFIX + "/"):
        rel_path = att.url[len(UPLOAD_URL_PREFIX) + 1 :]
        delete_upload(rel_path)

    add_audit(db, request_id, "Attachment Deleted", current_user, note=att.name)
    db.delete(att)
    db.commit()
