from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_camel_cfg = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    alias_generator=to_camel,
)


class RequestLogOut(BaseModel):
    model_config = _camel_cfg

    id: str
    timestamp: datetime
    method: str
    path: str
    query: str | None = None
    status_code: int
    duration_ms: float
    ip: str | None = None
    user_agent: str | None = None
    error: str | None = None


class LogMeta(BaseModel):
    total: int
    page: int
    page_size: int
    errors_only: bool


class LogListResponse(BaseModel):
    data: list[RequestLogOut]
    meta: LogMeta


class LogAccessKeyOut(BaseModel):
    model_config = _camel_cfg

    id: str
    label: str
    created_by_name: str
    created_at: datetime
    last_used_at: datetime | None = None
    is_active: bool


class CreateKeyPayload(BaseModel):
    label: str


class CreateKeyResponse(BaseModel):
    data: LogAccessKeyOut
    api_key: str  # shown once — never stored in plain text


class KeyListResponse(BaseModel):
    data: list[LogAccessKeyOut]
