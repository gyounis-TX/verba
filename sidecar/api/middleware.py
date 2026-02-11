import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send
from fastapi.middleware.cors import CORSMiddleware


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Prevent the Tauri webview from caching API responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


class CORSErrorWrapper:
    """Raw ASGI wrapper that ensures CORS headers on ALL responses.

    Starlette's BaseHTTPMiddleware swallows exceptions from call_next()
    and produces bare 500 responses that bypass CORSMiddleware. This
    wrapper sits outside everything and patches CORS headers onto any
    response that's missing them.
    """

    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed_origins = allowed_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract Origin from request headers
        request_origin = None
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"origin":
                request_origin = header_value.decode("latin-1")
                break

        if not request_origin:
            await self.app(scope, receive, send)
            return

        # Check if origin is allowed
        origin_allowed = (
            "*" in self.allowed_origins
            or request_origin in self.allowed_origins
        )
        if not origin_allowed:
            await self.app(scope, receive, send)
            return

        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                # Only add if CORSMiddleware didn't already
                if b"access-control-allow-origin" not in headers:
                    extra = [
                        (b"access-control-allow-origin", request_origin.encode()),
                        (b"access-control-allow-credentials", b"true"),
                    ]
                    message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_cors)


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
    # Outermost: ensure CORS headers even on bare 500s from BaseHTTPMiddleware
    app.add_middleware(CORSErrorWrapper, allowed_origins=origins)
