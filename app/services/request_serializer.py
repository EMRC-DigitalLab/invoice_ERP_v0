from sqlalchemy.orm import Session

from app.models.request import (
    ApprovalStep,
    Attachment,
    AuditEntry,
    MemoLineItem,
    Request,
)
from app.schemas.request import RequestOut


def _orm_to_dict(obj) -> dict:
    d = obj.__dict__.copy()
    d.pop("_sa_instance_state", None)
    return d


def build_requests_out(db: Session, requests: list[Request]) -> list[RequestOut]:
    """Batched version of build_request_out — fetches each child table once
    for the whole list (WHERE request_id IN (...)) instead of once per row,
    so a list of N requests costs 5 queries total instead of 4N+1."""
    if not requests:
        return []
    request_ids = [r.id for r in requests]

    steps_by_request: dict[str, list[ApprovalStep]] = {rid: [] for rid in request_ids}
    for s in (
        db.query(ApprovalStep)
        .filter(ApprovalStep.request_id.in_(request_ids))
        .order_by(ApprovalStep.step_index)
        .all()
    ):
        steps_by_request[s.request_id].append(s)

    atts_by_request: dict[str, list[Attachment]] = {rid: [] for rid in request_ids}
    for a in db.query(Attachment).filter(Attachment.request_id.in_(request_ids)).all():
        atts_by_request[a.request_id].append(a)

    entries_by_request: dict[str, list[AuditEntry]] = {rid: [] for rid in request_ids}
    for e in (
        db.query(AuditEntry)
        .filter(AuditEntry.request_id.in_(request_ids))
        .order_by(AuditEntry.timestamp)
        .all()
    ):
        entries_by_request[e.request_id].append(e)

    items_by_request: dict[str, list[MemoLineItem]] = {rid: [] for rid in request_ids}
    for li in (
        db.query(MemoLineItem)
        .filter(MemoLineItem.request_id.in_(request_ids))
        .order_by(MemoLineItem.sort_order)
        .all()
    ):
        items_by_request[li.request_id].append(li)

    results = []
    for req in requests:
        data = _orm_to_dict(req)
        data["approval_chain"] = [_orm_to_dict(s) for s in steps_by_request[req.id]]
        data["attachments"] = [_orm_to_dict(a) for a in atts_by_request[req.id]]
        data["audit"] = [_orm_to_dict(e) for e in entries_by_request[req.id]]
        data["line_items"] = [_orm_to_dict(li) for li in items_by_request[req.id]]
        results.append(RequestOut.model_validate(data))
    return results


def build_request_out(db: Session, req: Request) -> RequestOut:
    return build_requests_out(db, [req])[0]
