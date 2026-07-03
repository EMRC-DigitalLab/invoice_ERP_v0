import json
import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        status_code = 500
        error_detail = None

        try:
            response = await call_next(request)
            status_code = response.status_code

            if status_code >= 400:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                try:
                    error_detail = str(json.loads(body).get("detail", ""))[:1000]
                except Exception:
                    error_detail = body.decode(errors="replace")[:1000]
                response = Response(
                    content=body,
                    status_code=status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

        except Exception as exc:
            error_detail = str(exc)[:1000]
            raise

        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            _persist(request, status_code, duration_ms, error_detail)

        return response


def _persist(
    request: Request, status_code: int, duration_ms: float, error: str | None
) -> None:
    from app.core.database import SessionLocal
    from app.models.log import RequestLog

    db = SessionLocal()
    try:
        db.add(
            RequestLog(
                id=uuid.uuid4().hex,
                timestamp=datetime.now(timezone.utc),
                method=request.method,
                path=request.url.path,
                query=str(request.url.query) or None,
                status_code=status_code,
                duration_ms=duration_ms,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", "")[:200],
                error=error,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
