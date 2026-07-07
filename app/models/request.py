from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class Request(Base):
    __tablename__ = "requests"

    id = Column(String, primary_key=True)
    reference = Column(String, unique=True, nullable=True, index=True)
    type = Column(
        String, nullable=False, index=True
    )  # project_payment | advance | expense | proposal
    subject = Column(String, nullable=False)
    department = Column(String, nullable=False)
    requester_department_id = Column(String, nullable=False)
    requester_region_id = Column(String, nullable=True)
    status = Column(String, default="draft", nullable=False, index=True)
    currency = Column(String, default="NGN", nullable=False)
    requested_by = Column(String, nullable=False)
    requested_by_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    requester_role = Column(String, nullable=False)
    current_step_index = Column(Integer, default=-1, nullable=False)
    payment_reference = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # project_payment fields — per the CFO's 2026-07 review call, renamed
    # "Invoice Submitter Form"; vendor bank/account fields removed (sourced
    # from procurement's own PO records, not staff-entered here).
    job_type = Column(String, nullable=True)  # work | service
    description = Column(String, nullable=True)
    po_id = Column(String, ForeignKey("purchase_orders.id"), nullable=True, index=True)
    po_number = Column(String, nullable=True)
    project_owner_department = Column(String, nullable=True)
    project_owner_department_id = Column(String, nullable=True)
    service_order_name = Column(String, nullable=True)
    contractor_name = Column(String, nullable=True)
    invoice_number = Column(String, nullable=True)
    invoice_date = Column(String, nullable=True)
    amount_due = Column(Float, nullable=True)
    payment_timeframe_days = Column(Integer, nullable=True)
    payment_option = Column(String, nullable=True)  # arrears | advance
    tin = Column(String, nullable=True)
    service_status = Column(String, nullable=True)  # completed | milestone
    documents_confirmed = Column(Boolean, default=False, nullable=False)

    # advance fields
    advance_details = Column(String, nullable=True)

    # expense fields
    expense_details = Column(String, nullable=True)

    # shared: advance / expense / proposal
    amount = Column(Float, nullable=True)
    bank_name = Column(String, nullable=True)
    account_name = Column(String, nullable=True)
    account_no = Column(String, nullable=True)
    # Free-text pick from a fixed list of org units (Regulatory, F&A, etc.) —
    # deliberately not tied to the Department org-directory table/routing.
    requesting_department = Column(String, nullable=True)

    # proposal fields
    purpose = Column(String, nullable=True)
    amount_proposed = Column(Float, nullable=True)

    # memo fields — narrative body + optional CC line, mirroring the paper
    # memo format. Line items live in MemoLineItem (variable-length table).
    memo_body = Column(String, nullable=True)
    memo_cc = Column(String, nullable=True)
    # viewonly: inserts/deletes are still handled explicitly in the request
    # creation endpoint, not via cascading — this is just for reads (summary
    # totals, PDF export) so get_effective_amount() works on the ORM object.
    line_items = relationship(
        "MemoLineItem",
        order_by="MemoLineItem.sort_order",
        viewonly=True,
    )


class MemoLineItem(Base):
    """One officer/row on a Memo Request's accommodation-or-expense table —
    variable-length, so it's a child table rather than fixed Request columns."""

    __tablename__ = "memo_line_items"

    id = Column(String, primary_key=True)
    request_id = Column(String, ForeignKey("requests.id"), nullable=False, index=True)
    officer_name = Column(String, nullable=False)
    nights = Column(Integer, nullable=False)
    rate_per_night = Column(Float, nullable=False)
    bank_details = Column(String, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)


class ApprovalStep(Base):
    __tablename__ = "approval_steps"

    id = Column(String, primary_key=True)
    request_id = Column(String, ForeignKey("requests.id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    role = Column(String, nullable=False)
    status = Column(
        String, default="pending", nullable=False
    )  # pending|approved|returned|rejected|skipped|forwarded
    acted_by = Column(String, nullable=True)
    acted_by_name = Column(String, nullable=True)
    acted_at = Column(DateTime(timezone=True), nullable=True)
    comment = Column(String, nullable=True)
    reservation = Column(Boolean, nullable=True)
    # Set when this step was created via "Forward" — pins the step to one
    # specific person instead of resolving `role` through department/region.
    assigned_user_id = Column(String, ForeignKey("users.id"), nullable=True)


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String, primary_key=True)
    request_id = Column(String, ForeignKey("requests.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    size = Column(String, nullable=False)
    type = Column(String, nullable=False)
    uploaded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    url = Column(String, nullable=True)


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id = Column(String, primary_key=True)
    request_id = Column(String, ForeignKey("requests.id"), nullable=False, index=True)
    action = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    actor_id = Column(String, ForeignKey("users.id"), nullable=True)
    role = Column(String, nullable=False)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    note = Column(String, nullable=True)
