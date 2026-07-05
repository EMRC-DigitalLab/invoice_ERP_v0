from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, String

from app.core.database import Base


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(String, primary_key=True)
    po_number = Column(String, unique=True, nullable=False, index=True)
    contractor_name = Column(String, nullable=False)
    contract_amount = Column(Float, nullable=False)
    currency = Column(String, default="NGN", nullable=False)
    department_id = Column(String, ForeignKey("departments.id"), nullable=False)
    description = Column(String, nullable=True)
    date_issued = Column(String, nullable=True)
    job_type = Column(String, nullable=True)  # work | service
    contractor_address = Column(String, nullable=True)
    status = Column(String, default="active", nullable=False)  # active | closed
    created_by_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
