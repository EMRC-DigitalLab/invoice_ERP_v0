from fastapi import APIRouter
from app.api.v1 import uploads, notifications

router = APIRouter()


@router.get("/ping")
def ping():
    return {"message": "pong"}


router.include_router(uploads.router)
router.include_router(notifications.router)
