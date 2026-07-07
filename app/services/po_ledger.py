from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.request import Request

# Requests in these statuses count against a PO's contract ceiling; draft,
# returned, and rejected requests haven't committed real spend yet.
COMMITTED_STATUSES = ("in_review", "approved", "closed")


def committed_amount_for_po(
    db: Session, po_id: str, exclude_request_id: str | None = None
) -> float:
    query = db.query(func.coalesce(func.sum(Request.amount_due), 0.0)).filter(
        Request.po_id == po_id, Request.status.in_(COMMITTED_STATUSES)
    )
    if exclude_request_id:
        query = query.filter(Request.id != exclude_request_id)
    return float(query.scalar() or 0.0)


def committed_amounts_for_pos(db: Session, po_ids: list[str]) -> dict[str, float]:
    """Batched version of committed_amount_for_po for lists — one grouped
    query instead of one per PO."""
    if not po_ids:
        return {}
    rows = (
        db.query(Request.po_id, func.coalesce(func.sum(Request.amount_due), 0.0))
        .filter(Request.po_id.in_(po_ids), Request.status.in_(COMMITTED_STATUSES))
        .group_by(Request.po_id)
        .all()
    )
    result = dict.fromkeys(po_ids, 0.0)
    for po_id, total in rows:
        result[po_id] = float(total or 0.0)
    return result
