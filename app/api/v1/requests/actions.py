import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.requests._shared import (
    ROLE_LABELS,
    add_audit,
    get_or_404,
    notify_decision,
)
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.request import ApprovalStep
from app.models.user import User
from app.schemas.request import (
    ActionPayload,
    ClosePayload,
    ForwardPayload,
    RequestDetailResponse,
)
from app.services.approval_routing import check_approver
from app.services.request_serializer import build_request_out

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("/{request_id}/submit", response_model=RequestDetailResponse)
def submit_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = get_or_404(db, request_id)

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

    add_audit(db, req.id, "Submitted for Approval", current_user)

    if not steps:
        # Empty chain → auto-approve immediately
        req.status = "approved"
        req.current_step_index = -1
        req.submitted_at = now
        req.updated_at = now
        req.closed_at = now
        add_audit(
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
    return RequestDetailResponse(data=build_request_out(db, req))


@router.post("/{request_id}/approve", response_model=RequestDetailResponse)
def approve_request(
    request_id: str,
    payload: ActionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = get_or_404(db, request_id)
    step = check_approver(db, req, current_user)

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
    add_audit(db, req.id, audit_action, current_user, note=payload.comment)

    if is_final:
        req.status = "approved"
        req.closed_at = now
    else:
        req.current_step_index += 1

    req.updated_at = now
    db.commit()
    db.refresh(req)

    if is_final:
        notify_decision(db, req, "approved", current_user, payload.comment)

    return RequestDetailResponse(data=build_request_out(db, req))


@router.post("/{request_id}/forward", response_model=RequestDetailResponse)
def forward_request(
    request_id: str,
    payload: ForwardPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Routes the request to a specific person (e.g. the MD) as an extra
    approval step ahead of the current approver, instead of approving/rejecting."""
    req = get_or_404(db, request_id)
    step = check_approver(db, req, current_user)

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

    add_audit(
        db,
        req.id,
        "Forwarded",
        current_user,
        note=f"Forwarded to {target_user.name} ({ROLE_LABELS.get(target_user.role, target_user.role)})"
        + (f" — {payload.comment}" if payload.comment else ""),
    )

    db.commit()
    db.refresh(req)
    return RequestDetailResponse(data=build_request_out(db, req))


@router.post("/{request_id}/return", response_model=RequestDetailResponse)
def return_request(
    request_id: str,
    payload: ActionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = get_or_404(db, request_id)
    step = check_approver(db, req, current_user)

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
    add_audit(
        db, req.id, "Seek Further Clarification", current_user, note=payload.comment
    )
    db.commit()
    db.refresh(req)
    return RequestDetailResponse(data=build_request_out(db, req))


@router.post("/{request_id}/reject", response_model=RequestDetailResponse)
def reject_request(
    request_id: str,
    payload: ActionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = get_or_404(db, request_id)
    step = check_approver(db, req, current_user)

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

    add_audit(db, req.id, "Rejected", current_user, note=payload.comment)
    db.commit()
    db.refresh(req)

    notify_decision(db, req, "rejected", current_user, payload.comment)

    return RequestDetailResponse(data=build_request_out(db, req))


@router.post("/{request_id}/close", response_model=RequestDetailResponse)
def close_request(
    request_id: str,
    payload: ClosePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = get_or_404(db, request_id)

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

    add_audit(
        db,
        req.id,
        "Closed",
        current_user,
        note=f"Payment reference: {payload.payment_reference}",
    )
    db.commit()
    db.refresh(req)
    return RequestDetailResponse(data=build_request_out(db, req))
