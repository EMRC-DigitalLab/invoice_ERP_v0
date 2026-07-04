from fastapi import Request

from app.core.config import settings


def get_public_base_url(request: Request) -> str:
    """
    Absolute origin to prefix file URLs with, so links work regardless of which
    frontend (or domain) is consuming the API — never a bare relative path.
    """
    if settings.PUBLIC_BASE_URL:
        return settings.PUBLIC_BASE_URL.rstrip("/")

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme}://{host}"
