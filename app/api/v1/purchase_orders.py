import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.org import Department
from app.models.purchase_order import PurchaseOrder
from app.models.request import Request
from app.models.user import User
from app.schemas.purchase_order import (
    CreatePurchaseOrderPayload,
    PurchaseOrderDetailResponse,
    PurchaseOrderListResponse,
    PurchaseOrderOut,
)

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])

# Requests in these statuses count against a PO's contract ceiling; draft,
# returned, and rejected requests haven't committed real spend yet.
_COMMITTED_STATUSES = ("in_review", "approved", "closed")


def _committed_amount(db: Session, po_id: str) -> float:
    total = (
        db.query(func.coalesce(func.sum(Request.amount_due), 0.0))
        .filter(Request.po_id == po_id, Request.status.in_(_COMMITTED_STATUSES))
        .scalar()
    )
    return float(total or 0.0)


def _to_out(
    db: Session, po: PurchaseOrder, dept_names: dict[str, str]
) -> PurchaseOrderOut:
    committed = _committed_amount(db, po.id)
    return PurchaseOrderOut(
        id=po.id,
        po_number=po.po_number,
        contractor_name=po.contractor_name,
        contract_amount=po.contract_amount,
        currency=po.currency,
        department_id=po.department_id,
        department_name=dept_names.get(po.department_id),
        description=po.description,
        date_issued=po.date_issued,
        status=po.status,
        amount_committed=committed,
        amount_remaining=max(po.contract_amount - committed, 0.0),
        created_at=po.created_at,
    )


@router.get("", response_model=PurchaseOrderListResponse)
def list_purchase_orders(
    search: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = db.query(PurchaseOrder)
    if status and status != "all":
        query = query.filter(PurchaseOrder.status == status)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            (PurchaseOrder.po_number.ilike(like))
            | (PurchaseOrder.contractor_name.ilike(like))
        )

    purchase_orders = query.order_by(PurchaseOrder.created_at.desc()).limit(50).all()
    dept_names = {d.id: d.name for d in db.query(Department).all()}
    items = [_to_out(db, po, dept_names) for po in purchase_orders]
    return PurchaseOrderListResponse(data=items, meta={"total": len(items)})


@router.post("", status_code=201, response_model=PurchaseOrderDetailResponse)
def create_purchase_order(
    payload: CreatePurchaseOrderPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.po_number == payload.po_number)
        .first()
    ):
        raise HTTPException(
            status_code=409, detail="A PO with this number already exists."
        )

    department = db.get(Department, payload.department_id)
    if department is None:
        raise HTTPException(status_code=400, detail="Unknown department.")

    po = PurchaseOrder(
        id=uuid.uuid4().hex,
        po_number=payload.po_number.strip(),
        contractor_name=payload.contractor_name.strip(),
        contract_amount=payload.contract_amount,
        currency=payload.currency,
        department_id=payload.department_id,
        description=payload.description,
        date_issued=payload.date_issued,
        status=payload.status,
        created_by_id=current_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(po)
    db.commit()
    db.refresh(po)

    dept_names = {department.id: department.name}
    return PurchaseOrderDetailResponse(data=_to_out(db, po, dept_names))


@router.get("/{po_id}", response_model=PurchaseOrderDetailResponse)
def get_purchase_order(
    po_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    dept_names = {d.id: d.name for d in db.query(Department).all()}
    return PurchaseOrderDetailResponse(data=_to_out(db, po, dept_names))
