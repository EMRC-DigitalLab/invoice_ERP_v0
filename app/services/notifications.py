from datetime import datetime, timezone
from typing import List
import uuid


_store: List[dict] = []


def create_notification(user_id: str, message: str) -> dict:
    notification = {
        "id": uuid.uuid4().hex,
        "user_id": user_id,
        "message": message,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _store.append(notification)
    return notification


def get_notifications(user_id: str, page: int = 1, page_size: int = 20) -> dict:
    user_notifs = [n for n in _store if n["user_id"] == user_id]
    user_notifs.sort(key=lambda n: n["created_at"], reverse=True)
    start = (page - 1) * page_size
    return {
        "total": len(user_notifs),
        "page": page,
        "items": user_notifs[start : start + page_size],
    }


def mark_read(notification_id: str, user_id: str) -> bool:
    for n in _store:
        if n["id"] == notification_id and n["user_id"] == user_id:
            n["read"] = True
            return True
    return False
