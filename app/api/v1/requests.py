import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.org import Department
from app.models.request import ApprovalStep, Attachment, AuditEntry, Request
from app.models.user import User
from app.schemas.request import (
    ActionPayload,
    AttachmentDetailResponse,
    AttachmentOut,
    ClosePayload,
    CreateRequestPayload,
    RequestDetailResponse,
    RequestListResponse,
    RequestOut,
    SummaryData,
    SummaryResponse,
)
from app.services.approval_chains import build_chain, get_effective_amount
from app.services.file_upload import delete_upload, save_upload
from app.services.org_resolver import resolve_role_to_user

router = APIRouter(prefix="/requests", tags=["requests"])

ROLE_LABELS: dict[str, str] = {
    "staff": "Staff",
    "department_head": "Department Head",
    "regional_department_head": "Regional Department Head",
    "regional_manager": "Regional Manager",
    "finance_controller": "Finance Controller",
    "finance_control": "Finance & Control",
    "project_owner": "Project Owner",
    "procurement": "Procurement",
    "cfo": "CFO",
}


# ── Helpers ────────────────────────────────────────────────────────────────────


def _orm_to_dict(obj) -> dict:
    d = obj.__dict__.copy()
    d.pop("_sa_instance_state", None)
    return d


def _build_request_out(db: Session, req: Request) -> RequestOut:
    steps = (
        db.query(ApprovalStep)
        .filter(ApprovalStep.request_id == req.id)
        .order_by(ApprovalStep.step_index)
        .all()
    )
    atts = db.query(Attachment).filter(Attachment.request_id == req.id).all()
    entries = (
        db.query(AuditEntry)
        .filter(AuditEntry.request_id == req.id)
        .order_by(AuditEntry.timestamp)
        .all()
    )
    data = _orm_to_dict(req)
    data["approval_chain"] = [_orm_to_dict(s) for s in steps]
    data["attachments"] = [_orm_to_dict(a) for a in atts]
    data["audit"] = [_orm_to_dict(e) for e in entries]
    return RequestOut.model_validate(data)


def _get_or_404(db: Session, request_id: str) -> Request:
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found.")
    return req


def _add_audit(
    db: Session,
    request_id: str,
    action: str,
    actor: User,
    note: str | None = None,
) -> None:
    db.add(
        AuditEntry(
            id=uuid.uuid4().hex,
            request_id=request_id,
            action=action,
            actor=actor.name,
            actor_id=actor.id,
            role=ROLE_LABELS.get(actor.role, actor.role),
            timestamp=datetime.now(timezone.utc),
            note=note,
        )
    )


def _is_pending_for(db: Session, req: Request, user: User) -> bool:
    """True when this in_review request's current step resolves to user."""
    if req.status != "in_review" or req.current_step_index < 0:
        return False
    step = (
        db.query(ApprovalStep)
        .filter(
            ApprovalStep.request_id == req.id,
            ApprovalStep.step_index == req.current_step_index,
        )
        .first()
    )
    if step is None:
        return False
    resolved = resolve_role_to_user(
        role=step.role,
        db=db,
        requester_dept_id=req.requester_department_id,
        requester_region_id=req.requester_region_id,
        project_owner_dept_id=req.project_owner_department_id,
    )
    if resolved == user.id:
        return True
    # Fallback: if seat unassigned, any user holding that role can act
    return resolved is None and user.role == step.role


def _check_approver(db: Session, req: Request, user: User) -> ApprovalStep:
    """Returns the current step if user may act; raises 403/409 otherwise."""
    if req.status != "in_review":
        raise HTTPException(
            status_code=409, detail="Request is not currently in review."
        )
    if req.requested_by_id == user.id:
        raise HTTPException(
            status_code=403, detail="You cannot act on your own request."
        )

    step = (
        db.query(ApprovalStep)
        .filter(
            ApprovalStep.request_id == req.id,
            ApprovalStep.step_index == req.current_step_index,
        )
        .first()
    )
    if step is None:
        raise HTTPException(status_code=409, detail="No active approval step found.")

    resolved = resolve_role_to_user(
        role=step.role,
        db=db,
        requester_dept_id=req.requester_department_id,
        requester_region_id=req.requester_region_id,
        project_owner_dept_id=req.project_owner_department_id,
    )
    if resolved is not None and resolved != user.id:
        raise HTTPException(
            status_code=403, detail="You are not the expected approver for this step."
        )
    if resolved is None and user.role != step.role:
        raise HTTPException(
            status_code=403, detail="You are not the expected approver for this step."
        )

    return step


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=RequestListResponse)
def list_requests(
    view: str = Query("mine"),
    status: str | None = Query(None),
    type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Request)

    if view == "mine":
        query = query.filter(Request.requested_by_id == current_user.id)
    elif view == "pending":
        query = query.filter(Request.status == "in_review")
    # "all" → no extra filter

    if status and status != "all":
        query = query.filter(Request.status == status)
    if type and type != "all":
        query = query.filter(Request.type == type)

    requests = query.order_by(Request.created_at.desc()).all()

    if view == "pending":
        requests = [
            r
            for r in requests
            if _is_pending_for(db, r, current_user)
            and r.requested_by_id != current_user.id
        ]

    items = [_build_request_out(db, r) for r in requests]
    return RequestListResponse(data=items, meta={"total": len(items)})


@router.get("/summary", response_model=SummaryResponse)
def get_summary(
    view: str = Query("mine"),
    status: str | None = Query(None),
    type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Request)

    if view == "mine":
        query = query.filter(Request.requested_by_id == current_user.id)
    elif view == "pending":
        query = query.filter(Request.status == "in_review")

    if status and status != "all":
        query = query.filter(Request.status == status)
    if type and type != "all":
        query = query.filter(Request.type == type)

    requests = query.all()

    if view == "pending":
        requests = [
            r
            for r in requests
            if _is_pending_for(db, r, current_user)
            and r.requested_by_id != current_user.id
        ]

    counts: dict[str, int] = {
        "draft": 0,
        "in_review": 0,
        "approved": 0,
        "returned": 0,
        "rejected": 0,
        "closed": 0,
    }
    total_value = 0.0
    for r in requests:
        counts[r.status] = counts.get(r.status, 0) + 1
        total_value += get_effective_amount(r)

    return SummaryResponse(
        data=SummaryData(
            total=len(requests),
            draft=counts["draft"],
            in_review=counts["in_review"],
            approved=counts["approved"],
            returned=counts["returned"],
            rejected=counts["rejected"],
            closed=counts["closed"],
            totalValue=total_value,
        )
    )


@router.get("/{request_id}", response_model=RequestDetailResponse)
def get_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, request_id)
    return RequestDetailResponse(data=_build_request_out(db, req))


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=RequestDetailResponse
)
def create_request(
    payload: CreateRequestPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.department_id:
        raise HTTPException(
            status_code=400,
            detail="You must be assigned to a department before submitting a request. Contact an administrator.",
        )

    req_id = uuid.uuid4().hex
    year = datetime.now(timezone.utc).year
    count = db.query(Request).count() + 1
    reference = f"IBEDC-REQ-{year}-{count:04d}"
    now = datetime.now(timezone.utc)

    amount = get_effective_amount(payload)
    chain_roles = build_chain(payload.type, amount, current_user.role)

    currency = (
        payload.currency
        if payload.type == "project_payment" and payload.currency
        else "NGN"
    )

    # Stamp project_owner_department display name server-side
    proj_owner_dept_name = None
    if payload.type == "project_payment" and payload.project_owner_department_id:
        dept = db.get(Department, payload.project_owner_department_id)
        proj_owner_dept_name = (
            dept.name if dept else payload.project_owner_department_id
        )

    req = Request(
        id=req_id,
        reference=reference,
        type=payload.type,
        subject=payload.subject,
        department=current_user.department,
        requester_department_id=current_user.department_id,
        requester_region_id=current_user.region_id,
        status="draft",
        currency=currency,
        requested_by=current_user.name,
        requested_by_id=current_user.id,
        requester_role=current_user.role,
        current_step_index=-1,
        created_at=now,
        updated_at=now,
        # project_payment
        po_number=payload.po_number,
        project_owner_department=proj_owner_dept_name,
        project_owner_department_id=payload.project_owner_department_id,
        service_order_name=payload.service_order_name,
        contractor_name=payload.contractor_name,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        amount_due=payload.amount_due,
        payment_timeframe_days=payload.payment_timeframe_days,
        payment_option=payload.payment_option,
        tin=payload.tin,
        service_status=payload.service_status,
        documents_confirmed=payload.documents_confirmed or False,
        # advance
        advance_details=payload.advance_details,
        # expense
        expense_details=payload.expense_details,
        # shared
        amount=payload.amount,
        bank_name=payload.bank_name,
        account_name=payload.account_name,
        account_no=payload.account_no,
        # proposal
        purpose=payload.purpose,
        amount_proposed=payload.amount_proposed,
    )
    db.add(req)
    db.flush()

    for i, role in enumerate(chain_roles):
        db.add(
            ApprovalStep(
                id=uuid.uuid4().hex,
                request_id=req_id,
                step_index=i,
                role=role,
                status="pending",
            )
        )

    if payload.attachments:
        for att in payload.attachments:
            db.add(
                Attachment(
                    id=uuid.uuid4().hex,
                    request_id=req_id,
                    name=att.name,
                    size=att.size,
                    type=att.type,
                    uploaded_at=now,
                    url=att.url,
                )
            )

    _add_audit(db, req_id, "Request Created", current_user)
    db.commit()
    db.refresh(req)
    return RequestDetailResponse(data=_build_request_out(db, req))


@router.post("/{request_id}/submit", response_model=RequestDetailResponse)
def submit_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, request_id)

    if req.requested_by_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the requester can submit this request."
        )
    if req.status not in ("draft", "returned"):
        raise HTTPException(
            status_code=409, detail="Request has already been submitted."
        )

    now = datetime.now(timezone.utc)

    # Reset all steps for a clean run
    steps = (
        db.query(ApprovalStep)
        .filter(ApprovalStep.request_id == req.id)
        .order_by(ApprovalStep.step_index)
        .all()
    )
    for step in steps:
        step.status = "pending"
        step.acted_by = None
        step.acted_by_name = None
        step.acted_at = None
        step.comment = None
        step.signature = None

    _add_audit(db, req.id, "Submitted for Approval", current_user)

    if not steps:
        # Empty chain → auto-approve immediately
        req.status = "approved"
        req.current_step_index = -1
        req.submitted_at = now
        req.updated_at = now
        req.closed_at = now
        _add_audit(
            db,
            req.id,
            "Auto-Approved",
            current_user,
            note="Auto-approved — no senior approver required for the requester's seniority.",
        )
    else:
        req.status = "in_review"
        req.current_step_index = 0
        req.submitted_at = now
        req.updated_at = now

    db.commit()
    db.refresh(req)
    return RequestDetailResponse(data=_build_request_out(db, req))


@router.post("/{request_id}/approve", response_model=RequestDetailResponse)
def approve_request(
    request_id: str,
    payload: ActionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, request_id)
    step = _check_approver(db, req, current_user)

    total_steps = (
        db.query(ApprovalStep).filter(ApprovalStep.request_id == req.id).count()
    )
    is_final = req.current_step_index == total_steps - 1

    if is_final and not payload.signature:
        raise HTTPException(
            status_code=400,
            detail="An e-signature is required for the final approval.",
        )
    if payload.reservation and not (payload.comment and payload.comment.strip()):
        raise HTTPException(
            status_code=400,
            detail="A comment is required when approving with a reservation.",
        )

    now = datetime.now(timezone.utc)
    step.status = "approved"
    step.acted_by = current_user.id
    step.acted_by_name = current_user.name
    step.acted_at = now
    step.comment = payload.comment
    step.reservation = payload.reservation or None
    if is_final:
        step.signature = payload.signature

    audit_note = payload.comment
    if is_final and payload.signature:
        sig_line = f"Signed: {payload.signature}"
        audit_note = f"{sig_line}. {audit_note}" if audit_note else sig_line

    audit_action = "Approved (with reservation)" if payload.reservation else "Approved"
    _add_audit(db, req.id, audit_action, current_user, note=audit_note)

    if is_final:
        req.status = "approved"
        req.closed_at = now
    else:
        req.current_step_index += 1

    req.updated_at = now
    db.commit()
    db.refresh(req)
    return RequestDetailResponse(data=_build_request_out(db, req))


@router.post("/{request_id}/return", response_model=RequestDetailResponse)
def return_request(
    request_id: str,
    payload: ActionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, request_id)
    step = _check_approver(db, req, current_user)

    if not payload.comment:
        raise HTTPException(
            status_code=422, detail="A comment is required when returning a request."
        )

    now = datetime.now(timezone.utc)
    step.status = "returned"
    step.acted_by = current_user.id
    step.acted_by_name = current_user.name
    step.acted_at = now
    step.comment = payload.comment

    req.status = "returned"
    req.current_step_index = -1
    req.updated_at = now

    # Label matches the CFO's "Seek Further Clarification" terminology for
    # this decision — status/behavior are unchanged (still `returned`).
    _add_audit(
        db, req.id, "Seek Further Clarification", current_user, note=payload.comment
    )
    db.commit()
    db.refresh(req)
    return RequestDetailResponse(data=_build_request_out(db, req))


@router.post("/{request_id}/reject", response_model=RequestDetailResponse)
def reject_request(
    request_id: str,
    payload: ActionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, request_id)
    step = _check_approver(db, req, current_user)

    if not payload.comment:
        raise HTTPException(
            status_code=422, detail="A comment is required when rejecting a request."
        )

    now = datetime.now(timezone.utc)
    step.status = "rejected"
    step.acted_by = current_user.id
    step.acted_by_name = current_user.name
    step.acted_at = now
    step.comment = payload.comment

    req.status = "rejected"
    req.current_step_index = -1
    req.updated_at = now

    _add_audit(db, req.id, "Rejected", current_user, note=payload.comment)
    db.commit()
    db.refresh(req)
    return RequestDetailResponse(data=_build_request_out(db, req))


@router.post("/{request_id}/close", response_model=RequestDetailResponse)
def close_request(
    request_id: str,
    payload: ClosePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, request_id)

    if req.status != "approved":
        raise HTTPException(
            status_code=409, detail="Only approved requests can be closed."
        )
    if current_user.role not in ("finance_control", "finance_controller", "cfo"):
        raise HTTPException(
            status_code=403, detail="You are not authorised to close requests."
        )

    now = datetime.now(timezone.utc)
    req.status = "closed"
    req.payment_reference = payload.payment_reference
    req.closed_at = now
    req.updated_at = now

    _add_audit(
        db,
        req.id,
        "Closed",
        current_user,
        note=f"Payment reference: {payload.payment_reference}",
    )
    db.commit()
    db.refresh(req)
    return RequestDetailResponse(data=_build_request_out(db, req))


# ── Attachments ────────────────────────────────────────────────────────────────

_UPLOAD_URL_PREFIX = "/api/v1/uploads"
_EDITABLE_STATUSES = {"draft", "returned"}


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
    req = _get_or_404(db, request_id)

    if req.requested_by_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You cannot add attachments to this request."
        )
    if req.status not in _EDITABLE_STATUSES:
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
        url=f"{_UPLOAD_URL_PREFIX}/{result['path']}",
    )
    db.add(att)
    _add_audit(db, request_id, "Attachment Added", current_user, note=att.name)
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
    req = _get_or_404(db, request_id)

    if req.requested_by_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="You cannot delete attachments from this request."
        )
    if req.status not in _EDITABLE_STATUSES:
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

    if att.url and att.url.startswith(_UPLOAD_URL_PREFIX + "/"):
        rel_path = att.url[len(_UPLOAD_URL_PREFIX) + 1 :]
        delete_upload(rel_path)

    _add_audit(db, request_id, "Attachment Deleted", current_user, note=att.name)
    db.delete(att)
    db.commit()
