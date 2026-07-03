from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_camel_cfg = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    alias_generator=to_camel,
)


class ApprovalStepOut(BaseModel):
    model_config = _camel_cfg

    role: str
    status: str
    acted_by: str | None = None
    acted_by_name: str | None = None
    acted_at: datetime | None = None
    comment: str | None = None
    signature: str | None = None
    reservation: bool | None = None


class AttachmentOut(BaseModel):
    model_config = _camel_cfg

    id: str
    name: str
    size: str
    type: str
    uploaded_at: datetime
    url: str | None = None


class AuditEntryOut(BaseModel):
    model_config = _camel_cfg

    id: str
    action: str
    actor: str
    role: str
    timestamp: datetime
    note: str | None = None


class RequestOut(BaseModel):
    model_config = _camel_cfg

    id: str
    reference: str | None = None
    type: str
    subject: str
    department: str
    requester_department_id: str
    requester_region_id: str | None = None
    status: str
    currency: str
    requested_by: str
    requested_by_id: str
    requester_role: str
    current_step_index: int
    payment_reference: str | None = None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    closed_at: datetime | None = None

    approval_chain: list[ApprovalStepOut] = []
    attachments: list[AttachmentOut] = []
    audit: list[AuditEntryOut] = []

    # project_payment
    po_number: str | None = None
    project_owner_department: str | None = None
    project_owner_department_id: str | None = None
    service_order_name: str | None = None
    contractor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    amount_due: float | None = None
    payment_timeframe_days: int | None = None
    payment_option: str | None = None
    tin: str | None = None
    service_status: str | None = None
    documents_confirmed: bool | None = None

    # advance
    advance_details: str | None = None

    # expense
    expense_details: str | None = None

    # shared: advance / expense / proposal
    amount: float | None = None
    bank_name: str | None = None
    account_name: str | None = None
    account_no: str | None = None

    # proposal
    purpose: str | None = None
    amount_proposed: float | None = None


class RequestDetailResponse(BaseModel):
    data: RequestOut


class RequestListResponse(BaseModel):
    data: list[RequestOut]
    meta: dict


class AttachmentDetailResponse(BaseModel):
    data: AttachmentOut


# ── Input schemas ──────────────────────────────────────────────────────────────


class AttachmentIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    name: str
    size: str
    type: str
    url: str | None = None


class CreateRequestPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    type: str
    subject: str

    # project_payment
    po_number: str | None = None
    project_owner_department_id: str | None = None
    service_order_name: str | None = None
    contractor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    amount_due: float | None = None
    payment_timeframe_days: int | None = None
    payment_option: str | None = None
    tin: str | None = None
    service_status: str | None = None
    documents_confirmed: bool | None = None
    currency: str | None = None

    # advance
    advance_details: str | None = None

    # expense
    expense_details: str | None = None

    # shared: advance / expense / proposal
    amount: float | None = None
    bank_name: str | None = None
    account_name: str | None = None
    account_no: str | None = None

    # proposal
    purpose: str | None = None
    amount_proposed: float | None = None

    attachments: list[AttachmentIn] | None = None


class ActionPayload(BaseModel):
    comment: str | None = None
    signature: str | None = None
    reservation: bool | None = None


class ClosePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    payment_reference: str


# ── Summary response ───────────────────────────────────────────────────────────


class SummaryData(BaseModel):
    total: int
    draft: int
    in_review: int
    approved: int
    returned: int
    rejected: int
    closed: int
    totalValue: float  # noqa: N815


class SummaryResponse(BaseModel):
    data: SummaryData
