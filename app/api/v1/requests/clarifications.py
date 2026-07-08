import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.v1.requests._shared import UPLOAD_URL_PREFIX, add_audit, get_or_404
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.clarification import ClarificationRequest
from app.models.request import AuditEntry, Request
from app.models.user import User
from app.schemas.clarification import (
    ClarificationDetailResponse,
    ClarificationListResponse,
    ClarificationOut,
    ClarificationPublicOut,
    ClarificationPublicResponse,
    SeekClarificationPayload,
)
from app.services.approval_routing import check_approver
from app.services.email import (
    send_clarification_received_email,
    send_clarification_request_email,
)
from app.services.file_upload import save_upload
from app.services.request_serializer import _orm_to_dict

router = APIRouter(prefix="/requests", tags=["requests"])


def _clarification_to_out(c: ClarificationRequest) -> ClarificationOut:
    data = _orm_to_dict(c)
    data["cc_emails"] = [e.strip() for e in (c.cc_emails or "").split(",") if e.strip()]
    return ClarificationOut.model_validate(data)


@router.post(
    "/{request_id}/seek-clarification",
    response_model=ClarificationDetailResponse,
    status_code=201,
)
def seek_clarification(
    request_id: str,
    payload: SeekClarificationPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = get_or_404(db, request_id)
    check_approver(db, req, current_user)

    clarification = ClarificationRequest(
        id=uuid.uuid4().hex,
        request_id=req.id,
        token=secrets.token_urlsafe(32),
        requested_by_id=current_user.id,
        recipient_email=str(payload.recipient_email),
        cc_emails=",".join(str(e) for e in payload.cc_emails),
        note=payload.note,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(clarification)

    add_audit(
        db,
        req.id,
        "Sought further clarification",
        current_user,
        note=f"Emailed {clarification.recipient_email}"
        + (f" (cc: {clarification.cc_emails})" if clarification.cc_emails else "")
        + (f" — {payload.note}" if payload.note else ""),
    )
    db.commit()
    db.refresh(clarification)

    link = f"{settings.FRONTEND_URL}/clarification/{clarification.token}"
    try:
        send_clarification_request_email(
            to=clarification.recipient_email,
            cc=payload.cc_emails or None,
            requester_name=current_user.name,
            request_reference=req.reference or req.id,
            request_subject=req.subject,
            link=link,
            contractor_name=req.contractor_name,
            po_number=req.po_number,
            invoice_number=req.invoice_number,
            amount_due=req.amount_due,
            currency=req.currency,
            note=payload.note,
        )
    except Exception as exc:  # noqa: BLE001 — don't let an email outage lose the saved request
        raise HTTPException(
            status_code=502, detail=f"Saved, but could not send the email: {exc}"
        ) from exc

    return ClarificationDetailResponse(data=_clarification_to_out(clarification))


@router.get("/{request_id}/clarifications", response_model=ClarificationListResponse)
def list_clarifications(
    request_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    get_or_404(db, request_id)
    items = (
        db.query(ClarificationRequest)
        .filter(ClarificationRequest.request_id == request_id)
        .order_by(ClarificationRequest.created_at.desc())
        .all()
    )
    return ClarificationListResponse(data=[_clarification_to_out(c) for c in items])


@router.get("/clarifications/{token}", response_model=ClarificationPublicResponse)
def get_public_clarification(token: str, db: Session = Depends(get_db)):
    clarification = (
        db.query(ClarificationRequest)
        .filter(ClarificationRequest.token == token)
        .first()
    )
    if clarification is None:
        raise HTTPException(status_code=404, detail="This link is invalid.")

    req = db.get(Request, clarification.request_id)
    return ClarificationPublicResponse(
        data=ClarificationPublicOut(
            request_reference=req.reference if req else None,
            request_subject=req.subject if req else "",
            recipient_email=clarification.recipient_email,
            status=clarification.status,
            note=clarification.note,
            contractor_name=req.contractor_name if req else None,
            po_number=req.po_number if req else None,
            invoice_number=req.invoice_number if req else None,
            amount_due=req.amount_due if req else None,
            currency=req.currency if req else None,
        )
    )


@router.post(
    "/clarifications/{token}/respond", response_model=ClarificationDetailResponse
)
async def respond_to_clarification(
    token: str,
    name: str = Form(...),
    position: str = Form(...),
    clarification_text: str = Form(..., alias="clarificationText"),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    clarification = (
        db.query(ClarificationRequest)
        .filter(ClarificationRequest.token == token)
        .first()
    )
    if clarification is None:
        raise HTTPException(status_code=404, detail="This link is invalid.")
    if clarification.status == "responded":
        raise HTTPException(
            status_code=409, detail="This request has already been responded to."
        )

    if file is not None:
        result = await save_upload(file, subfolder="clarifications")
        clarification.attachment_url = f"{UPLOAD_URL_PREFIX}/{result['path']}"
        clarification.attachment_name = file.filename

    clarification.status = "responded"
    clarification.responded_at = datetime.now(timezone.utc)
    clarification.respondent_name = name.strip()
    clarification.respondent_email = clarification.recipient_email
    clarification.respondent_position = position.strip()
    clarification.clarification_text = clarification_text.strip()

    req = db.get(Request, clarification.request_id)
    if req is not None:
        note = clarification.clarification_text
        # Marker parsed by the frontend audit log to render a "View attachment"
        # link — kept out of the visible note text.
        if clarification.attachment_url:
            note = f"{note}\n[attachment:{clarification.attachment_url}]"
        db.add(
            AuditEntry(
                id=uuid.uuid4().hex,
                request_id=req.id,
                action="Clarification received",
                actor=clarification.respondent_name,
                actor_id=None,
                role=clarification.respondent_position,
                timestamp=datetime.now(timezone.utc),
                note=note,
            )
        )

    db.commit()
    db.refresh(clarification)

    requester = db.get(User, clarification.requested_by_id)
    if requester is not None and req is not None:
        try:
            send_clarification_received_email(
                to=requester.email,
                respondent_name=clarification.respondent_name,
                respondent_position=clarification.respondent_position,
                clarification_text=clarification.clarification_text,
                attachment_name=clarification.attachment_name,
                request_reference=req.reference or req.id,
                request_subject=req.subject,
                app_link=f"{settings.FRONTEND_URL}/dashboard/invoices/{req.id}",
            )
        except Exception:  # noqa: BLE001 — the response is already saved; don't fail the request over a notification email
            pass

    return ClarificationDetailResponse(data=_clarification_to_out(clarification))
