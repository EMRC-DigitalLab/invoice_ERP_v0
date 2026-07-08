from fastapi import APIRouter

from app.api.v1.requests import actions, attachments, clarifications, crud

router = APIRouter()

router.include_router(crud.router)
router.include_router(actions.router)
router.include_router(clarifications.router)
router.include_router(attachments.router)
