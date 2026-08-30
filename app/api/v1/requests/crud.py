import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, selectinload

from app.api.v1.requests._shared import add_audit, get_or_404
from app.core.database import get_db
from app.core.security import get_current_user
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
from app.schemas.request import (
    CreateRequestPayload,
    RequestDetailResponse,
    RequestListResponse,
    SummaryData,
    SummaryResponse,
)
from app.services.approval_chains import build_chain, get_effective_amount
from app.services.approval_routing import (
    OVERSIGHT_ROLES,
    can_view_request,
    filter_pending,
)
from app.services.pdf_export import generate_period_report_pdf, generate_request_pdf
from app.services.po_ledger import committed_amount_for_po
from app.services.request_serializer import build_request_out, build_requests_out

router = APIRouter(prefix="/requests", tags=["requests"])

_REPORT_ROLES = {"finance_control", "finance_controller", "cfo", "md"}


@router.get("", response_model=RequestListResponse)
def list_requests(
    view: str = Query("mine"),
    status: str | None = Query(None),
    type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Request)

    is_oversight = current_user.is_admin or current_user.role in OVERSIGHT_ROLES
    if view == "mine":
        query = query.filter(Request.requested_by_id == current_user.id)
    elif view == "pending":
        query = query.filter(Request.status == "in_review")
    elif view == "all" and not is_oversight:
        # Only oversight roles/admins may browse every request in the system —
        # anyone else asking for "all" is scoped down to their own requests
        # instead of being shown other staff's requests (defense-in-depth:
        # the frontend should already avoid requesting "all" for these roles).
        query = query.filter(Request.requested_by_id == current_user.id)
    # "all" for an oversight user → no extra filter

    if status and status != "all":
        query = query.filter(Request.status == status)
    if type and type != "all":
        query = query.filter(Request.type == type)

    requests = query.order_by(Request.created_at.desc()).all()

    if view == "pending":
        requests = [
            r
            for r in filter_pending(db, requests, current_user)
            if r.requested_by_id != current_user.id
        ]

    items = build_requests_out(db, requests)
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

    is_oversight = current_user.is_admin or current_user.role in OVERSIGHT_ROLES
    if view == "mine":
        query = query.filter(Request.requested_by_id == current_user.id)
    elif view == "pending":
        query = query.filter(Request.status == "in_review")
    elif view == "all" and not is_oversight:
        query = query.filter(Request.requested_by_id == current_user.id)

    if status and status != "all":
        query = query.filter(Request.status == status)
    if type and type != "all":
        query = query.filter(Request.type == type)

    # get_effective_amount() reads .line_items for memo requests — eager-load
    # it here so that doesn't lazy-load one query per memo row below.
    requests = query.options(selectinload(Request.line_items)).all()

    if view == "pending":
        requests = [
            r
            for r in filter_pending(db, requests, current_user)
            if r.requested_by_id != current_user.id
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

    # get_effective_amount() reads .line_items for memo requests — eager-load
    # it here so the report's totals don't lazy-load one query per memo row.
    requests = (
        query.options(selectinload(Request.line_items))
        .order_by(Request.closed_at)
        .all()
    )

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
    req = get_or_404(db, request_id)
    if not can_view_request(db, req, current_user):
        raise HTTPException(
            status_code=403, detail="You do not have access to this request."
        )
    return RequestDetailResponse(data=build_request_out(db, req))


@router.get("/{request_id}/pdf")
def get_request_pdf(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = get_or_404(db, request_id)
    if not can_view_request(db, req, current_user):
        raise HTTPException(
            status_code=403, detail="You do not have access to this request."
        )
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
    req = get_or_404(db, request_id)

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
        if po.status == "paid":
            raise HTTPException(
                status_code=400,
                detail="This PO is marked Paid — no new invoices can be raised against it.",
            )

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

    # project_payment always inherits the PO's currency; other types (e.g.
    # memo) may pass their own client-selected currency, defaulting to NGN.
    currency = po.currency if po else (payload.currency or "NGN")

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
        retention_type=payload.retention_type,
        retention_value=payload.retention_value,
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
        memo_subtype=payload.memo_subtype,
        memo_to=payload.memo_to,
        memo_thru=payload.memo_thru,
        memo_ref_no=payload.memo_ref_no,
        vat_inclusive=payload.vat_inclusive,
    )
    db.add(req)
    db.flush()

    if payload.type == "memo" and payload.line_items:
        for i, item in enumerate(payload.line_items):
            db.add(
                MemoLineItem(
                    id=uuid.uuid4().hex,
                    request_id=req_id,
                    description=item.description,
                    quantity=item.quantity,
                    unit_rate=item.unit_rate,
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

    add_audit(db, req_id, "Request Created", current_user)
    db.commit()
    db.refresh(req)
    return RequestDetailResponse(data=build_request_out(db, req))
