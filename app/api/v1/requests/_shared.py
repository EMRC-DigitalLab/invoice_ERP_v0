import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.notification import PendingDecisionEmail
from app.models.request import ApprovalStep, AuditEntry, Request
from app.models.user import User

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

UPLOAD_URL_PREFIX = "/api/v1/uploads"
EDITABLE_STATUSES = {"draft", "returned"}


def get_or_404(db: Session, request_id: str) -> Request:
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found.")
    return req


def add_audit(
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


def notify_decision(
    db: Session,
    req: Request,
    decision: str,
    decided_by: User,
    comment: str | None,
) -> None:
    """Queues a "your request was approved/rejected" notification for the
    requester and every prior approver, one row per recipient. NOT sent
    immediately — app/services/decision_digest.py sweeps these on a
    schedule and batches everything for the same recipient into a single
    digest email, so bulk-approving N requests doesn't fire N separate
    emails (Resend's free tier is volume-limited)."""
    acted_user_ids = {
        s.acted_by
        for s in db.query(ApprovalStep).filter(ApprovalStep.request_id == req.id).all()
        if s.acted_by
    }
    recipient_ids = (acted_user_ids | {req.requested_by_id}) - {decided_by.id}
    recipients = (
        db.query(User).filter(User.id.in_(recipient_ids)).all() if recipient_ids else []
    )

    decided_by_role_label = ROLE_LABELS.get(decided_by.role, decided_by.role)

    for user in recipients:
        db.add(
            PendingDecisionEmail(
                id=uuid.uuid4().hex,
                request_id=req.id,
                request_reference=req.reference or req.id,
                request_subject=req.subject or "",
                decision=decision,
                decided_by_name=decided_by.name,
                decided_by_role_label=decided_by_role_label,
                comment=comment,
                recipient_user_id=user.id,
                recipient_email=user.email,
                recipient_name=user.name,
            )
        )
    if recipients:
        db.commit()
