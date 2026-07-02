import os
import uuid

from fastapi import HTTPException, UploadFile

from app.core.config import settings

ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg"}


async def save_upload(file: UploadFile, subfolder: str = "") -> str:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="File type not allowed")

    contents = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit",
        )

    dest_dir = os.path.join(settings.UPLOAD_DIR, subfolder)
    os.makedirs(dest_dir, exist_ok=True)

    ext = os.path.splitext(file.filename or "")[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(dest_dir, filename)

    with open(filepath, "wb") as f:
        f.write(contents)

    return os.path.join(subfolder, filename).replace("\\", "/")


def delete_upload(relative_path: str) -> None:
    full_path = os.path.join(settings.UPLOAD_DIR, relative_path)
    if os.path.exists(full_path):
        os.remove(full_path)
