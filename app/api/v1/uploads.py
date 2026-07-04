from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.upload import UploadedFileOut, UploadResponse
from app.services.file_upload import save_upload
from app.services.public_url import get_public_base_url

router = APIRouter(prefix="/uploads", tags=["uploads"])

_UPLOAD_URL_PREFIX = "/api/v1/uploads"


@router.post("", response_model=UploadResponse, status_code=201)
@router.post(
    "/", response_model=UploadResponse, status_code=201, include_in_schema=False
)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    _current_user: User = Depends(get_current_user),
):
    result = await save_upload(file, subfolder="general")
    return UploadResponse(
        data=UploadedFileOut(
            url=f"{get_public_base_url(request)}{_UPLOAD_URL_PREFIX}/{result['path']}",
            name=file.filename or "file",
            size=str(result["size"]),
            type=result["content_type"],
        )
    )


@router.get("/{file_path:path}")
def serve_file(
    file_path: str,
    _current_user: User = Depends(get_current_user),
):
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    full_path = (upload_root / file_path).resolve()

    # Path traversal guard
    if not full_path.is_relative_to(upload_root):
        raise HTTPException(status_code=403, detail="Access denied.")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(path=str(full_path), filename=full_path.name)
