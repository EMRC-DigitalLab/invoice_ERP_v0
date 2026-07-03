from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from app.core.database import Base


class Request(Base):
    __tablename__ = "requests"

    id = Column(String, primary_key=True)
    reference = Column(String, unique=True, nullable=True, index=True)
    type = Column(
        String, nullable=False
    )  # project_payment | advance | expense | proposal
    subject = Column(String, nullable=False)
    department = Column(String, nullable=False)
    requester_department_id = Column(String, nullable=False)
    requester_region_id = Column(String, nullable=True)
    status = Column(String, default="draft", nullable=False)
    currency = Column(String, default="NGN", nullable=False)
    requested_by = Column(String, nullable=False)
    requested_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    requester_role = Column(String, nullable=False)
    current_step_index = Column(Integer, default=-1, nullable=False)
    payment_reference = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # project_payment fields
    po_number = Column(String, nullable=True)
    project_owner_department = Column(String, nullable=True)
    project_owner_department_id = Column(String, nullable=True)
    project_start_date = Column(String, nullable=True)
    total_project_sum = Column(Float, nullable=True)
    project_kind = Column(String, nullable=True)  # one_off | recurring
    amount_due = Column(Float, nullable=True)
    vendor_name = Column(String, nullable=True)
    vendor_bank_name = Column(String, nullable=True)
    vendor_account_name = Column(String, nullable=True)
    vendor_account_no = Column(String, nullable=True)

    # advance fields
    advance_details = Column(String, nullable=True)

    # expense fields
    expense_details = Column(String, nullable=True)

    # shared: advance / expense / proposal
    amount = Column(Float, nullable=True)
    bank_name = Column(String, nullable=True)
    account_name = Column(String, nullable=True)
    account_no = Column(String, nullable=True)

    # proposal fields
    purpose = Column(String, nullable=True)
    amount_proposed = Column(Float, nullable=True)


class ApprovalStep(Base):
    __tablename__ = "approval_steps"

    id = Column(String, primary_key=True)
    request_id = Column(String, ForeignKey("requests.id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    role = Column(String, nullable=False)
    status = Column(
        String, default="pending", nullable=False
    )  # pending|approved|returned|rejected|skipped
    acted_by = Column(String, nullable=True)
    acted_by_name = Column(String, nullable=True)
    acted_at = Column(DateTime(timezone=True), nullable=True)
    comment = Column(String, nullable=True)
    signature = Column(String, nullable=True)


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
