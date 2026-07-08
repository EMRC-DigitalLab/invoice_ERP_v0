import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.request import ApprovalStep, AuditEntry, Request
from app.models.user import User
from app.services.email import send_request_decision_email

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
