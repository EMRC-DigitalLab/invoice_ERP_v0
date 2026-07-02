from fastapi import APIRouter
from app.services.notifications import get_notifications, mark_read

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/{user_id}")
def list_notifications(user_id: str, page: int = 1):
    return get_notifications(user_id=user_id, page=page)


@router.patch("/{notification_id}/read")
def read_notification(notification_id: str, user_id: str):
    success = mark_read(notification_id=notification_id, user_id=user_id)
    return {"success": success}
