from fastapi import APIRouter

from app.api.v1 import auth, notifications, org, requests, uploads

router = APIRouter()


@router.get("/ping")
def ping():
    return {"message": "pong"}


router.include_router(auth.router)
router.include_router(requests.router)
router.include_router(org.router)
router.include_router(uploads.router)
router.include_router(notifications.router)
