from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_camel_cfg = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    alias_generator=to_camel,
)


class PurchaseOrderOut(BaseModel):
    model_config = _camel_cfg

    id: str
    po_number: str
    contractor_name: str
    contract_amount: float
    currency: str
    department_id: str
    department_name: str | None = None
    description: str | None = None
    date_issued: str | None = None
    job_type: str | None = None
    contractor_address: str | None = None
    status: str
    amount_committed: float = 0
    amount_remaining: float = 0
    created_at: datetime


class PurchaseOrderListResponse(BaseModel):
    data: list[PurchaseOrderOut]
    meta: dict


class PurchaseOrderDetailResponse(BaseModel):
    data: PurchaseOrderOut


class CreatePurchaseOrderPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    po_number: str
    contractor_name: str
    contract_amount: float
    currency: str = "NGN"
    department_id: str
    description: str | None = None
    date_issued: str | None = None
    job_type: str | None = None
    contractor_address: str | None = None
    status: str = "active"


class UpdatePurchaseOrderPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    po_number: str | None = None
    contractor_name: str | None = None
    contract_amount: float | None = None
    currency: str | None = None
    department_id: str | None = None
    description: str | None = None
    date_issued: str | None = None
    job_type: str | None = None
    contractor_address: str | None = None
    status: str | None = None


class BatchUploadResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    created: int
    skipped: list[str]


class BatchUploadResponse(BaseModel):
    data: BatchUploadResult
