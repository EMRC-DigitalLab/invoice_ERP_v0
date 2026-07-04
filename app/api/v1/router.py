from fastapi import APIRouter

from app.api.v1 import (
    auth,
    logs,
    notifications,
    org,
    purchase_orders,
    requests,
    uploads,
)

router = APIRouter()


@router.get("/ping")
def ping():
    return {"message": "pong"}


router.include_router(auth.router)
router.include_router(requests.router)
router.include_router(org.router)
router.include_router(purchase_orders.router)
router.include_router(uploads.router)
router.include_router(notifications.router)
router.include_router(logs.router)
