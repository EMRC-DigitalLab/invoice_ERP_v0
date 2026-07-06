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
