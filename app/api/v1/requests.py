import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.clarification import ClarificationRequest
from app.models.org import Department
from app.models.purchase_order import PurchaseOrder
from app.models.request import (
    ApprovalStep,
    Attachment,
    AuditEntry,
    MemoLineItem,
    Request,
)
from app.models.user import User
from app.schemas.clarification import (
    ClarificationDetailResponse,
    ClarificationListResponse,
    ClarificationOut,
    ClarificationPublicOut,
    ClarificationPublicResponse,
    SeekClarificationPayload,
)
from app.schemas.request import (
    ActionPayload,
    AttachmentDetailResponse,
    AttachmentOut,
    ClosePayload,
    CreateRequestPayload,
    ForwardPayload,
    RequestDetailResponse,
    RequestListResponse,
    RequestOut,
    SummaryData,
    SummaryResponse,
)
from app.services.approval_chains import build_chain, get_effective_amount
from app.services.email import (
    send_clarification_received_email,
    send_clarification_request_email,
    send_request_decision_email,
)
from app.services.file_upload import delete_upload, save_upload
from app.services.org_resolver import resolve_role_to_user
from app.services.pdf_export import generate_period_report_pdf, generate_request_pdf
from app.services.po_ledger import committed_amount_for_po

router = APIRouter(prefix="/requests", tags=["requests"])

ROLE_LABELS: dict[str, str] = {
    "staff": "Staff",
    "executive_assistant": "Executive Assistant",
    "department_head": "Department Head",
    "regional_department_head": "Regional Department Head",
    "regional_manager": "Regional Manager",
    "finance_controller": "Finance Controller",
    "finance_control": "Finance & Control",
    "project_owner": "Project Owner",
    "procurement": "Procurement",
    "cfo": "CFO",
    "md": "Managing Director",
}

_REPORT_ROLES = {"finance_control", "finance_controller", "cfo", "md"}


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
    line_items = (
        db.query(MemoLineItem)
        .filter(MemoLineItem.request_id == req.id)
        .order_by(MemoLineItem.sort_order)
        .all()
    )
    data = _orm_to_dict(req)
    data["approval_chain"] = [_orm_to_dict(s) for s in steps]
    data["attachments"] = [_orm_to_dict(a) for a in atts]
    data["audit"] = [_orm_to_dict(e) for e in entries]
    data["line_items"] = [_orm_to_dict(li) for li in line_items]
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


def _notify_decision(
    db: Session,
    req: Request,
    decision: str,
    decided_by: User,
    comment: str | None,
) -> None:
    """Emails the requester and every prior approver once a request reaches a
    final decision. Best-effort: a failed/misconfigured email send must never
    fail the approval/rejection itself, so errors are swallowed here."""
    acted_user_ids = {
        s.acted_by
        for s in db.query(ApprovalStep).filter(ApprovalStep.request_id == req.id).all()
        if s.acted_by
    }
    recipient_ids = (acted_user_ids | {req.requested_by_id}) - {decided_by.id}
    recipients = (
        db.query(User).filter(User.id.in_(recipient_ids)).all() if recipient_ids else []
    )

    app_link = f"{settings.FRONTEND_URL}/dashboard/invoices/{req.id}"
    decided_by_role_label = ROLE_LABELS.get(decided_by.role, decided_by.role)

    for user in recipients:
        try:
            send_request_decision_email(
                to=user.email,
                recipient_name=user.name,
                decision=decision,
                request_reference=req.reference or req.id,
                request_subject=req.subject or "",
                decided_by_name=decided_by.name,
                decided_by_role_label=decided_by_role_label,
                app_link=app_link,
                comment=comment,
            )
        except Exception:
            pass


def _resolve_step_user(db: Session, req: Request, step: ApprovalStep) -> str | None:
    """A "Forward"-created step is pinned to one specific person; otherwise
    resolve the role through the requester's department/region as usual."""
    if step.assigned_user_id:
        return step.assigned_user_id
    return resolve_role_to_user(
        role=step.role,
        db=db,
        requester_dept_id=req.requester_department_id,
        requester_region_id=req.requester_region_id,
        project_owner_dept_id=req.project_owner_department_id,
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
    resolved = _resolve_step_user(db, req, step)
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

    resolved = _resolve_step_user(db, req, step)
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


@router.get("/reports/pdf")
def get_period_report_pdf(
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    status: str = Query("approved"),
    type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in _REPORT_ROLES and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="You are not authorised to generate reports."
        )

    try:
        start = date.fromisoformat(from_date) if from_date else None
        end = date.fromisoformat(to_date) if to_date else None
    except ValueError:
        raise HTTPException(
            status_code=400, detail="from/to must be dates in YYYY-MM-DD format."
        )

    query = db.query(Request)
    if status and status != "all":
        query = query.filter(Request.status == status)
    if type and type != "all":
        query = query.filter(Request.type == type)
    if start:
        query = query.filter(
            Request.closed_at >= datetime.combine(start, datetime.min.time())
        )
    if end:
        query = query.filter(
            Request.closed_at
            < datetime.combine(end + timedelta(days=1), datetime.min.time())
        )

    requests = query.order_by(Request.closed_at).all()

    period_label = (
        f"{from_date or 'inception'} to {to_date or 'present'} · status: {status}"
    )
    pdf_bytes = generate_period_report_pdf(requests, period_label)
    filename = f"IBEDC-{status}-invoices-{from_date or 'all'}-{to_date or 'all'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{request_id}", response_model=RequestDetailResponse)
def get_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, request_id)
    return RequestDetailResponse(data=_build_request_out(db, req))


@router.get("/{request_id}/pdf")
def get_request_pdf(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, request_id)
    steps = (
        db.query(ApprovalStep)
        .filter(ApprovalStep.request_id == req.id)
        .order_by(ApprovalStep.step_index)
        .all()
    )
    attachments = db.query(Attachment).filter(Attachment.request_id == req.id).all()

    pdf_bytes = generate_request_pdf(req, steps, attachments)
    filename = f"{req.reference or req.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, request_id)

    if req.requested_by_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="You cannot delete a request you did not create."
        )

    db.query(ApprovalStep).filter(ApprovalStep.request_id == request_id).delete()
    db.query(Attachment).filter(Attachment.request_id == request_id).delete()
    db.query(AuditEntry).filter(AuditEntry.request_id == request_id).delete()
    db.delete(req)
    db.commit()


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

    # Contractor name and currency come from the selected PO, not free-text
    # entry — staff pick a PO, they don't retype vendor details themselves.
    po: PurchaseOrder | None = None
    if payload.type == "project_payment":
        if not payload.po_id:
            raise HTTPException(
                status_code=400, detail="A purchase order must be selected."
            )
        po = db.get(PurchaseOrder, payload.po_id)
        if po is None:
            raise HTTPException(status_code=400, detail="Unknown purchase order.")

        committed = committed_amount_for_po(db, po.id)
        remaining = po.contract_amount - committed
        if payload.amount_due and payload.amount_due > remaining:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This invoice ({payload.amount_due:,.2f} {po.currency}) exceeds "
                    f"the PO's remaining balance of {remaining:,.2f} {po.currency}."
                ),
            )

    currency = po.currency if po else "NGN"

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
        job_type=payload.job_type,
        description=payload.description,
        po_id=po.id if po else None,
        po_number=po.po_number if po else None,
        project_owner_department=proj_owner_dept_name,
        project_owner_department_id=payload.project_owner_department_id,
        service_order_name=payload.service_order_name,
        contractor_name=po.contractor_name if po else None,
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
        requesting_department=payload.requesting_department,
        # proposal
        purpose=payload.purpose,
        amount_proposed=payload.amount_proposed,
        # memo
        memo_body=payload.memo_body,
        memo_cc=payload.memo_cc,
    )
    db.add(req)
    db.flush()

    if payload.type == "memo" and payload.line_items:
        for i, item in enumerate(payload.line_items):
            db.add(
                MemoLineItem(
                    id=uuid.uuid4().hex,
                    request_id=req_id,
                    officer_name=item.officer_name,
                    nights=item.nights,
                    rate_per_night=item.rate_per_night,
                    bank_details=item.bank_details,
                    sort_order=i,
                )
            )

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
        step.reservation = None

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

    audit_action = "Approved (with reservation)" if payload.reservation else "Approved"
    _add_audit(db, req.id, audit_action, current_user, note=payload.comment)

    if is_final:
        req.status = "approved"
        req.closed_at = now
    else:
        req.current_step_index += 1

    req.updated_at = now
    db.commit()
    db.refresh(req)

    if is_final:
        _notify_decision(db, req, "approved", current_user, payload.comment)

    return RequestDetailResponse(data=_build_request_out(db, req))


@router.post("/{request_id}/forward", response_model=RequestDetailResponse)
def forward_request(
    request_id: str,
    payload: ForwardPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Routes the request to a specific person (e.g. the MD) as an extra
    approval step ahead of the current approver, instead of approving/rejecting."""
    req = _get_or_404(db, request_id)
    step = _check_approver(db, req, current_user)

    target_user = db.get(User, payload.to_user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="Selected user not found.")
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=400, detail="You can't forward a request to yourself."
        )

    now = datetime.now(timezone.utc)

    # Make room for the new step right after the current one.
    later_steps = (
        db.query(ApprovalStep)
        .filter(
            ApprovalStep.request_id == req.id,
            ApprovalStep.step_index > step.step_index,
        )
        .order_by(ApprovalStep.step_index.desc())
        .all()
    )
    for later in later_steps:
        later.step_index += 1

    db.add(
        ApprovalStep(
            id=uuid.uuid4().hex,
            request_id=req.id,
            step_index=step.step_index + 1,
            role=target_user.role,
            status="pending",
            assigned_user_id=target_user.id,
        )
    )

    step.status = "forwarded"
    step.acted_by = current_user.id
    step.acted_by_name = current_user.name
    step.acted_at = now
    step.comment = payload.comment

    req.current_step_index = step.step_index + 1
    req.updated_at = now

    _add_audit(
        db,
        req.id,
        "Forwarded",
        current_user,
        note=f"Forwarded to {target_user.name} ({ROLE_LABELS.get(target_user.role, target_user.role)})"
        + (f" — {payload.comment}" if payload.comment else ""),
    )

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

    _notify_decision(db, req, "rejected", current_user, payload.comment)

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


# ── Seek Further Clarification (external, email-based) ─────────────────────────


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
    req = _get_or_404(db, request_id)
    _check_approver(db, req, current_user)

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

    _add_audit(
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
    _get_or_404(db, request_id)
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
        clarification.attachment_url = f"{_UPLOAD_URL_PREFIX}/{result['path']}"
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
