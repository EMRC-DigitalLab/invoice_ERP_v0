import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.migrations import run_pending_migrations
from app.core.scheduler import start_scheduler, stop_scheduler
from app.middleware.request_logger import RequestLoggingMiddleware

# Without this, logger.info()/.warning() calls anywhere in the app (e.g. the
# scheduler in app/core/scheduler.py) go nowhere — Python's root logger has
# no handler by default and silently drops anything below WARNING. This
# doesn't affect SQLAlchemy's own query logging (echo=settings.DEBUG in
# app/core/database.py), which configures its logger independently.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.models  # noqa: F401 — registers all tables with Base.metadata

    Base.metadata.create_all(bind=engine)
    run_pending_migrations(engine)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENV != "production" else [],
    allow_origin_regex=r"(https://.*\.vercel\.app|https://.*\.raven-emrc\.com|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?)",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
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
