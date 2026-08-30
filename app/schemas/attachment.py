from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_camel_cfg = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    alias_generator=to_camel,
)


class AttachmentWithRequestOut(BaseModel):
    """An attachment plus just enough of its parent request to place it in
    the Files tree (Year → Month → Request) and link back to it — the full
    request detail is a click away, so we don't nest the whole RequestOut."""

    model_config = _camel_cfg

    id: str
    name: str
    size: str
    type: str
    uploaded_at: datetime
    url: str | None = None

    request_id: str
    request_reference: str
    request_type: str
    request_subject: str
    request_status: str
    department: str


class AttachmentListResponse(BaseModel):
    model_config = _camel_cfg

    data: list[AttachmentWithRequestOut]
