from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.api.v1.router import router as v1_router

app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

ENV_MESSAGES = {
    "staging": "Hi, I am v0 Development ERP. All I want right now is to be full and alive as an ERP — not just an invoice tool. We are building.",
    "production": "Hi, I am v0 ERP — production is live. Full ERP, not just invoicing. We are operational.",
    "development": "Hi, I am v0 ERP — running locally in development mode.",
}


@app.get("/health")
def health_check():
    message = ENV_MESSAGES.get(settings.ENV, "Hi, I am v0 ERP.")

    db_status = "ok"
    db_error = None
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as e:
        db_status = "error"
        db_error = str(e)

    return {
        "message": message,
        "env": settings.ENV,
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        **({"database_error": db_error} if db_error else {}),
    }
