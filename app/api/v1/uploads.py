from fastapi import APIRouter, UploadFile, File
from app.services.file_upload import save_upload

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post("/")
async def upload_file(file: UploadFile = File(...)):
    path = await save_upload(file, subfolder="general")
    return {"path": path}
