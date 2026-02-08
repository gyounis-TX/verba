import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.middleware.cors import CORSMiddleware


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Prevent the Tauri webview from caching API responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


def add_cors_middleware(app):
    # Read allowed origins from env var (comma-separated) for web mode
    # If not set, allow all origins (desktop mode)
    allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
    if allowed_origins_env:
        origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
    else:
        origins = ["*"]

    app.add_middleware(NoCacheMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
