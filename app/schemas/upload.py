from pydantic import BaseModel


class UploadedFileOut(BaseModel):
    url: str
    name: str
    size: str
    type: str


class UploadResponse(BaseModel):
    data: UploadedFileOut
