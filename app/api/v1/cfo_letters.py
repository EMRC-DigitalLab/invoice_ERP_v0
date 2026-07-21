import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.cfo_letter import CfoLetter, CfoLetterComment
from app.models.org import OrgSettings
from app.models.user import User
from app.schemas.cfo_letter import (
    CfoLetterCommentOut,
    CfoLetterDetailResponse,
    CfoLetterListItemOut,
    CfoLetterListResponse,
    CfoLetterOut,
    ReplyToLetterPayload,
)
from app.services.email import send_cfo_letter_reply_email
from app.services.file_upload import save_upload

router = APIRouter(prefix="/cfo-letters", tags=["cfo-letters"])

_FILE_URL_PREFIX = "/api/v1/cfo-letters"


def _is_uploader(db: Session, user: User) -> bool:
    org_settings = db.get(OrgSettings, 1)
    return org_settings is not None and org_settings.cfo_letters_uploader_id == user.id


def _is_cfo(user: User) -> bool:
    return user.role == "cfo"


def _require_uploader(db: Session, user: User) -> None:
    if not _is_uploader(db, user):
        raise HTTPException(
            status_code=403, detail="You are not authorised to upload CFO letters."
        )


def _require_letter_access(db: Session, user: User) -> None:
    """Deliberately CFO + uploader only — not oversight roles, not admins.
    This is meant to be private correspondence, per the CFO's request."""
    if not (_is_cfo(user) or _is_uploader(db, user)):
        raise HTTPException(
            status_code=403, detail="You do not have access to CFO letters."
        )


def _get_or_404(db: Session, letter_id: str) -> CfoLetter:
    letter = db.get(CfoLetter, letter_id)
    if letter is None:
        raise HTTPException(status_code=404, detail="Letter not found.")
    return letter


def _uploader_email(db: Session, letter: CfoLetter) -> str:
    uploader = db.get(User, letter.uploaded_by_id)
    return uploader.email if uploader else ""


def _serialize(letter: CfoLetter) -> CfoLetterOut:
    return CfoLetterOut(
        id=letter.id,
        uploadedById=letter.uploaded_by_id,
        uploadedByName=letter.uploaded_by_name,
        title=letter.title,
        note=letter.note,
        fileUrl=f"{_FILE_URL_PREFIX}/{letter.id}/file",
        fileName=letter.file_name,
        fileType=letter.file_type,
        fileSize=letter.file_size,
        status=letter.status,
        createdAt=letter.created_at,
        readAt=letter.read_at,
        comments=[CfoLetterCommentOut.model_validate(c) for c in letter.comments],
    )


@router.get("", response_model=CfoLetterListResponse)
def list_letters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_letter_access(db, current_user)
    letters = db.query(CfoLetter).order_by(CfoLetter.created_at.desc()).all()
    items = [CfoLetterListItemOut.model_validate(letter) for letter in letters]
    return CfoLetterListResponse(data=items, meta={"total": len(items)})


@router.post("", status_code=201, response_model=CfoLetterDetailResponse)
async def upload_letter(
    title: str = Form(...),
    note: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_uploader(db, current_user)

    result = await save_upload(file, subfolder="cfo-letters")
    letter = CfoLetter(
        id=uuid.uuid4().hex,
        uploaded_by_id=current_user.id,
        uploaded_by_name=current_user.name,
        title=title.strip(),
        note=(note or "").strip() or None,
        file_path=result["path"],
        file_name=file.filename or "file",
        file_type=result["content_type"],
        file_size=str(result["size"]),
        status="unread",
        created_at=datetime.now(timezone.utc),
    )
    db.add(letter)
    db.commit()
    db.refresh(letter)
    return CfoLetterDetailResponse(data=_serialize(letter))


@router.get("/{letter_id}", response_model=CfoLetterDetailResponse)
def get_letter(
    letter_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_letter_access(db, current_user)
    letter = _get_or_404(db, letter_id)

    # Opening it counts as read — only meaningful coming from the CFO, since
    # the uploader already knows they uploaded it.
    if _is_cfo(current_user) and letter.status == "unread":
        letter.status = "read"
        letter.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(letter)

    return CfoLetterDetailResponse(data=_serialize(letter))


@router.get("/{letter_id}/file")
def get_letter_file(
    letter_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_letter_access(db, current_user)
    letter = _get_or_404(db, letter_id)

    upload_root = Path(settings.UPLOAD_DIR).resolve()
    full_path = (upload_root / letter.file_path).resolve()

    if not full_path.is_relative_to(upload_root):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(path=str(full_path), filename=letter.file_name)


@router.post("/{letter_id}/reply", response_model=CfoLetterDetailResponse)
def reply_to_letter(
    letter_id: str,
    payload: ReplyToLetterPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_cfo(current_user):
        raise HTTPException(
            status_code=403, detail="Only the CFO can reply to a letter."
        )
    letter = _get_or_404(db, letter_id)

    comment = payload.comment.strip()
    if not comment:
        raise HTTPException(status_code=422, detail="A comment is required to reply.")

    db.add(
        CfoLetterComment(
            id=uuid.uuid4().hex,
            letter_id=letter.id,
            author_id=current_user.id,
            author_name=current_user.name,
            body=comment,
        )
    )
    letter.status = "replied"
    if letter.read_at is None:
        letter.read_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(letter)

    uploader_email = _uploader_email(db, letter)
    if uploader_email:
        try:
            send_cfo_letter_reply_email(
                to=uploader_email,
                recipient_name=letter.uploaded_by_name,
                letter_title=letter.title,
                comment=comment,
                decided_by_name=current_user.name,
                app_link=f"{settings.FRONTEND_URL}/dashboard/cfo-letters/{letter.id}",
            )
        except Exception:  # noqa: BLE001 — the reply is already saved; don't fail the request over a notification email
            pass

    return CfoLetterDetailResponse(data=_serialize(letter))
