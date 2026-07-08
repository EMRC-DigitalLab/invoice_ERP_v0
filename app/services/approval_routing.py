from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.request import ApprovalStep, Request
from app.models.user import User
from app.services.org_resolver import resolve_role_to_user


def resolve_step_user(db: Session, req: Request, step: ApprovalStep) -> str | None:
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


def filter_pending(db: Session, requests: list[Request], user: User) -> list[Request]:
    """Batched replacement for checking is-pending-for-user per row — fetches
    every candidate's current ApprovalStep in one query and memoizes
    org-resolver lookups by (role, dept, region), instead of up to 2 queries
    per request in the list."""
    candidates = [
        r for r in requests if r.status == "in_review" and r.current_step_index >= 0
    ]
    if not candidates:
        return []

    steps_by_request: dict[str, list[ApprovalStep]] = {}
    for s in (
        db.query(ApprovalStep)
        .filter(ApprovalStep.request_id.in_([r.id for r in candidates]))
        .all()
    ):
        steps_by_request.setdefault(s.request_id, []).append(s)

    resolve_cache: dict[tuple, str | None] = {}
    result = []
    for req in candidates:
        step = next(
            (
                s
                for s in steps_by_request.get(req.id, [])
                if s.step_index == req.current_step_index
            ),
            None,
        )
        if step is None:
            continue
        if step.assigned_user_id:
            resolved = step.assigned_user_id
        else:
            key = (
                step.role,
                req.requester_department_id,
                req.requester_region_id,
                req.project_owner_department_id,
            )
            if key not in resolve_cache:
                resolve_cache[key] = resolve_role_to_user(
                    role=step.role,
                    db=db,
                    requester_dept_id=req.requester_department_id,
                    requester_region_id=req.requester_region_id,
                    project_owner_dept_id=req.project_owner_department_id,
                )
            resolved = resolve_cache[key]
        # Fallback: if seat unassigned, any user holding that role can act
        if resolved == user.id or (resolved is None and user.role == step.role):
            result.append(req)
    return result


def check_approver(db: Session, req: Request, user: User) -> ApprovalStep:
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

    resolved = resolve_step_user(db, req, step)
    if resolved is not None and resolved != user.id:
        raise HTTPException(
            status_code=403, detail="You are not the expected approver for this step."
        )
    if resolved is None and user.role != step.role:
        raise HTTPException(
            status_code=403, detail="You are not the expected approver for this step."
        )

    return step
