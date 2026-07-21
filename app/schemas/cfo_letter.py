from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_camel_cfg = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    alias_generator=to_camel,
)


class ReplyToLetterPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    comment: str


class CfoLetterCommentOut(BaseModel):
    model_config = _camel_cfg

    id: str
    author_id: str
    author_name: str
    body: str
    created_at: datetime


class CfoLetterOut(BaseModel):
    model_config = _camel_cfg

    id: str
    uploaded_by_id: str
    uploaded_by_name: str
    title: str
    note: str | None = None
    # Built by the endpoint as /api/v1/cfo-letters/{id}/file — deliberately
    # NOT the raw file_path column (see the model's comment on why this
    # isn't served through the shared /uploads/{path} endpoint).
    file_url: str
    file_name: str
    file_type: str
    file_size: str | None = None
    status: str
    created_at: datetime
    read_at: datetime | None = None
    comments: list[CfoLetterCommentOut] = []


class CfoLetterListItemOut(BaseModel):
    """Same as CfoLetterOut but without the comment thread — the list view
    doesn't need every reply's full text, just whether one exists."""

    model_config = _camel_cfg

    id: str
    uploaded_by_id: str
    uploaded_by_name: str
    title: str
    file_name: str
    file_type: str
    status: str
    created_at: datetime


class CfoLetterDetailResponse(BaseModel):
    data: CfoLetterOut


class CfoLetterListResponse(BaseModel):
    data: list[CfoLetterListItemOut]
    meta: dict = {}
