from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr
from pydantic.alias_generators import to_camel

_camel_cfg = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    alias_generator=to_camel,
)


class SeekClarificationPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    recipient_email: EmailStr
    cc_emails: list[EmailStr] = []
    note: str | None = None


class ClarificationOut(BaseModel):
    model_config = _camel_cfg

    id: str
    request_id: str
    recipient_email: str
    cc_emails: list[str] = []
    note: str | None = None
    status: str
    created_at: datetime
    responded_at: datetime | None = None
    respondent_name: str | None = None
    respondent_email: str | None = None
    respondent_position: str | None = None
    clarification_text: str | None = None
    attachment_url: str | None = None
    attachment_name: str | None = None


class ClarificationDetailResponse(BaseModel):
    data: ClarificationOut


class ClarificationListResponse(BaseModel):
    data: list[ClarificationOut]


class ClarificationPublicOut(BaseModel):
    """What the unauthenticated external respondent sees when opening the link."""

    model_config = _camel_cfg

    request_reference: str | None = None
    request_subject: str
    recipient_email: str
    status: str
    note: str | None = None
    contractor_name: str | None = None
    po_number: str | None = None
    invoice_number: str | None = None
    amount_due: float | None = None
    currency: str | None = None


class ClarificationPublicResponse(BaseModel):
    data: ClarificationPublicOut
